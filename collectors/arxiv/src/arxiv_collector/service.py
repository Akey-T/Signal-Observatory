"""Topic-driven arXiv backfill and incremental orchestration."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from arxiv_collector.client import (
    ArxivClient,
    ArxivClientError,
    ArxivForbiddenError,
)
from arxiv_collector.models import (
    ArxivHTTPResponse,
    ArxivRequest,
    PersistenceCounts,
)
from arxiv_collector.parser import ArxivAtomParser, ArxivParseError
from arxiv_collector.persistence import ArxivPersistence
from arxiv_collector.query import ArxivQueryBuilder, ArxivQueryError
from collector_core import LocalRawStore
from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivPaper,
    ArxivPaperAuthor,
    ArxivPaperCategory,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.base import utc_now
from observatory_db.models import (
    DataQualityCheck,
    IngestionError,
    IngestionRun,
    IngestionStatus,
    QualityStatus,
    Source,
    Topic,
    TopicSourceMapping,
    TopicStatus,
)
from signal_observatory_config import Settings

COLLECTOR_VERSION = "0.1.0"
RAW_SCHEMA_VERSION = "arxiv-atom-v1"
SAFE_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "date",
        "etag",
        "last-modified",
        "retry-after",
        "cache-control",
        "server",
        "via",
    }
)

logger = structlog.get_logger("arxiv_collector")


class ArxivCollectionError(RuntimeError):
    """Raised when collection cannot be safely planned or executed."""


class ArxivRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["backfill", "incremental", "dry_run"]
    run_id: UUID | None = None
    status: str
    started_at: datetime
    finished_at: datetime
    topics_considered: int = Field(ge=0)
    mappings_executed: int = Field(ge=0)
    api_requests: int = Field(ge=0)
    entries_received: int = Field(ge=0)
    new_papers: int = Field(ge=0)
    updated_papers: int = Field(ge=0)
    existing_papers: int = Field(ge=0)
    topic_matches_added: int = Field(ge=0)
    errors: int = Field(ge=0)
    raw_payloads_preserved: int = Field(ge=0)
    estimated_minimum_delay_seconds: float = Field(ge=0)
    checkpoints: list[dict[str, Any]] = Field(default_factory=list)
    planned_queries: list[dict[str, Any]] = Field(default_factory=list)
    data_quality: dict[str, int] = Field(default_factory=dict)


@dataclass(slots=True)
class RunAccumulator:
    started_at: datetime
    topics_considered: int = 0
    mappings_executed: int = 0
    api_requests: int = 0
    entries_received: int = 0
    counts: PersistenceCounts = field(default_factory=PersistenceCounts)
    errors: int = 0
    raw_payloads: int = 0
    stopped_by_safety_limit: bool = False
    successful_windows: int = 0
    failed_mappings: set[UUID] = field(default_factory=set)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    planned_queries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class QueryWindow:
    window_from: datetime
    window_until: datetime

    @property
    def key(self) -> str:
        return f"backfill:{self.window_from.isoformat()}:{self.window_until.isoformat()}"


@dataclass(frozen=True, slots=True)
class WindowOutcome:
    status: ArxivCursorStatus
    split: tuple[QueryWindow, QueryWindow] | None = None


class ArxivCollectionService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        client: ArxivClient | None = None,
        raw_store: LocalRawStore | None = None,
        parser: ArxivAtomParser | None = None,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client = client or ArxivClient(
            base_url=settings.arxiv_api_base_url,
            user_agent=settings.arxiv_user_agent,
            minimum_interval_seconds=settings.arxiv_min_request_interval_seconds,
            timeout_seconds=settings.arxiv_request_timeout_seconds,
            retry_attempts=settings.arxiv_retry_attempts,
        )
        self.raw_store = raw_store or LocalRawStore(settings.raw_data_path)
        self.parser = parser or ArxivAtomParser()
        self.query_builder = ArxivQueryBuilder()
        self.persistence = ArxivPersistence(session)
        self._now = now
        self._monotonic = monotonic

    async def backfill(
        self,
        *,
        topic_slugs: Sequence[str] | None,
        window_from: datetime,
        window_until: datetime,
        dry_run: bool = False,
        max_pages: int | None = None,
        page_size: int | None = None,
    ) -> ArxivRunSummary:
        start = self._utc(window_from)
        end = self._utc(window_until)
        if end <= start:
            raise ArxivCollectionError("backfill --until must be after --from")
        mappings = self._enabled_mappings(topic_slugs)
        windows = self.partition_windows(
            start,
            end,
            window_days=self.settings.arxiv_backfill_window_days,
        )
        started_at = self._now()
        accumulator = RunAccumulator(
            started_at=started_at,
            topics_considered=len({mapping.topic_id for mapping in mappings}),
        )
        for mapping in mappings:
            base_query = self.query_builder.from_mapping(mapping)
            for window in windows:
                accumulator.planned_queries.append(
                    self._plan_item(
                        mapping, base_query, window, page_size or self.settings.arxiv_page_size
                    )
                )
        if dry_run:
            return self._summary(
                mode="dry_run",
                run=None,
                accumulator=accumulator,
                status="dry_run",
                data_quality={},
            )

        source = self._arxiv_source()
        run = self._start_run(source, "backfill", accumulator, start, end)
        started_monotonic = self._monotonic()
        forbidden = False
        for mapping in mappings:
            if self._runtime_exceeded(started_monotonic):
                accumulator.stopped_by_safety_limit = True
                break
            accumulator.mappings_executed += 1
            base_query = self.query_builder.from_mapping(mapping)
            pending = list(windows)
            mapping_failed = False
            while pending:
                window = pending.pop(0)
                try:
                    outcome = await self._collect_window(
                        run=run,
                        mapping=mapping,
                        base_query=base_query,
                        window=window,
                        accumulator=accumulator,
                        max_pages=max_pages,
                        page_size=page_size or self.settings.arxiv_page_size,
                    )
                except ArxivForbiddenError as error:
                    self._record_error(run, mapping, error, critical=True)
                    accumulator.errors += 1
                    accumulator.failed_mappings.add(mapping.id)
                    mapping_failed = True
                    forbidden = True
                    break
                except (
                    ArxivClientError,
                    ArxivCollectionError,
                    ArxivParseError,
                    ArxivQueryError,
                ) as error:
                    self._record_error(run, mapping, error)
                    accumulator.errors += 1
                    accumulator.failed_mappings.add(mapping.id)
                    mapping_failed = True
                    continue
                if outcome.split is not None:
                    pending[0:0] = list(outcome.split)
                elif outcome.status is ArxivCursorStatus.SUCCEEDED:
                    accumulator.successful_windows += 1
                else:
                    mapping_failed = True
            if mapping_failed:
                accumulator.failed_mappings.add(mapping.id)
            if forbidden or accumulator.api_requests >= self.settings.arxiv_max_requests_per_run:
                accumulator.stopped_by_safety_limit = not forbidden
                break

        status = self._terminal_status(accumulator)
        data_quality = self._finish_run(run, accumulator, status)
        return self._summary(
            mode="backfill",
            run=run,
            accumulator=accumulator,
            status=status.value,
            data_quality=data_quality,
        )

    @staticmethod
    def partition_windows(
        window_from: datetime, window_until: datetime, *, window_days: int
    ) -> tuple[QueryWindow, ...]:
        if window_days < 1:
            raise ArxivCollectionError("backfill window_days must be positive")
        windows: list[QueryWindow] = []
        cursor = window_from
        while cursor < window_until:
            boundary = min(cursor + timedelta(days=window_days), window_until)
            windows.append(QueryWindow(cursor, boundary))
            cursor = boundary
        return tuple(windows)

    async def _collect_window(
        self,
        *,
        run: IngestionRun,
        mapping: TopicSourceMapping,
        base_query: str,
        window: QueryWindow,
        accumulator: RunAccumulator,
        max_pages: int | None,
        page_size: int,
    ) -> WindowOutcome:
        cursor = self._cursor(mapping, window)
        if cursor.status is ArxivCursorStatus.SUCCEEDED:
            self._append_checkpoint(accumulator, cursor)
            return WindowOutcome(ArxivCursorStatus.SUCCEEDED)
        cursor.status = ArxivCursorStatus.RUNNING
        cursor.last_error = None
        cursor.window_from = window.window_from
        cursor.window_until = window.window_until
        cursor.checkpoint = {
            "topic_slug": mapping.topic.slug,
            "mapping_id": str(mapping.id),
            "window_from": window.window_from.isoformat(),
            "window_until": window.window_until.isoformat(),
            "next_start": cursor.next_start,
        }
        self.session.commit()

        dated_query = self.query_builder.with_submitted_window(
            base_query,
            window_from=window.window_from,
            window_until=window.window_until,
        )
        pages = 0
        results_seen = 0
        while True:
            if self._request_limit_reached(accumulator):
                return self._pause_cursor(cursor, accumulator, "max_requests_per_run")
            if max_pages is not None and pages >= max_pages:
                return self._pause_cursor(cursor, accumulator, "max_pages")
            if results_seen >= self.settings.arxiv_max_results_per_topic:
                return self._pause_cursor(cursor, accumulator, "max_results_per_topic")

            request = ArxivRequest(
                search_query=dated_query,
                start=cursor.next_start,
                max_results=page_size,
                sort_by="submittedDate",
                sort_order="ascending",
            )
            raw_response: ArxivRawResponse | None = None

            async def preserve(response: ArxivHTTPResponse) -> None:
                nonlocal raw_response
                safe_response = response.model_copy(
                    update={"headers": self._safe_headers(response.headers)}
                )
                raw = self.raw_store.write(
                    source="arxiv",
                    payload=response.body,
                    request_timestamp=response.requested_at,
                    collector_version=COLLECTOR_VERSION,
                    schema_version=RAW_SCHEMA_VERSION,
                    source_metadata={
                        "requested_at": response.requested_at.isoformat(),
                        "request": response.request.model_dump(mode="json"),
                        "http_status": response.status_code,
                        "response_headers": safe_response.headers,
                        "collector_version": COLLECTOR_VERSION,
                        "schema_version": RAW_SCHEMA_VERSION,
                    },
                )
                raw_response = self.persistence.record_raw_response(
                    run=run,
                    topic=mapping.topic,
                    mapping=mapping,
                    raw=raw,
                    response=safe_response,
                    request_metadata={
                        "mode": "backfill",
                        "window_from": window.window_from.isoformat(),
                        "window_until": window.window_until.isoformat(),
                        "query_hash": hashlib.sha256(
                            response.request.search_query.encode("utf-8")
                        ).hexdigest(),
                    },
                )
                accumulator.api_requests += 1
                accumulator.raw_payloads += 1
                self.session.commit()

            response = await self.client.get(request, on_response=preserve)
            if raw_response is None:
                raise ArxivCollectionError("arXiv response was not persisted to Raw")
            try:
                feed = self.parser.parse(response.body)
            except ArxivParseError as error:
                self.persistence.record_parse_error(raw_response, error)
                cursor.status = ArxivCursorStatus.FAILED
                cursor.last_error = str(error)
                self.session.commit()
                raise
            if feed.start_index != request.start:
                pagination_error = ArxivParseError(
                    f"pagination mismatch: requested {request.start}, received {feed.start_index}"
                )
                self.persistence.record_parse_error(raw_response, pagination_error)
                cursor.status = ArxivCursorStatus.FAILED
                cursor.last_error = str(pagination_error)
                self.session.commit()
                raise pagination_error
            if (
                request.start == 0
                and feed.total_results > self.settings.arxiv_large_query_threshold
            ):
                raw_response.parsed_entry_count = len(feed.articles)
                split = self._split_window(window)
                if split is None:
                    return self._pause_cursor(cursor, accumulator, "large_query_one_day")
                cursor.status = ArxivCursorStatus.PARTIAL
                cursor.last_error = "large query partitioned into smaller date windows"
                cursor.checkpoint = {**cursor.checkpoint, "reason": "large_query_partition"}
                self.session.commit()
                self._append_checkpoint(accumulator, cursor)
                return WindowOutcome(ArxivCursorStatus.PARTIAL, split=split)

            counts = self.persistence.persist_feed(
                feed=feed,
                raw_response=raw_response,
                run=run,
                topic=mapping.topic,
                mapping=mapping,
                matched_query=base_query,
            )
            accumulator.counts = accumulator.counts.add(counts)
            accumulator.entries_received += len(feed.articles)
            pages += 1
            results_seen += len(feed.articles)
            advance = max(len(feed.articles), feed.items_per_page)
            if advance == 0:
                if request.start < feed.total_results:
                    return self._pause_cursor(cursor, accumulator, "empty_page_before_total")
                cursor.next_start = feed.total_results
            else:
                cursor.next_start = feed.start_index + advance
            cursor.checkpoint = {**cursor.checkpoint, "next_start": cursor.next_start}
            logger.info(
                "arxiv_page_persisted",
                source="arxiv",
                run_id=str(run.run_id),
                topic_id=str(mapping.topic_id),
                mapping_id=str(mapping.id),
                request_number=accumulator.api_requests,
                query_hash=hashlib.sha256(dated_query.encode()).hexdigest(),
                page=pages,
                records_received=len(feed.articles),
                records_inserted=counts.papers_inserted,
                duration_ms=response.duration_ms,
                status="persisted",
            )
            if cursor.next_start >= feed.total_results:
                cursor.status = ArxivCursorStatus.SUCCEEDED
                cursor.last_successful_run_at = self._now()
                cursor.last_query_from = window.window_from
                cursor.last_query_until = window.window_until
                cursor.last_observed_updated_at = max(
                    (article.updated_at for article in feed.articles),
                    default=cursor.last_observed_updated_at,
                )
                cursor.last_error = None
                self.session.commit()
                self._append_checkpoint(accumulator, cursor)
                return WindowOutcome(ArxivCursorStatus.SUCCEEDED)
            self.session.commit()

    def _enabled_mappings(self, topic_slugs: Sequence[str] | None) -> list[TopicSourceMapping]:
        statement = (
            select(TopicSourceMapping)
            .join(TopicSourceMapping.source)
            .join(TopicSourceMapping.topic)
            .where(
                Source.name == "arxiv",
                TopicSourceMapping.enabled.is_(True),
                Topic.status == TopicStatus.ACTIVE,
            )
            .options(
                selectinload(TopicSourceMapping.source),
                selectinload(TopicSourceMapping.topic),
            )
            .order_by(Topic.monitoring_priority.desc(), Topic.slug)
        )
        requested = tuple(dict.fromkeys(topic_slugs or ()))
        if requested:
            statement = statement.where(Topic.slug.in_(requested))
        mappings = list(self.session.scalars(statement).all())
        found = {mapping.topic.slug for mapping in mappings}
        missing = sorted(set(requested) - found)
        if missing:
            raise ArxivCollectionError(
                "active enabled arXiv mapping not found for: " + ", ".join(missing)
            )
        if not mappings:
            raise ArxivCollectionError("no active enabled arXiv mappings are available")
        return mappings

    def _arxiv_source(self) -> Source:
        source = self.session.scalar(select(Source).where(Source.name == "arxiv"))
        if source is None or not source.is_active:
            raise ArxivCollectionError("arXiv source is not synchronized or active")
        return source

    def _start_run(
        self,
        source: Source,
        mode: str,
        accumulator: RunAccumulator,
        window_from: datetime,
        window_until: datetime,
    ) -> IngestionRun:
        run = IngestionRun(
            source=source,
            status=IngestionStatus.RUNNING,
            collector_version=COLLECTOR_VERSION,
            checkpoint_before={
                "window_from": window_from.isoformat(),
                "window_until": window_until.isoformat(),
            },
            metadata_={
                "mode": mode,
                "schema_version": RAW_SCHEMA_VERSION,
                "minimum_request_interval_seconds": (
                    self.settings.arxiv_min_request_interval_seconds
                ),
                "concurrency": 1,
            },
        )
        self.session.add(run)
        self.session.commit()
        logger.info("arxiv_run_started", source="arxiv", run_id=str(run.run_id), mode=mode)
        return run

    def _cursor(self, mapping: TopicSourceMapping, window: QueryWindow) -> ArxivCollectionCursor:
        cursor = self.session.scalar(
            select(ArxivCollectionCursor).where(
                ArxivCollectionCursor.source_mapping_id == mapping.id,
                ArxivCollectionCursor.cursor_key == window.key,
            )
        )
        if cursor is None:
            cursor = ArxivCollectionCursor(
                topic_id=mapping.topic_id,
                source_mapping_id=mapping.id,
                cursor_key=window.key,
                mode="backfill",
                window_from=window.window_from,
                window_until=window.window_until,
                next_start=0,
                checkpoint={},
                status=ArxivCursorStatus.PENDING,
            )
            self.session.add(cursor)
            self.session.flush()
        return cursor

    def _pause_cursor(
        self,
        cursor: ArxivCollectionCursor,
        accumulator: RunAccumulator,
        reason: str,
    ) -> WindowOutcome:
        cursor.status = ArxivCursorStatus.PARTIAL
        cursor.last_error = reason
        cursor.checkpoint = {**cursor.checkpoint, "reason": reason, "next_start": cursor.next_start}
        accumulator.stopped_by_safety_limit = True
        self.session.commit()
        self._append_checkpoint(accumulator, cursor)
        return WindowOutcome(ArxivCursorStatus.PARTIAL)

    def _record_error(
        self,
        run: IngestionRun,
        mapping: TopicSourceMapping,
        error: BaseException,
        *,
        critical: bool = False,
    ) -> None:
        cursor = self.session.scalar(
            select(ArxivCollectionCursor)
            .where(ArxivCollectionCursor.source_mapping_id == mapping.id)
            .order_by(ArxivCollectionCursor.updated_at.desc())
            .limit(1)
        )
        if cursor is not None:
            cursor.status = ArxivCursorStatus.FAILED
            cursor.last_error = str(error)
        self.session.add(
            IngestionError(
                run_id=run.run_id,
                error_type=type(error).__name__,
                message=str(error),
                record_identifier=str(mapping.id),
                details={
                    "source": "arxiv",
                    "topic_id": str(mapping.topic_id),
                    "mapping_id": str(mapping.id),
                    "critical": critical,
                },
            )
        )
        self.session.commit()

    def _finish_run(
        self,
        run: IngestionRun,
        accumulator: RunAccumulator,
        status: IngestionStatus,
    ) -> dict[str, int]:
        data_quality = self._quality_counts(run, accumulator)
        warning_names = {
            "duplicate_paper_count",
            "papers_without_authors",
            "papers_without_categories",
            "parse_error_count",
            "enabled_topics_without_arxiv_mapping",
            "stale_cursors",
            "failed_mappings",
        }
        for name, value in data_quality.items():
            quality_status = (
                QualityStatus.WARNING
                if name in warning_names and value > 0
                else QualityStatus.PASSED
            )
            self.session.add(
                DataQualityCheck(
                    run_id=run.run_id,
                    name=name,
                    status=quality_status,
                    observed={"count": value},
                    expected={"count": 0} if name in warning_names else {"minimum": 0},
                    details={"source": "arxiv"},
                )
            )
        run.status = status
        run.finished_at = self._now()
        run.records_requested = accumulator.api_requests * self.settings.arxiv_page_size
        run.records_received = accumulator.entries_received
        run.records_inserted = accumulator.counts.papers_inserted
        run.records_updated = accumulator.counts.papers_updated
        run.records_skipped = accumulator.counts.papers_existing
        run.error_count = accumulator.errors
        run.checkpoint_after = {"checkpoints": accumulator.checkpoints}
        run.metadata_ = {
            **run.metadata_,
            "api_requests": accumulator.api_requests,
            "raw_payloads_preserved": accumulator.raw_payloads,
            "topic_matches_added": accumulator.counts.topic_matches_added,
            "data_quality": data_quality,
        }
        self.session.commit()
        logger.info(
            "arxiv_run_finished",
            source="arxiv",
            run_id=str(run.run_id),
            status=status.value,
            api_requests=accumulator.api_requests,
            records_received=accumulator.entries_received,
            error_count=accumulator.errors,
        )
        return data_quality

    def _quality_counts(self, run: IngestionRun, accumulator: RunAccumulator) -> dict[str, int]:
        run_id = run.run_id
        raw_count = self.session.scalar(
            select(func.count())
            .select_from(ArxivRawResponse)
            .where(ArxivRawResponse.ingestion_run_id == run_id)
        )
        parsed_count = self.session.scalar(
            select(func.coalesce(func.sum(ArxivRawResponse.parsed_entry_count), 0)).where(
                ArxivRawResponse.ingestion_run_id == run_id
            )
        )
        unique_papers = self.session.scalar(
            select(func.count(func.distinct(ArxivPaperObservation.paper_id))).where(
                ArxivPaperObservation.ingestion_run_id == run_id
            )
        )
        topic_matches = self.session.scalar(
            select(func.count())
            .select_from(ArxivTopicMatch)
            .where(ArxivTopicMatch.last_ingestion_run_id == run_id)
        )
        without_authors = self.session.scalar(
            select(func.count())
            .select_from(ArxivPaper)
            .outerjoin(ArxivPaperAuthor)
            .where(ArxivPaperAuthor.paper_id.is_(None))
        )
        without_categories = self.session.scalar(
            select(func.count())
            .select_from(ArxivPaper)
            .outerjoin(ArxivPaperCategory)
            .where(ArxivPaperCategory.paper_id.is_(None))
        )
        parse_errors = self.session.scalar(
            select(func.count())
            .select_from(ArxivRawResponse)
            .where(
                ArxivRawResponse.ingestion_run_id == run_id,
                ArxivRawResponse.parse_error.is_not(None),
            )
        )
        mapped_topics = (
            select(TopicSourceMapping.topic_id)
            .join(TopicSourceMapping.source)
            .where(Source.name == "arxiv", TopicSourceMapping.enabled.is_(True))
        )
        without_mapping = self.session.scalar(
            select(func.count())
            .select_from(Topic)
            .where(
                Topic.status == TopicStatus.ACTIVE,
                Topic.id.not_in(mapped_topics),
            )
        )
        stale_before = self._now() - timedelta(days=2)
        stale_cursors = self.session.scalar(
            select(func.count())
            .select_from(ArxivCollectionCursor)
            .where(
                ArxivCollectionCursor.mode == "incremental",
                ArxivCollectionCursor.last_successful_run_at.is_not(None),
                ArxivCollectionCursor.last_successful_run_at < stale_before,
            )
        )
        return {
            "raw_response_count": int(raw_count or 0),
            "parsed_entry_count": int(parsed_count or 0),
            "unique_paper_count": int(unique_papers or 0),
            "topic_match_count": int(topic_matches or 0),
            "duplicate_paper_count": accumulator.counts.duplicate_papers,
            "papers_without_authors": int(without_authors or 0),
            "papers_without_categories": int(without_categories or 0),
            "parse_error_count": int(parse_errors or 0),
            "enabled_topics_without_arxiv_mapping": int(without_mapping or 0),
            "stale_cursors": int(stale_cursors or 0),
            "failed_mappings": len(accumulator.failed_mappings),
        }

    def _summary(
        self,
        *,
        mode: Literal["backfill", "incremental", "dry_run"],
        run: IngestionRun | None,
        accumulator: RunAccumulator,
        status: str,
        data_quality: dict[str, int],
    ) -> ArxivRunSummary:
        finished = run.finished_at if run is not None else self._now()
        assert finished is not None
        return ArxivRunSummary(
            mode=mode,
            run_id=run.run_id if run is not None else None,
            status=status,
            started_at=accumulator.started_at,
            finished_at=finished,
            topics_considered=accumulator.topics_considered,
            mappings_executed=accumulator.mappings_executed,
            api_requests=accumulator.api_requests,
            entries_received=accumulator.entries_received,
            new_papers=accumulator.counts.papers_inserted,
            updated_papers=accumulator.counts.papers_updated,
            existing_papers=accumulator.counts.papers_existing,
            topic_matches_added=accumulator.counts.topic_matches_added,
            errors=accumulator.errors,
            raw_payloads_preserved=accumulator.raw_payloads,
            estimated_minimum_delay_seconds=max(
                0,
                (len(accumulator.planned_queries) - 1)
                * self.settings.arxiv_min_request_interval_seconds,
            ),
            checkpoints=accumulator.checkpoints,
            planned_queries=accumulator.planned_queries,
            data_quality=data_quality,
        )

    @staticmethod
    def _terminal_status(accumulator: RunAccumulator) -> IngestionStatus:
        if accumulator.errors and accumulator.successful_windows == 0:
            return IngestionStatus.FAILED
        if accumulator.errors or accumulator.stopped_by_safety_limit:
            return IngestionStatus.PARTIAL
        return IngestionStatus.SUCCEEDED

    def _request_limit_reached(self, accumulator: RunAccumulator) -> bool:
        return accumulator.api_requests >= self.settings.arxiv_max_requests_per_run

    def _runtime_exceeded(self, started_monotonic: float) -> bool:
        limit = self.settings.arxiv_max_runtime_minutes * 60
        return self._monotonic() - started_monotonic >= limit

    @staticmethod
    def _split_window(window: QueryWindow) -> tuple[QueryWindow, QueryWindow] | None:
        duration = window.window_until - window.window_from
        if duration <= timedelta(days=1):
            return None
        midpoint = window.window_from + duration / 2
        return (
            QueryWindow(window.window_from, midpoint),
            QueryWindow(midpoint, window.window_until),
        )

    @staticmethod
    def _append_checkpoint(accumulator: RunAccumulator, cursor: ArxivCollectionCursor) -> None:
        accumulator.checkpoints.append(
            {
                "cursor_key": cursor.cursor_key,
                "status": cursor.status.value,
                "next_start": cursor.next_start,
                "checkpoint": cursor.checkpoint,
            }
        )

    @staticmethod
    def _plan_item(
        mapping: TopicSourceMapping,
        base_query: str,
        window: QueryWindow,
        page_size: int,
    ) -> dict[str, Any]:
        return {
            "topic_slug": mapping.topic.slug,
            "mapping_id": str(mapping.id),
            "base_query": base_query,
            "window_from": window.window_from.isoformat(),
            "window_until": window.window_until.isoformat(),
            "page_size": page_size,
        }

    @staticmethod
    def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
        return {
            key: value
            for key, value in headers.items()
            if key.casefold() in SAFE_RESPONSE_HEADERS or key.casefold().startswith("x-")
        }

    @staticmethod
    def date_start(value: date) -> datetime:
        return datetime.combine(value, datetime_time.min, tzinfo=UTC)

    @staticmethod
    def date_until_exclusive(value: date) -> datetime:
        return datetime.combine(value + timedelta(days=1), datetime_time.min, tzinfo=UTC)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ArxivCollectionError("collection timestamps must be timezone-aware")
        return value.astimezone(UTC)
