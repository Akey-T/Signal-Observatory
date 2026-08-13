"""Deterministic coverage derivation and read models."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivTopicMatch,
)
from observatory_db.base import utc_now
from observatory_db.coverage_models import (
    CoverageStatus,
    CoverageStrategy,
    TopicSourceCoverage,
)
from observatory_db.github_models import (
    GithubDiscoveryState,
    GithubOperationStatus,
    GithubRepositoryPollState,
    GithubRepositorySnapshot,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import Source, Topic, TopicSourceMapping, TopicStatus
from observatory_operations.models import freshness_state
from signal_observatory_config import Settings

COVERAGE_DERIVATION_VERSION = "coverage-v1"
SUPPORTED_SOURCES = frozenset({"arxiv", "github"})


@dataclass(frozen=True, slots=True)
class CoverageProjection:
    topic_id: UUID
    source_id: UUID
    coverage_status: CoverageStatus
    coverage_strategy: CoverageStrategy
    coverage_start: date | None
    coverage_end: date | None
    target_start: date | None
    target_end: date | None
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    last_successful_run_at: datetime | None
    observation_count: int
    expected_observation_count: int | None
    missing_observation_count: int
    partial_reason: str | None
    metadata: dict[str, Any]


class MissingObservationDetector:
    """Find absent UTC dates without manufacturing replacement observations."""

    @staticmethod
    def between(observation_dates: Iterable[date]) -> tuple[date, ...]:
        observed = sorted(set(observation_dates))
        if len(observed) < 2:
            return ()
        expected: list[date] = []
        cursor = observed[0]
        while cursor <= observed[-1]:
            expected.append(cursor)
            cursor += timedelta(days=1)
        observed_set = set(observed)
        return tuple(day for day in expected if day not in observed_set)


class CoverageDeriver:
    """Rebuild the projection exclusively from persisted source facts."""

    def __init__(self, session: Session, *, now: datetime | None = None) -> None:
        self.session = session
        self.now = (now or utc_now()).astimezone(UTC)

    def rebuild(self) -> dict[str, Any]:
        mappings = list(
            self.session.scalars(
                select(TopicSourceMapping)
                .join(TopicSourceMapping.topic)
                .join(TopicSourceMapping.source)
                .where(
                    TopicSourceMapping.enabled.is_(True),
                    Topic.status == TopicStatus.ACTIVE,
                    Source.name.in_(SUPPORTED_SOURCES),
                )
                .options(
                    selectinload(TopicSourceMapping.topic),
                    selectinload(TopicSourceMapping.source),
                )
                .order_by(Topic.slug, Source.name, TopicSourceMapping.id)
            ).all()
        )
        groups: dict[tuple[UUID, UUID], list[TopicSourceMapping]] = defaultdict(list)
        for mapping in mappings:
            groups[(mapping.topic_id, mapping.source_id)].append(mapping)

        projections: list[CoverageProjection] = []
        for group in groups.values():
            source_name = group[0].source.name
            if source_name == "arxiv":
                projections.append(self._derive_arxiv(group))
            elif source_name == "github":
                projections.append(self._derive_github(group))

        handled_source_ids = set(
            self.session.scalars(select(Source.id).where(Source.name.in_(SUPPORTED_SOURCES))).all()
        )
        existing = {
            (item.topic_id, item.source_id): item
            for item in self.session.scalars(
                select(TopicSourceCoverage).where(
                    TopicSourceCoverage.source_id.in_(handled_source_ids)
                )
            ).all()
        }
        expected_keys: set[tuple[UUID, UUID]] = set()
        created = updated = unchanged = 0
        for projection in projections:
            key = (projection.topic_id, projection.source_id)
            expected_keys.add(key)
            row = existing.get(key)
            values = self._projection_values(projection)
            if row is None:
                self.session.add(
                    TopicSourceCoverage(
                        **values,
                        derived_at=self.now,
                        derivation_version=COVERAGE_DERIVATION_VERSION,
                    )
                )
                created += 1
                continue
            if self._projection_changed(row, values):
                for name, value in values.items():
                    setattr(row, name, value)
                row.derived_at = self.now
                row.derivation_version = COVERAGE_DERIVATION_VERSION
                updated += 1
            else:
                unchanged += 1

        deleted = 0
        for key, row in existing.items():
            if key not in expected_keys:
                self.session.delete(row)
                deleted += 1
        self.session.commit()
        return {
            "derivation_version": COVERAGE_DERIVATION_VERSION,
            "derived_at": self.now,
            "projections": len(projections),
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "deleted": deleted,
        }

    def _derive_arxiv(self, mappings: Sequence[TopicSourceMapping]) -> CoverageProjection:
        mapping_ids = [mapping.id for mapping in mappings]
        topic_id = mappings[0].topic_id
        source_id = mappings[0].source_id
        cursors = list(
            self.session.scalars(
                select(ArxivCollectionCursor)
                .where(ArxivCollectionCursor.source_mapping_id.in_(mapping_ids))
                .order_by(
                    ArxivCollectionCursor.source_mapping_id,
                    ArxivCollectionCursor.window_from,
                    ArxivCollectionCursor.cursor_key,
                )
            ).all()
        )
        backfill = [cursor for cursor in cursors if cursor.mode == "backfill"]
        successful = [
            cursor
            for cursor in backfill
            if cursor.status == ArxivCursorStatus.SUCCEEDED
            and cursor.window_from is not None
            and cursor.window_until is not None
        ]
        unresolved = [cursor for cursor in backfill if cursor.status != ArxivCursorStatus.SUCCEEDED]
        gaps = self._cursor_gaps(backfill)
        target_start = self._min_date(cursor.window_from for cursor in backfill)
        target_end = self._max_date(cursor.window_until for cursor in backfill)
        coverage_start = self._min_date(cursor.window_from for cursor in successful)
        coverage_end = self._max_date(cursor.window_until for cursor in successful)

        observation_count = int(
            self.session.scalar(
                select(func.count(func.distinct(ArxivTopicMatch.paper_id))).where(
                    ArxivTopicMatch.topic_id == topic_id,
                    ArxivTopicMatch.source_mapping_id.in_(mapping_ids),
                )
            )
            or 0
        )
        first_observed, last_observed = self.session.execute(
            select(
                func.min(ArxivTopicMatch.first_matched_at),
                func.max(ArxivTopicMatch.last_matched_at),
            ).where(
                ArxivTopicMatch.topic_id == topic_id,
                ArxivTopicMatch.source_mapping_id.in_(mapping_ids),
            )
        ).one()
        last_successful = self._max_datetime(cursor.last_successful_run_at for cursor in cursors)

        reasons: list[str] = []
        if not backfill:
            status = CoverageStatus.UNKNOWN
            reasons.append("No persisted historical backfill window defines the target coverage.")
        elif unresolved or gaps:
            status = CoverageStatus.PARTIAL
            if unresolved:
                states = sorted({cursor.status.value for cursor in unresolved})
                reasons.append(
                    f"{len(unresolved)} historical cursor window(s) unresolved: "
                    f"{', '.join(states)}."
                )
            if gaps:
                reasons.append(f"{len(gaps)} gap(s) exist between persisted target windows.")
        elif observation_count == 0:
            status = CoverageStatus.EMPTY
        else:
            status = CoverageStatus.COMPLETE

        partial_mapping_count = 0
        mapping_details: list[dict[str, Any]] = []
        for mapping in mappings:
            mapping_cursors = [
                cursor for cursor in backfill if cursor.source_mapping_id == mapping.id
            ]
            mapping_unresolved = [
                cursor for cursor in mapping_cursors if cursor.status != ArxivCursorStatus.SUCCEEDED
            ]
            mapping_partial = bool(mapping_unresolved)
            partial_mapping_count += int(mapping_partial)
            mapping_details.append(
                {
                    "mapping_id": str(mapping.id),
                    "window_count": len(mapping_cursors),
                    "unresolved_window_count": len(mapping_unresolved),
                    "status": "partial" if mapping_partial else "complete",
                }
            )

        return CoverageProjection(
            topic_id=topic_id,
            source_id=source_id,
            coverage_status=status,
            coverage_strategy=CoverageStrategy.HISTORICAL_BACKFILL,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            target_start=target_start,
            target_end=target_end,
            first_observed_at=first_observed,
            last_observed_at=last_observed,
            last_successful_run_at=last_successful,
            observation_count=observation_count,
            expected_observation_count=None,
            missing_observation_count=len(unresolved) + len(gaps),
            partial_reason=" ".join(reasons) or None,
            metadata={
                "observation_unit": "papers",
                "completeness_basis": "persisted_backfill_cursor_windows",
                "backfill_window_count": len(backfill),
                "successful_window_count": len(successful),
                "partial_mapping_count": partial_mapping_count,
                "mapping_details": mapping_details,
                "window_gaps": gaps,
            },
        )

    def _derive_github(self, mappings: Sequence[TopicSourceMapping]) -> CoverageProjection:
        mapping_ids = [mapping.id for mapping in mappings]
        topic_id = mappings[0].topic_id
        source_id = mappings[0].source_id
        tracked_repository_ids = list(
            self.session.scalars(
                select(GithubTopicRepositoryMatch.repository_id)
                .where(
                    GithubTopicRepositoryMatch.topic_id == topic_id,
                    GithubTopicRepositoryMatch.source_mapping_id.in_(mapping_ids),
                    GithubTopicRepositoryMatch.tracking_state == GithubTrackingState.TRACKED,
                )
                .distinct()
            ).all()
        )
        observation_dates: list[date] = []
        first_observed: datetime | None = None
        last_observed: datetime | None = None
        last_successful: datetime | None = None
        if tracked_repository_ids:
            observation_dates = list(
                self.session.scalars(
                    select(GithubRepositorySnapshot.observation_date)
                    .where(GithubRepositorySnapshot.repository_id.in_(tracked_repository_ids))
                    .distinct()
                    .order_by(GithubRepositorySnapshot.observation_date)
                ).all()
            )
            first_observed, last_observed = self.session.execute(
                select(
                    func.min(GithubRepositorySnapshot.observed_at),
                    func.max(GithubRepositorySnapshot.observed_at),
                ).where(GithubRepositorySnapshot.repository_id.in_(tracked_repository_ids))
            ).one()
            last_successful = self.session.scalar(
                select(func.max(GithubRepositoryPollState.last_successful_at)).where(
                    GithubRepositoryPollState.repository_id.in_(tracked_repository_ids)
                )
            )

        discovery_states = list(
            self.session.scalars(
                select(GithubDiscoveryState).where(
                    GithubDiscoveryState.source_mapping_id.in_(mapping_ids)
                )
            ).all()
        )
        if last_successful is None:
            last_successful = self._max_datetime(
                state.last_successful_at for state in discovery_states
            )

        missing_dates = MissingObservationDetector.between(observation_dates)
        if observation_dates:
            status = CoverageStatus.FORWARD_ONLY
            reason = None
        elif (
            discovery_states
            and all(state.status == GithubOperationStatus.SUCCEEDED for state in discovery_states)
            and not tracked_repository_ids
        ):
            status = CoverageStatus.EMPTY
            reason = None
        else:
            status = CoverageStatus.UNKNOWN
            reason = (
                "Tracked repositories have not produced a persisted Snapshot."
                if tracked_repository_ids
                else "No successful GitHub observation is available for this Topic."
            )

        expected = (
            (observation_dates[-1] - observation_dates[0]).days + 1 if observation_dates else None
        )
        return CoverageProjection(
            topic_id=topic_id,
            source_id=source_id,
            coverage_status=status,
            coverage_strategy=CoverageStrategy.FORWARD_SNAPSHOT,
            coverage_start=observation_dates[0] if observation_dates else None,
            coverage_end=observation_dates[-1] if observation_dates else None,
            target_start=None,
            target_end=None,
            first_observed_at=first_observed,
            last_observed_at=last_observed,
            last_successful_run_at=last_successful,
            observation_count=len(observation_dates),
            expected_observation_count=expected,
            missing_observation_count=len(missing_dates),
            partial_reason=reason,
            metadata={
                "observation_unit": "utc_snapshot_dates",
                "historical_backfill": "unavailable_by_design",
                "tracked_repository_count": len(tracked_repository_ids),
                "missing_dates": [day.isoformat() for day in missing_dates],
                "partial_mapping_count": 0,
                "mapping_details": [
                    {
                        "mapping_id": str(mapping.id),
                        "status": next(
                            (
                                state.status.value
                                for state in discovery_states
                                if state.source_mapping_id == mapping.id
                            ),
                            "not_initialized",
                        ),
                    }
                    for mapping in mappings
                ],
            },
        )

    @staticmethod
    def _cursor_gaps(cursors: Sequence[ArxivCollectionCursor]) -> list[dict[str, str]]:
        windows = sorted(
            (
                (cursor.window_from, cursor.window_until)
                for cursor in cursors
                if cursor.window_from is not None and cursor.window_until is not None
            ),
            key=lambda item: item[0],
        )
        if not windows:
            return []
        gaps: list[dict[str, str]] = []
        current_end = windows[0][1]
        for window_from, window_until in windows[1:]:
            if window_from > current_end:
                gaps.append(
                    {
                        "from": current_end.isoformat(),
                        "until": window_from.isoformat(),
                    }
                )
            current_end = max(current_end, window_until)
        return gaps

    @staticmethod
    def _min_date(values: Iterable[datetime | None]) -> date | None:
        concrete = [value.astimezone(UTC).date() for value in values if value is not None]
        return min(concrete, default=None)

    @staticmethod
    def _max_date(values: Iterable[datetime | None]) -> date | None:
        concrete = [value.astimezone(UTC).date() for value in values if value is not None]
        return max(concrete, default=None)

    @staticmethod
    def _max_datetime(values: Iterable[datetime | None]) -> datetime | None:
        concrete = [value for value in values if value is not None]
        return max(concrete, default=None)

    @staticmethod
    def _projection_values(projection: CoverageProjection) -> dict[str, Any]:
        return {
            "topic_id": projection.topic_id,
            "source_id": projection.source_id,
            "coverage_status": projection.coverage_status,
            "coverage_strategy": projection.coverage_strategy,
            "coverage_start": projection.coverage_start,
            "coverage_end": projection.coverage_end,
            "target_start": projection.target_start,
            "target_end": projection.target_end,
            "first_observed_at": projection.first_observed_at,
            "last_observed_at": projection.last_observed_at,
            "last_successful_run_at": projection.last_successful_run_at,
            "observation_count": projection.observation_count,
            "expected_observation_count": projection.expected_observation_count,
            "missing_observation_count": projection.missing_observation_count,
            "partial_reason": projection.partial_reason,
            "metadata_": projection.metadata,
        }

    @staticmethod
    def _projection_changed(row: TopicSourceCoverage, values: dict[str, Any]) -> bool:
        if row.derivation_version != COVERAGE_DERIVATION_VERSION:
            return True
        return any(getattr(row, name) != value for name, value in values.items())


class CoverageQueryService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or Settings()
        self.now = (now or utc_now()).astimezone(UTC)

    def list(
        self,
        *,
        source: str | None = None,
        status: CoverageStatus | None = None,
        topic: str | None = None,
        stale: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        statement = (
            select(TopicSourceCoverage, Topic, Source)
            .join(Topic, Topic.id == TopicSourceCoverage.topic_id)
            .join(Source, Source.id == TopicSourceCoverage.source_id)
        )
        if source:
            statement = statement.where(Source.name == source)
        if status:
            statement = statement.where(TopicSourceCoverage.coverage_status == status)
        if topic:
            statement = statement.where(Topic.slug == topic)
        rows = list(
            self.session.execute(statement.order_by(Topic.canonical_name, Source.name)).all()
        )
        items = [
            self._item(coverage, topic_row, source_row) for coverage, topic_row, source_row in rows
        ]
        if stale is not None:
            items = [
                item for item in items if (item["freshness"] in {"stale", "very_stale"}) is stale
            ]
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "generated_at": self.now,
            "derivation_version": COVERAGE_DERIVATION_VERSION,
        }

    def topic(self, slug: str) -> dict[str, Any] | None:
        topic = self.session.scalar(select(Topic).where(Topic.slug == slug))
        if topic is None:
            return None
        projected = self.list(topic=slug, limit=20)["items"]
        by_source = {str(item["source"]): item for item in projected}
        channels = []
        for channel, source, label in (
            ("research", "arxiv", "Research"),
            ("developer", "github", "Developer"),
            ("community", "hacker_news", "Community"),
            ("public", "wikipedia", "Public"),
        ):
            coverage = by_source.get(source)
            channels.append(
                {
                    "channel": channel,
                    "label": label,
                    "source": source,
                    "collection_state": "collecting" if coverage is not None else "not_started",
                    "coverage": coverage,
                }
            )
        return {
            "topic": {"slug": topic.slug, "canonical_name": topic.canonical_name},
            "channels": channels,
            "generated_at": self.now,
        }

    def summary(self) -> dict[str, int]:
        counts = {member.value: 0 for member in CoverageStatus}
        for state, count in self.session.execute(
            select(TopicSourceCoverage.coverage_status, func.count()).group_by(
                TopicSourceCoverage.coverage_status
            )
        ):
            counts[state.value] = int(count)
        return counts

    def _item(
        self,
        coverage: TopicSourceCoverage,
        topic: Topic,
        source: Source,
    ) -> dict[str, Any]:
        fresh_hours, very_stale_hours = self._thresholds(source.name)
        freshness = freshness_state(
            coverage.last_successful_run_at or coverage.last_observed_at,
            now=self.now,
            fresh_hours=fresh_hours,
            very_stale_hours=very_stale_hours,
        )
        return {
            "topic": {
                "id": str(topic.id),
                "slug": topic.slug,
                "canonical_name": topic.canonical_name,
            },
            "source": source.name,
            "coverage_status": coverage.coverage_status.value,
            "coverage_strategy": coverage.coverage_strategy.value,
            "coverage_start": coverage.coverage_start,
            "coverage_end": coverage.coverage_end,
            "target_start": coverage.target_start,
            "target_end": coverage.target_end,
            "first_observed_at": coverage.first_observed_at,
            "last_observed_at": coverage.last_observed_at,
            "last_successful_run_at": coverage.last_successful_run_at,
            "observation_count": coverage.observation_count,
            "expected_observation_count": coverage.expected_observation_count,
            "missing_observation_count": coverage.missing_observation_count,
            "partial_reason": coverage.partial_reason,
            "freshness": freshness.value,
            "derived_at": coverage.derived_at,
            "derivation_version": coverage.derivation_version,
            "metadata": coverage.metadata_,
        }

    def _thresholds(self, source: str) -> tuple[int, int]:
        if source == "arxiv":
            return (
                self.settings.arxiv_freshness_fresh_hours,
                self.settings.arxiv_freshness_very_stale_hours,
            )
        if source == "github":
            return (
                self.settings.github_freshness_fresh_hours,
                self.settings.github_freshness_very_stale_hours,
            )
        return (36, 72)
