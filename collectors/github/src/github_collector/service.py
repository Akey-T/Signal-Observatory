"""Bounded GitHub discovery and immutable daily Repository snapshot orchestration."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from collector_core import LocalRawStore
from github_collector.client import (
    GithubBudgetExhaustedError,
    GithubClient,
    GithubClientError,
    GithubHTTPError,
    GithubNotConfiguredError,
    GithubRateLimitError,
    build_url,
    next_link,
)
from github_collector.models import GithubHTTPResponse, GithubRequest
from github_collector.parser import GithubJsonParser, GithubParseError
from github_collector.persistence import GithubPersistence
from github_collector.query import GithubQueryError, GithubRepositoryQueryBuilder
from observatory_db.github_models import (
    GithubDiscoveryState,
    GithubOperationStatus,
    GithubRawResponse,
    GithubRepository,
    GithubRepositoryPollState,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
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
RAW_SCHEMA_VERSION = "1"
logger = structlog.get_logger("github_collector")


class GithubCollectionError(RuntimeError):
    """Raised for invalid operator requests or unavailable prerequisites."""


class GithubRequestLimitReached(GithubCollectionError):
    """Raised before a request would exceed the configured per-run limit."""


class GithubRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["dry_run", "discovery", "snapshot"]
    run_id: UUID | None = None
    status: str
    started_at: datetime
    finished_at: datetime
    auth_configured: bool
    topics_considered: int = 0
    mappings_executed: int = 0
    requests_sent: int = 0
    raw_payloads_preserved: int = 0
    repositories_received: int = 0
    unique_repositories: int = 0
    new_repositories: int = 0
    existing_repositories: int = 0
    topic_matches_added: int = 0
    fork_count: int = 0
    archived_count: int = 0
    repositories_due: int = 0
    responses_200: int = 0
    responses_304: int = 0
    responses_404: int = 0
    rate_limited_responses: int = 0
    snapshots_created: int = 0
    unchanged_observations: int = 0
    failed_items: int = 0
    rate_limit_pauses: int = 0
    errors: int = 0
    planned_queries: list[dict[str, Any]] = Field(default_factory=list)
    data_quality: dict[str, int | float | None] = Field(default_factory=dict)
    rate_budgets: dict[str, dict[str, Any]] = Field(default_factory=dict)


@dataclass(slots=True)
class RunAccumulator:
    topics_considered: int = 0
    mappings_executed: int = 0
    requests_sent: int = 0
    raw_payloads: int = 0
    repositories_received: int = 0
    repository_ids: set[int] = field(default_factory=set)
    new_repositories: int = 0
    existing_repositories: int = 0
    topic_matches_added: int = 0
    fork_count: int = 0
    archived_count: int = 0
    repositories_due: int = 0
    responses_200: int = 0
    responses_304: int = 0
    responses_404: int = 0
    rate_limited_responses: int = 0
    snapshots_created: int = 0
    unchanged_observations: int = 0
    failed_items: int = 0
    rate_limit_pauses: int = 0
    errors: int = 0
    planned_queries: list[dict[str, Any]] = field(default_factory=list)


class GithubCollectionService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        client: GithubClient | None = None,
        parser: GithubJsonParser | None = None,
        query_builder: GithubRepositoryQueryBuilder | None = None,
        raw_store: LocalRawStore | None = None,
        now: Any = lambda: datetime.now(UTC),
        monotonic: Any = time.monotonic,
    ) -> None:
        self.session = session
        self.settings = settings
        self._provided_client = client
        self.parser = parser or GithubJsonParser()
        self.query_builder = query_builder or GithubRepositoryQueryBuilder()
        self.raw_store = raw_store or LocalRawStore(settings.raw_data_path)
        self.persistence = GithubPersistence(session)
        self._now = now
        self._monotonic = monotonic

    async def discover(
        self,
        *,
        topic_slugs: Sequence[str] | None = None,
        dry_run: bool = False,
        max_results: int | None = None,
        max_requests: int | None = None,
    ) -> GithubRunSummary:
        started_at = self._utc(self._now())
        mappings = self._enabled_mappings(topic_slugs)
        result_cap = max_results or self.settings.github_discovery_max_results_per_mapping
        request_cap = max_requests or self.settings.github_max_requests_per_run
        if result_cap < 1 or request_cap < 1:
            raise GithubCollectionError("GitHub result and request limits must be positive")
        accumulator = RunAccumulator(
            topics_considered=len({mapping.topic_id for mapping in mappings})
        )
        for mapping in mappings:
            queries = self.query_builder.from_mapping(mapping)
            accumulator.planned_queries.append(
                {
                    "topic_slug": mapping.topic.slug,
                    "mapping_id": str(mapping.id),
                    "queries": [self._effective_query(query) for query in queries],
                    "max_results": result_cap,
                    "page_size": min(self.settings.github_discovery_page_size, result_cap),
                }
            )
        if dry_run:
            finished_at = self._utc(self._now())
            return self._summary(
                mode="dry_run",
                run=None,
                status="dry_run",
                started_at=started_at,
                finished_at=finished_at,
                accumulator=accumulator,
                data_quality={},
                client=None,
            )

        client = self._client()
        run = self._start_run("discovery", started_at)
        for mapping in mappings:
            if self._runtime_exceeded(started_at):
                accumulator.errors += 1
                self._record_mapping_error(
                    run, mapping, GithubCollectionError("GitHub discovery runtime limit reached")
                )
                break
            accumulator.mappings_executed += 1
            try:
                await self._discover_mapping(
                    mapping=mapping,
                    run=run,
                    client=client,
                    accumulator=accumulator,
                    result_cap=result_cap,
                    request_cap=request_cap,
                )
            except (
                GithubClientError,
                GithubParseError,
                GithubQueryError,
                GithubRequestLimitReached,
            ) as error:
                accumulator.errors += 1
                accumulator.failed_items += 1
                self._record_mapping_error(run, mapping, error)
                if isinstance(error, (GithubBudgetExhaustedError, GithubRequestLimitReached)):
                    break
        status = self._terminal_status(accumulator)
        data_quality = self._finish_run(run, status, accumulator, mode="discovery")
        return self._summary(
            mode="discovery",
            run=run,
            status=status.value,
            started_at=started_at,
            finished_at=run.finished_at or self._utc(self._now()),
            accumulator=accumulator,
            data_quality=data_quality,
            client=client,
        )

    async def snapshot(
        self,
        *,
        topic_slugs: Sequence[str] | None = None,
        repository_ids: Sequence[int] | None = None,
        dry_run: bool = False,
        max_requests: int | None = None,
    ) -> GithubRunSummary:
        started_at = self._utc(self._now())
        request_cap = max_requests or self.settings.github_max_requests_per_run
        repositories = self._tracked_repositories(
            topic_slugs=topic_slugs, repository_ids=repository_ids, due_at=started_at
        )
        accumulator = RunAccumulator(
            repositories_due=len(repositories),
            topics_considered=len(set(topic_slugs or [])),
        )
        accumulator.planned_queries = [
            {
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
                "conditional": self.settings.github_conditional_requests_enabled,
            }
            for repository in repositories
        ]
        if dry_run:
            finished_at = self._utc(self._now())
            return self._summary(
                mode="dry_run",
                run=None,
                status="dry_run",
                started_at=started_at,
                finished_at=finished_at,
                accumulator=accumulator,
                data_quality={},
                client=None,
            )
        client = self._client()
        run = self._start_run("snapshot", started_at)
        for repository in repositories:
            if accumulator.requests_sent >= request_cap or self._runtime_exceeded(started_at):
                accumulator.errors += 1
                break
            try:
                await self._snapshot_repository(
                    repository=repository,
                    run=run,
                    client=client,
                    accumulator=accumulator,
                    request_cap=request_cap,
                )
            except (
                GithubClientError,
                GithubParseError,
                GithubRequestLimitReached,
                ValueError,
            ) as error:
                accumulator.errors += 1
                accumulator.failed_items += 1
                self._record_repository_error(run, repository, error)
                if isinstance(error, (GithubBudgetExhaustedError, GithubRequestLimitReached)):
                    break
        status = self._terminal_status(accumulator)
        data_quality = self._finish_run(run, status, accumulator, mode="snapshot")
        return self._summary(
            mode="snapshot",
            run=run,
            status=status.value,
            started_at=started_at,
            finished_at=run.finished_at or self._utc(self._now()),
            accumulator=accumulator,
            data_quality=data_quality,
            client=client,
        )

    async def _discover_mapping(
        self,
        *,
        mapping: TopicSourceMapping,
        run: IngestionRun,
        client: GithubClient,
        accumulator: RunAccumulator,
        result_cap: int,
        request_cap: int,
    ) -> None:
        state = self._discovery_state(mapping)
        state.status = GithubOperationStatus.RUNNING
        state.last_checked_at = self._utc(self._now())
        state.last_ingestion_run_id = run.run_id
        self.session.commit()
        received_for_mapping = 0
        for configured_query in self.query_builder.from_mapping(mapping):
            if received_for_mapping >= result_cap:
                break
            query = self._effective_query(configured_query)
            per_page = min(
                self.settings.github_discovery_page_size, result_cap - received_for_mapping
            )
            parameters = self.query_builder.search_parameters(query, page=1, per_page=per_page)
            url: str | None = build_url(
                self.settings.github_api_base_url, "/search/repositories", parameters
            )
            while url is not None and received_for_mapping < result_cap:
                request = GithubRequest(
                    endpoint_type="repository_search",
                    url=url,
                    query_parameters=dict(parameters),
                )
                raw_responses: list[GithubRawResponse] = []
                response = await client.get(
                    request,
                    on_response=self._raw_sink(
                        run=run,
                        mapping=mapping,
                        repository=None,
                        accumulator=accumulator,
                        collected=raw_responses,
                    ),
                    on_attempt=self._attempt_sink(accumulator, request_cap),
                )
                if response.status_code != 200:
                    raise GithubHTTPError(response)
                raw_response = raw_responses[-1]
                try:
                    parsed = self.parser.parse_search(response.payload)
                except GithubParseError as error:
                    self.persistence.record_parse_error(raw_response, error)
                    self.session.commit()
                    raise
                page_repositories = parsed.repositories[: result_cap - received_for_mapping]
                for repository_data in page_repositories:
                    received_for_mapping += 1
                    accumulator.repositories_received += 1
                    accumulator.repository_ids.add(repository_data.github_repository_id)
                    accumulator.fork_count += int(repository_data.is_fork)
                    accumulator.archived_count += int(
                        repository_data.archived or repository_data.disabled
                    )
                    repository, created = self.persistence.upsert_repository(
                        repository_data, observed_at=response.requested_at
                    )
                    accumulator.new_repositories += int(created)
                    accumulator.existing_repositories += int(not created)
                    tracking = self._tracking_state(repository_data)
                    added = self.persistence.upsert_match(
                        repository=repository,
                        mapping=mapping,
                        query=query,
                        rank=received_for_mapping,
                        run=run,
                        observed_at=response.requested_at,
                        tracking_state=tracking,
                        raw_response=raw_response,
                    )
                    accumulator.topic_matches_added += int(added)
                self.session.commit()
                url = next_link(response.headers)
                if not page_repositories:
                    break
                per_page = min(
                    self.settings.github_discovery_page_size,
                    result_cap - received_for_mapping,
                )
        state.status = GithubOperationStatus.SUCCEEDED
        state.last_checked_at = self._utc(self._now())
        state.last_successful_at = state.last_checked_at
        state.next_eligible_at = state.last_checked_at + timedelta(
            days=self.settings.github_discovery_due_days
        )
        state.last_error = None
        state.metadata_ = {"repositories_received": received_for_mapping}
        self.session.commit()

    async def _snapshot_repository(
        self,
        *,
        repository: GithubRepository,
        run: IngestionRun,
        client: GithubClient,
        accumulator: RunAccumulator,
        request_cap: int,
    ) -> None:
        poll = self._poll_state(repository)
        etag = poll.etag if self.settings.github_conditional_requests_enabled else None
        request = GithubRequest(
            endpoint_type="repository",
            url=repository.api_url,
            query_parameters={},
            github_repository_id=repository.github_repository_id,
            etag=etag,
        )
        raw_responses: list[GithubRawResponse] = []
        try:
            response = await client.get(
                request,
                on_response=self._raw_sink(
                    run=run,
                    mapping=None,
                    repository=repository,
                    accumulator=accumulator,
                    collected=raw_responses,
                ),
                on_attempt=self._attempt_sink(accumulator, request_cap),
            )
        except GithubHTTPError as error:
            response = error.response
            next_eligible = (
                response.rate_limit.reset_at if isinstance(error, GithubRateLimitError) else None
            )
            self.persistence.mark_poll_failure(
                repository=repository,
                observed_at=response.requested_at,
                status=response.status_code,
                error=error,
                next_eligible_at=next_eligible,
            )
            self.session.commit()
            raise
        raw_response = raw_responses[-1]
        if response.status_code == 304:
            _snapshot, created = self.persistence.create_unchanged_snapshot(
                repository=repository,
                run=run,
                raw_response=raw_response,
                observed_at=response.requested_at,
            )
            accumulator.snapshots_created += int(created)
            accumulator.unchanged_observations += 1
            self.session.commit()
            return
        if response.status_code != 200:
            raise GithubHTTPError(response)
        try:
            data = self.parser.parse_repository(response.payload)
        except GithubParseError as error:
            self.persistence.record_parse_error(raw_response, error)
            self.persistence.mark_poll_failure(
                repository=repository,
                observed_at=response.requested_at,
                status=response.status_code,
                error=error,
            )
            self.session.commit()
            raise
        repository, _created = self.persistence.upsert_repository(
            data, observed_at=response.requested_at
        )
        _snapshot, created = self.persistence.create_full_snapshot(
            repository=repository,
            data=data,
            run=run,
            raw_response=raw_response,
            observed_at=response.requested_at,
            etag=raw_response.etag,
        )
        accumulator.snapshots_created += int(created)
        self.session.commit()

    def _raw_sink(
        self,
        *,
        run: IngestionRun,
        mapping: TopicSourceMapping | None,
        repository: GithubRepository | None,
        accumulator: RunAccumulator,
        collected: list[GithubRawResponse],
    ) -> Any:
        async def persist(response: GithubHTTPResponse) -> None:
            raw_record = self.raw_store.write(
                source="github",
                payload=response.payload,
                request_timestamp=response.requested_at,
                collector_version=COLLECTOR_VERSION,
                schema_version=RAW_SCHEMA_VERSION,
                source_metadata={
                    "endpoint_type": response.request.endpoint_type,
                    "request_url_hash": hashlib.sha256(
                        response.request.url.encode("utf-8")
                    ).hexdigest(),
                    "query_parameters": response.request.query_parameters,
                    "github_repository_id": response.request.github_repository_id,
                    "http_status": response.status_code,
                    "etag": self._header(response.headers, "etag"),
                    "last_modified": self._header(response.headers, "last-modified"),
                    "rate_limit": response.rate_limit.model_dump(mode="json"),
                    "response_headers": response.headers,
                },
            )
            raw_response = self.persistence.record_raw_response(
                response=response,
                run=run,
                raw_record=raw_record,
                mapping=mapping,
                repository=repository,
            )
            self.session.commit()
            collected.append(raw_response)
            accumulator.raw_payloads += 1
            accumulator.responses_200 += int(response.status_code == 200)
            accumulator.responses_304 += int(response.status_code == 304)
            accumulator.responses_404 += int(response.status_code == 404)
            if response.status_code in {403, 429}:
                accumulator.rate_limited_responses += 1
                accumulator.rate_limit_pauses += int(
                    response.rate_limit.retry_after_seconds is not None
                    or response.rate_limit.remaining == 0
                )

        return persist

    @staticmethod
    def _attempt_sink(accumulator: RunAccumulator, request_cap: int) -> Any:
        async def count_attempt(_attempt: int) -> None:
            if accumulator.requests_sent >= request_cap:
                raise GithubRequestLimitReached("GitHub request limit reached")
            accumulator.requests_sent += 1

        return count_attempt

    def _enabled_mappings(self, topic_slugs: Sequence[str] | None) -> list[TopicSourceMapping]:
        statement = (
            select(TopicSourceMapping)
            .join(TopicSourceMapping.source)
            .join(TopicSourceMapping.topic)
            .options(joinedload(TopicSourceMapping.topic))
            .where(
                Source.name == "github",
                Source.is_active.is_(True),
                TopicSourceMapping.enabled.is_(True),
                Topic.status == TopicStatus.ACTIVE,
            )
            .order_by(Topic.slug, TopicSourceMapping.id)
        )
        if topic_slugs:
            statement = statement.where(Topic.slug.in_(tuple(topic_slugs)))
        mappings = list(self.session.scalars(statement).unique().all())
        if topic_slugs:
            found = {mapping.topic.slug for mapping in mappings}
            missing = sorted(set(topic_slugs) - found)
            if missing:
                raise GithubCollectionError(
                    "active enabled GitHub mapping not found for: " + ", ".join(missing)
                )
        if not mappings:
            raise GithubCollectionError("no active enabled GitHub mappings are available")
        return mappings

    def _tracked_repositories(
        self,
        *,
        topic_slugs: Sequence[str] | None,
        repository_ids: Sequence[int] | None,
        due_at: datetime,
    ) -> list[GithubRepository]:
        cutoff = due_at - timedelta(hours=self.settings.github_snapshot_due_hours)
        statement = (
            select(GithubRepository)
            .join(GithubTopicRepositoryMatch)
            .outerjoin(GithubRepositoryPollState)
            .where(
                GithubTopicRepositoryMatch.tracking_state == GithubTrackingState.TRACKED,
                or_(
                    GithubRepositoryPollState.last_snapshot_at.is_(None),
                    GithubRepositoryPollState.last_snapshot_at <= cutoff,
                ),
                or_(
                    GithubRepositoryPollState.next_eligible_at.is_(None),
                    GithubRepositoryPollState.next_eligible_at <= due_at,
                ),
            )
            .order_by(GithubRepository.github_repository_id)
        )
        if topic_slugs:
            statement = statement.join(
                Topic, Topic.id == GithubTopicRepositoryMatch.topic_id
            ).where(Topic.slug.in_(tuple(topic_slugs)))
        if repository_ids:
            statement = statement.where(
                GithubRepository.github_repository_id.in_(tuple(repository_ids))
            )
        repositories = list(self.session.scalars(statement).unique().all())
        if repository_ids:
            found = {repository.github_repository_id for repository in repositories}
            missing = sorted(set(repository_ids) - found)
            if missing:
                raise GithubCollectionError(
                    "tracked GitHub repository not found or not due: "
                    + ", ".join(str(value) for value in missing)
                )
        return repositories

    def _github_source(self) -> Source:
        source = self.session.scalar(select(Source).where(Source.name == "github"))
        if source is None or not source.is_active:
            raise GithubCollectionError("GitHub source is not synchronized or active")
        return source

    def _start_run(self, mode: str, started_at: datetime) -> IngestionRun:
        run = IngestionRun(
            source=self._github_source(),
            started_at=started_at,
            status=IngestionStatus.RUNNING,
            collector_version=COLLECTOR_VERSION,
            metadata_={
                "mode": mode,
                "schema_version": RAW_SCHEMA_VERSION,
                "concurrency": self.settings.github_request_concurrency,
                "api_version": self.settings.github_api_version,
                "authenticated": self.settings.github_token is not None,
            },
        )
        self.session.add(run)
        self.session.commit()
        logger.info("github_run_started", source="github", run_id=str(run.run_id), mode=mode)
        return run

    def _client(self) -> GithubClient:
        if self._provided_client is not None:
            return self._provided_client
        token = (
            self.settings.github_token.get_secret_value()
            if self.settings.github_token is not None
            else None
        )
        try:
            return GithubClient(
                token=token,
                api_version=self.settings.github_api_version,
                user_agent=self.settings.github_user_agent,
                require_auth=self.settings.github_require_auth,
                allow_anonymous_smoke=self.settings.github_allow_anonymous_smoke,
                timeout_seconds=self.settings.github_request_timeout_seconds,
                concurrency=self.settings.github_request_concurrency,
                retry_attempts=self.settings.github_retry_attempts,
                min_core_remaining=self.settings.github_min_core_remaining,
                min_search_remaining=self.settings.github_min_search_remaining,
            )
        except GithubNotConfiguredError as error:
            raise GithubCollectionError(str(error)) from error

    def _discovery_state(self, mapping: TopicSourceMapping) -> GithubDiscoveryState:
        state = self.session.scalar(
            select(GithubDiscoveryState).where(GithubDiscoveryState.source_mapping_id == mapping.id)
        )
        if state is None:
            state = GithubDiscoveryState(
                topic_id=mapping.topic_id,
                source_mapping_id=mapping.id,
                status=GithubOperationStatus.PENDING,
            )
            self.session.add(state)
            self.session.flush()
        return state

    def _poll_state(self, repository: GithubRepository) -> GithubRepositoryPollState:
        state = self.session.scalar(
            select(GithubRepositoryPollState).where(
                GithubRepositoryPollState.repository_id == repository.id
            )
        )
        if state is None:
            state = GithubRepositoryPollState(repository_id=repository.id)
            self.session.add(state)
            self.session.flush()
        return state

    def _record_mapping_error(
        self, run: IngestionRun, mapping: TopicSourceMapping, error: BaseException
    ) -> None:
        state = self._discovery_state(mapping)
        state.status = GithubOperationStatus.FAILED
        state.last_checked_at = self._utc(self._now())
        state.last_error = str(error)
        state.last_ingestion_run_id = run.run_id
        self.session.add(
            IngestionError(
                run_id=run.run_id,
                error_type=type(error).__name__,
                message=str(error),
                record_identifier=str(mapping.id),
                details={
                    "source": "github",
                    "mode": "discovery",
                    "topic_id": str(mapping.topic_id),
                    "mapping_id": str(mapping.id),
                },
            )
        )
        self.session.commit()

    def _record_repository_error(
        self, run: IngestionRun, repository: GithubRepository, error: BaseException
    ) -> None:
        self.session.add(
            IngestionError(
                run_id=run.run_id,
                error_type=type(error).__name__,
                message=str(error),
                record_identifier=str(repository.github_repository_id),
                details={
                    "source": "github",
                    "mode": "snapshot",
                    "repository_id": str(repository.id),
                    "full_name": repository.full_name,
                },
            )
        )
        self.session.commit()

    def _finish_run(
        self,
        run: IngestionRun,
        status: IngestionStatus,
        accumulator: RunAccumulator,
        *,
        mode: str,
    ) -> dict[str, int | float | None]:
        data_quality = self._data_quality(accumulator, mode=mode)
        warning_fields = {
            "duplicate_ratio",
            "fork_ratio",
            "archived_ratio",
            "failed_mappings",
            "snapshot_failure_count",
            "missing_snapshot_count",
            "rate_limit_pause_count",
        }
        for name, value in data_quality.items():
            numeric = float(value or 0)
            self.session.add(
                DataQualityCheck(
                    run_id=run.run_id,
                    name=f"github_{name}",
                    status=(
                        QualityStatus.WARNING
                        if name in warning_fields and numeric > 0
                        else QualityStatus.PASSED
                    ),
                    observed={"value": value},
                    expected={"minimum": 0},
                    details={"source": "github", "mode": mode},
                )
            )
        run.status = status
        run.finished_at = self._utc(self._now())
        run.records_requested = accumulator.requests_sent
        run.records_received = accumulator.repositories_received
        run.records_inserted = (
            accumulator.new_repositories if mode == "discovery" else accumulator.snapshots_created
        )
        run.records_updated = accumulator.existing_repositories if mode == "discovery" else 0
        run.records_skipped = accumulator.unchanged_observations
        run.error_count = accumulator.errors
        run.metadata_ = {
            **run.metadata_,
            "raw_payloads_preserved": accumulator.raw_payloads,
            "topic_matches_added": accumulator.topic_matches_added,
            "data_quality": data_quality,
        }
        self.session.commit()
        logger.info(
            "github_run_finished",
            source="github",
            mode=mode,
            run_id=str(run.run_id),
            status=status.value,
            requests=accumulator.requests_sent,
            errors=accumulator.errors,
        )
        return data_quality

    def _data_quality(
        self, accumulator: RunAccumulator, *, mode: str
    ) -> dict[str, int | float | None]:
        duplicate_count = max(
            0, accumulator.repositories_received - len(accumulator.repository_ids)
        )
        received = accumulator.repositories_received
        return {
            "discovery_query_count": (
                sum(len(item.get("queries", [])) for item in accumulator.planned_queries)
                if mode == "discovery"
                else 0
            ),
            "candidate_repo_count": received,
            "unique_repo_count": len(accumulator.repository_ids),
            "tracked_repo_count": self._tracked_count(),
            "fork_count": accumulator.fork_count,
            "archived_count": accumulator.archived_count,
            "duplicate_ratio": duplicate_count / received if received else 0.0,
            "fork_ratio": accumulator.fork_count / received if received else 0.0,
            "archived_ratio": accumulator.archived_count / received if received else 0.0,
            "snapshot_due_count": accumulator.repositories_due,
            "snapshot_success_count": accumulator.snapshots_created,
            "snapshot_304_count": accumulator.responses_304,
            "snapshot_failure_count": accumulator.failed_items,
            "stale_repo_count": self._stale_repository_count(),
            "missing_snapshot_count": max(
                0,
                accumulator.repositories_due
                - accumulator.snapshots_created
                - accumulator.unchanged_observations,
            ),
            "rate_limit_pause_count": accumulator.rate_limit_pauses,
            "failed_mappings": accumulator.failed_items if mode == "discovery" else 0,
            "mapping_without_results": 0,
        }

    def _tracked_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count(func.distinct(GithubTopicRepositoryMatch.repository_id))).where(
                    GithubTopicRepositoryMatch.tracking_state == GithubTrackingState.TRACKED
                )
            )
            or 0
        )

    def _stale_repository_count(self) -> int:
        cutoff = self._utc(self._now()) - timedelta(hours=self.settings.github_snapshot_due_hours)
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(GithubRepository)
                .outerjoin(GithubRepositoryPollState)
                .where(
                    or_(
                        GithubRepositoryPollState.last_snapshot_at.is_(None),
                        GithubRepositoryPollState.last_snapshot_at < cutoff,
                    )
                )
            )
            or 0
        )

    def _summary(
        self,
        *,
        mode: Literal["dry_run", "discovery", "snapshot"],
        run: IngestionRun | None,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        accumulator: RunAccumulator,
        data_quality: dict[str, int | float | None],
        client: GithubClient | None,
    ) -> GithubRunSummary:
        return GithubRunSummary(
            mode=mode,
            run_id=run.run_id if run is not None else None,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            auth_configured=self.settings.github_token is not None,
            topics_considered=accumulator.topics_considered,
            mappings_executed=accumulator.mappings_executed,
            requests_sent=accumulator.requests_sent,
            raw_payloads_preserved=accumulator.raw_payloads,
            repositories_received=accumulator.repositories_received,
            unique_repositories=len(accumulator.repository_ids),
            new_repositories=accumulator.new_repositories,
            existing_repositories=accumulator.existing_repositories,
            topic_matches_added=accumulator.topic_matches_added,
            fork_count=accumulator.fork_count,
            archived_count=accumulator.archived_count,
            repositories_due=accumulator.repositories_due,
            responses_200=accumulator.responses_200,
            responses_304=accumulator.responses_304,
            responses_404=accumulator.responses_404,
            rate_limited_responses=accumulator.rate_limited_responses,
            snapshots_created=accumulator.snapshots_created,
            unchanged_observations=accumulator.unchanged_observations,
            failed_items=accumulator.failed_items,
            rate_limit_pauses=accumulator.rate_limit_pauses,
            errors=accumulator.errors,
            planned_queries=accumulator.planned_queries,
            data_quality=data_quality,
            rate_budgets=self._rate_budgets(client),
        )

    @staticmethod
    def _terminal_status(accumulator: RunAccumulator) -> IngestionStatus:
        return IngestionStatus.PARTIAL if accumulator.errors else IngestionStatus.SUCCEEDED

    def _tracking_state(self, repository: Any) -> GithubTrackingState:
        if repository.archived or repository.disabled:
            return GithubTrackingState.CANDIDATE
        if repository.is_fork and not self.settings.github_track_forks:
            return GithubTrackingState.CANDIDATE
        return GithubTrackingState.TRACKED

    def _effective_query(self, query: str) -> str:
        qualifiers = [query]
        if "is:public" not in query.casefold():
            qualifiers.append("is:public")
        if not self.settings.github_track_forks and "fork:" not in query.casefold():
            qualifiers.append("fork:false")
        return " ".join(qualifiers)

    def _runtime_exceeded(self, started_at: datetime) -> bool:
        elapsed = self._utc(self._now()) - started_at
        return elapsed >= timedelta(minutes=self.settings.github_max_runtime_minutes)

    @staticmethod
    def _rate_budgets(client: GithubClient | None) -> dict[str, dict[str, Any]]:
        if client is None:
            return {}
        return {
            resource: budget.model_dump(mode="json")
            for resource in ("search", "core")
            if (budget := client.rate_limits.budget(resource)) is not None
        }

    @staticmethod
    def _header(headers: dict[str, str], name: str) -> str | None:
        return next((value for key, value in headers.items() if key.casefold() == name), None)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("GitHub service time must be timezone-aware")
        return value.astimezone(UTC)
