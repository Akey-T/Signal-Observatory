"""Unified collector health derived from persisted operational facts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivPaper,
    ArxivRawResponse,
)
from observatory_db.base import utc_now
from observatory_db.coverage_models import CoverageStatus, TopicSourceCoverage
from observatory_db.github_models import (
    GithubDiscoveryState,
    GithubOperationStatus,
    GithubRawResponse,
    GithubRepository,
    GithubRepositorySnapshot,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import (
    IngestionError,
    IngestionRun,
    IngestionStatus,
    Source,
    Topic,
    TopicSourceMapping,
    TopicStatus,
)
from observatory_operations.coverage import CoverageQueryService
from observatory_operations.models import (
    CollectorState,
    FreshnessState,
    OverallState,
    freshness_state,
)
from signal_observatory_config import Settings
from topic_registry.queries import TopicQueryService

SOURCE_PRESENTATION = {
    "arxiv": {"channel": "research", "label": "Research", "display_name": "arXiv"},
    "github": {"channel": "developer", "label": "Developer", "display_name": "GitHub"},
    "hacker_news": {
        "channel": "community",
        "label": "Community",
        "display_name": "Hacker News",
    },
    "wikipedia": {"channel": "public", "label": "Public", "display_name": "Wikipedia"},
}


class OperationsService:
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

    def overview(self) -> dict[str, Any]:
        sources = [self.source(name) for name in SOURCE_PRESENTATION]
        coverage_summary = CoverageQueryService(self.session, self.settings, now=self.now).summary()
        data_quality = self._data_quality()
        active = [source for source in sources if source["implemented"] and source["enabled"]]
        overall = self._overall_state(
            active,
            coverage_summary,
            missing_snapshot_dates=data_quality["missing_snapshot_dates"],
        )
        return {
            "overall_state": overall.value,
            "explanation": self._overall_explanation(sources, coverage_summary),
            "registry": self._registry(),
            "sources": sources,
            "coverage_summary": coverage_summary,
            "data_quality": data_quality,
            "generated_at": self.now,
        }

    @staticmethod
    def _overall_state(
        active: list[dict[str, Any]],
        coverage_summary: dict[str, int],
        *,
        missing_snapshot_dates: int,
    ) -> OverallState:
        states = {str(source["collector_state"]) for source in active}
        if not active:
            return OverallState.NOT_STARTED
        if CollectorState.FAILED.value in states:
            return OverallState.FAILED
        if (
            any(state != CollectorState.HEALTHY.value for state in states)
            or coverage_summary[CoverageStatus.PARTIAL.value] > 0
            or coverage_summary[CoverageStatus.UNKNOWN.value] > 0
            or missing_snapshot_dates > 0
        ):
            return OverallState.DEGRADED
        return OverallState.HEALTHY

    def source(self, name: str) -> dict[str, Any]:
        if name not in SOURCE_PRESENTATION:
            raise ValueError(f"unsupported operations source: {name}")
        if name == "arxiv":
            return self._arxiv()
        if name == "github":
            return self._github()
        return self._not_started(name)

    def _arxiv(self) -> dict[str, Any]:
        source, active_mappings = self._source_and_mapping_count("arxiv")
        latest, latest_successful = self._latest_runs(source)
        failed_mappings = int(
            self.session.scalar(
                select(func.count(func.distinct(ArxivCollectionCursor.source_mapping_id))).where(
                    ArxivCollectionCursor.status == ArxivCursorStatus.FAILED
                )
            )
            or 0
        )
        partial_mappings = int(
            self.session.scalar(
                select(func.count(func.distinct(ArxivCollectionCursor.source_mapping_id))).where(
                    ArxivCollectionCursor.status == ArxivCursorStatus.PARTIAL
                )
            )
            or 0
        )
        stale_before = self.now - timedelta(hours=self.settings.arxiv_freshness_fresh_hours)
        stale_mappings = int(
            self.session.scalar(
                select(func.count(func.distinct(ArxivCollectionCursor.source_mapping_id))).where(
                    ArxivCollectionCursor.mode == "incremental",
                    ArxivCollectionCursor.last_successful_run_at.is_not(None),
                    ArxivCollectionCursor.last_successful_run_at < stale_before,
                )
            )
            or 0
        )
        raw_last_run = self._raw_count(ArxivRawResponse, latest)
        fresh_at = latest_successful.finished_at if latest_successful is not None else None
        freshness = freshness_state(
            fresh_at,
            now=self.now,
            fresh_hours=self.settings.arxiv_freshness_fresh_hours,
            very_stale_hours=self.settings.arxiv_freshness_very_stale_hours,
        )
        state = self._collector_state(
            source=source,
            active_mappings=active_mappings,
            latest=latest,
            freshness=freshness,
            configured=True,
        )
        return {
            **SOURCE_PRESENTATION["arxiv"],
            "source": "arxiv",
            "implemented": True,
            "enabled": bool(source and source.is_active and active_mappings),
            "collector_state": state.value,
            "last_run_at": latest.started_at if latest else None,
            "last_successful_run_at": latest_successful.finished_at if latest_successful else None,
            "latest_run_status": latest.status.value if latest else None,
            "active_mappings": active_mappings,
            "failed_mappings": failed_mappings,
            "partial_mappings": partial_mappings,
            "stale_mappings": stale_mappings,
            "errors_last_run": latest.error_count if latest else 0,
            "raw_responses_last_run": raw_last_run,
            "freshness": freshness.value,
            "details": {
                "papers_observed": int(
                    self.session.scalar(select(func.count()).select_from(ArxivPaper)) or 0
                ),
                "freshness_threshold_hours": self.settings.arxiv_freshness_fresh_hours,
                "very_stale_threshold_hours": (self.settings.arxiv_freshness_very_stale_hours),
            },
        }

    def _github(self) -> dict[str, Any]:
        source, active_mappings = self._source_and_mapping_count("github")
        latest, latest_successful = self._latest_runs(source)
        failed_mappings = int(
            self.session.scalar(
                select(func.count())
                .select_from(GithubDiscoveryState)
                .where(GithubDiscoveryState.status == GithubOperationStatus.FAILED)
            )
            or 0
        )
        partial_mappings = int(
            self.session.scalar(
                select(func.count())
                .select_from(GithubDiscoveryState)
                .where(GithubDiscoveryState.status == GithubOperationStatus.PARTIAL)
            )
            or 0
        )
        latest_snapshot_at = self.session.scalar(
            select(func.max(GithubRepositorySnapshot.observed_at))
        )
        freshness = freshness_state(
            latest_snapshot_at,
            now=self.now,
            fresh_hours=self.settings.github_freshness_fresh_hours,
            very_stale_hours=self.settings.github_freshness_very_stale_hours,
        )
        state = self._collector_state(
            source=source,
            active_mappings=active_mappings,
            latest=latest,
            freshness=freshness,
            configured=self.settings.github_token is not None,
        )
        tracked = int(
            self.session.scalar(
                select(func.count(func.distinct(GithubTopicRepositoryMatch.repository_id))).where(
                    GithubTopicRepositoryMatch.tracking_state == GithubTrackingState.TRACKED
                )
            )
            or 0
        )
        snapshot_dates = int(
            self.session.scalar(
                select(func.count(func.distinct(GithubRepositorySnapshot.observation_date)))
            )
            or 0
        )
        return {
            **SOURCE_PRESENTATION["github"],
            "source": "github",
            "implemented": True,
            "enabled": bool(source and source.is_active and active_mappings),
            "collector_state": state.value,
            "last_run_at": latest.started_at if latest else None,
            "last_successful_run_at": latest_successful.finished_at if latest_successful else None,
            "latest_run_status": latest.status.value if latest else None,
            "active_mappings": active_mappings,
            "failed_mappings": failed_mappings,
            "partial_mappings": partial_mappings,
            "stale_mappings": 0,
            "errors_last_run": latest.error_count if latest else 0,
            "raw_responses_last_run": self._raw_count(GithubRawResponse, latest),
            "freshness": freshness.value,
            "details": {
                "auth_configured": self.settings.github_token is not None,
                "tracked_repositories": tracked,
                "repositories_known": int(
                    self.session.scalar(select(func.count()).select_from(GithubRepository)) or 0
                ),
                "snapshot_dates": snapshot_dates,
                "latest_snapshot": (
                    latest_snapshot_at.astimezone(UTC).date() if latest_snapshot_at else None
                ),
                "freshness_threshold_hours": self.settings.github_freshness_fresh_hours,
                "very_stale_threshold_hours": (self.settings.github_freshness_very_stale_hours),
            },
        }

    def _not_started(self, name: str) -> dict[str, Any]:
        source, active_mappings = self._source_and_mapping_count(name)
        return {
            **SOURCE_PRESENTATION[name],
            "source": name,
            "implemented": False,
            "enabled": bool(source and source.is_active and active_mappings),
            "collector_state": CollectorState.NOT_INITIALIZED.value,
            "last_run_at": None,
            "last_successful_run_at": None,
            "latest_run_status": None,
            "active_mappings": active_mappings,
            "failed_mappings": 0,
            "partial_mappings": 0,
            "stale_mappings": 0,
            "errors_last_run": 0,
            "raw_responses_last_run": 0,
            "freshness": FreshnessState.UNKNOWN.value,
            "details": {"collection_state": "not_started"},
        }

    def _source_and_mapping_count(self, name: str) -> tuple[Source | None, int]:
        source = self.session.scalar(select(Source).where(Source.name == name))
        count = int(
            self.session.scalar(
                select(func.count())
                .select_from(TopicSourceMapping)
                .join(TopicSourceMapping.source)
                .join(TopicSourceMapping.topic)
                .where(
                    Source.name == name,
                    TopicSourceMapping.enabled.is_(True),
                    Topic.status == TopicStatus.ACTIVE,
                )
            )
            or 0
        )
        return source, count

    def _latest_runs(
        self, source: Source | None
    ) -> tuple[IngestionRun | None, IngestionRun | None]:
        if source is None:
            return None, None
        latest = self.session.scalar(
            select(IngestionRun)
            .where(IngestionRun.source_id == source.id)
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        successful = self.session.scalar(
            select(IngestionRun)
            .where(
                IngestionRun.source_id == source.id,
                IngestionRun.status == IngestionStatus.SUCCEEDED,
            )
            .order_by(IngestionRun.finished_at.desc())
            .limit(1)
        )
        return latest, successful

    @staticmethod
    def _collector_state(
        *,
        source: Source | None,
        active_mappings: int,
        latest: IngestionRun | None,
        freshness: FreshnessState,
        configured: bool,
    ) -> CollectorState:
        if source is None or not configured or active_mappings == 0:
            return CollectorState.NOT_CONFIGURED
        if not source.is_active:
            return CollectorState.PAUSED
        if latest is None:
            return CollectorState.NOT_INITIALIZED
        if latest.status == IngestionStatus.FAILED:
            return CollectorState.FAILED
        if latest.status == IngestionStatus.PARTIAL:
            return CollectorState.DEGRADED
        if freshness in {FreshnessState.STALE, FreshnessState.VERY_STALE}:
            return CollectorState.DEGRADED
        return CollectorState.HEALTHY

    def _data_quality(self) -> dict[str, Any]:
        since = self.now - timedelta(hours=24)
        errors = int(
            self.session.scalar(
                select(func.count())
                .select_from(IngestionError)
                .where(IngestionError.occurred_at >= since)
            )
            or 0
        )
        coverage_rows = list(self.session.scalars(select(TopicSourceCoverage)).all())
        partial_mappings = sum(
            int(row.metadata_.get("partial_mapping_count", 0)) for row in coverage_rows
        )
        missing_dates = sum(
            row.missing_observation_count
            for row in coverage_rows
            if row.coverage_strategy.value == "forward_snapshot"
        )
        stale_before = self.now - timedelta(hours=self.settings.arxiv_freshness_fresh_hours)
        stale_cursors = int(
            self.session.scalar(
                select(func.count())
                .select_from(ArxivCollectionCursor)
                .where(
                    ArxivCollectionCursor.mode == "incremental",
                    (
                        ArxivCollectionCursor.status.in_(
                            [ArxivCursorStatus.PARTIAL, ArxivCursorStatus.FAILED]
                        )
                        | (
                            ArxivCollectionCursor.last_successful_run_at.is_not(None)
                            & (ArxivCollectionCursor.last_successful_run_at < stale_before)
                        )
                    ),
                )
            )
            or 0
        )
        registry = TopicQueryService(self.session).registry_status()
        registry_warnings = registry["warnings"] if registry else 0
        assert isinstance(registry_warnings, int)
        return {
            "ingestion_errors_last_24h": errors,
            "partial_mappings": partial_mappings,
            "stale_cursors": stale_cursors,
            "missing_snapshot_dates": missing_dates,
            "raw_checksum_failures": None,
            "raw_integrity_state": "not_verified",
            "registry_warnings": registry_warnings,
        }

    def _registry(self) -> dict[str, Any]:
        registry = TopicQueryService(self.session).registry_status()
        if registry is None:
            return {"state": "not_initialized", "version": None, "warnings": 0}
        warnings = registry["warnings"]
        assert isinstance(warnings, int)
        return {
            "state": "healthy" if warnings == 0 else "degraded",
            "version": registry["version"],
            "warnings": warnings,
            "last_synced_at": registry["last_synced_at"],
        }

    def _raw_count(self, model: type[Any], latest: IngestionRun | None) -> int:
        if latest is None:
            return 0
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.ingestion_run_id == latest.run_id)
            )
            or 0
        )

    def _overall_explanation(
        self, sources: list[dict[str, Any]], coverage_summary: dict[str, int]
    ) -> str:
        research = next(source for source in sources if source["source"] == "arxiv")
        developer = next(source for source in sources if source["source"] == "github")
        parts = [
            f"Research is {str(research['collector_state']).replace('_', ' ')}",
            f"Developer is {str(developer['collector_state']).replace('_', ' ')}",
        ]
        if coverage_summary[CoverageStatus.PARTIAL.value]:
            parts.append(
                f"{coverage_summary[CoverageStatus.PARTIAL.value]} Topic-source coverage "
                "projection(s) are partial"
            )
        if coverage_summary[CoverageStatus.FORWARD_ONLY.value]:
            parts.append(
                f"{coverage_summary[CoverageStatus.FORWARD_ONLY.value]} GitHub projection(s) "
                "are accumulating forward-only history"
            )
        return ". ".join(parts) + "."
