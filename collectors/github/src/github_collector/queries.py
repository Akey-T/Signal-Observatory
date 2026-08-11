"""Read-only GitHub collector status, samples, and Topic Developer observations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from observatory_db.github_models import (
    GithubDiscoveryState,
    GithubRawResponse,
    GithubRepository,
    GithubRepositorySnapshot,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import IngestionRun, IngestionStatus, Source, Topic, TopicSourceMapping
from signal_observatory_config import Settings


class GithubQueryService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or Settings()

    def status(self) -> dict[str, Any]:
        source = self.session.scalar(select(Source).where(Source.name == "github"))
        auth_configured = self.settings.github_token is not None
        if source is None:
            return self._empty_status(auth_configured=auth_configured)
        runs = self._runs(source.id)
        last_run = runs[0] if runs else None
        snapshot_runs = [run for run in runs if run.metadata_.get("mode") == "snapshot"]
        last_snapshot_run = snapshot_runs[0] if snapshot_runs else None
        successful_snapshot_run = next(
            (run for run in snapshot_runs if run.status == IngestionStatus.SUCCEEDED), None
        )
        last_discovery_at = self.session.scalar(
            select(func.max(GithubDiscoveryState.last_successful_at))
        )
        last_snapshot_at = self.session.scalar(
            select(func.max(GithubRepositorySnapshot.observed_at))
        )
        tracked = self._tracked_count()
        snapshot_count = int(
            self.session.scalar(select(func.count()).select_from(GithubRepositorySnapshot)) or 0
        )
        if not auth_configured and self.settings.github_require_auth:
            collector_state = "not_configured"
        elif successful_snapshot_run is None:
            collector_state = "not_initialized"
        elif last_snapshot_run is not None and last_snapshot_run.status in {
            IngestionStatus.PARTIAL,
            IngestionStatus.FAILED,
        }:
            collector_state = "degraded"
        else:
            collector_state = "healthy"
        return {
            "source": "github",
            "enabled": source.is_active,
            "auth_configured": auth_configured,
            "collector_state": collector_state,
            "last_run_at": last_run.finished_at if last_run is not None else None,
            "last_run_status": last_run.status.value if last_run is not None else None,
            "last_discovery_at": last_discovery_at,
            "last_snapshot_at": last_snapshot_at,
            "last_successful_snapshot_at": (
                successful_snapshot_run.finished_at if successful_snapshot_run is not None else None
            ),
            "tracked_repositories": tracked,
            "snapshots": snapshot_count,
            "errors_last_run": last_run.error_count if last_run is not None else 0,
            "search_rate": self._latest_rate("search"),
            "core_rate": self._latest_rate("core"),
        }

    def sample(self, topic_slug: str, *, limit: int) -> list[dict[str, Any]]:
        statement = (
            select(GithubTopicRepositoryMatch, GithubRepository)
            .join(GithubRepository, GithubRepository.id == GithubTopicRepositoryMatch.repository_id)
            .join(Topic, Topic.id == GithubTopicRepositoryMatch.topic_id)
            .where(Topic.slug == topic_slug)
            .order_by(
                GithubTopicRepositoryMatch.discovery_rank,
                GithubRepository.github_repository_id,
            )
            .limit(limit)
        )
        return [
            {
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
                "description": repository.description,
                "language": repository.language,
                "is_fork": repository.is_fork,
                "archived": repository.archived,
                "disabled": repository.disabled,
                "matched_query": match.matched_query,
                "mapping_id": str(match.source_mapping_id),
                "discovery_rank": match.discovery_rank,
                "tracking_state": match.tracking_state.value,
                "discovery_run_id": str(match.last_ingestion_run_id),
                "raw_checksum": self._match_raw_checksum(match),
            }
            for match, repository in self.session.execute(statement).all()
        ]

    def topic_exists(self, topic_slug: str) -> bool:
        return self.session.scalar(select(Topic.id).where(Topic.slug == topic_slug)) is not None

    def development(self, topic_slug: str, *, limit: int) -> dict[str, Any] | None:
        topic = self.session.scalar(select(Topic).where(Topic.slug == topic_slug))
        if topic is None:
            return None
        mappings = self.session.scalars(
            select(TopicSourceMapping)
            .join(Source, Source.id == TopicSourceMapping.source_id)
            .where(
                TopicSourceMapping.topic_id == topic.id,
                TopicSourceMapping.enabled.is_(True),
                Source.name == "github",
            )
        ).all()
        mapping_ids = {mapping.id for mapping in mappings}
        repositories = self._topic_repositories(topic.id)
        latest_and_previous = {
            repository.id: self._latest_two_snapshots(repository.id) for repository in repositories
        }
        latest = {
            repository_id: snapshots[0]
            for repository_id, snapshots in latest_and_previous.items()
            if snapshots
        }
        previous = {
            repository_id: snapshots[1]
            for repository_id, snapshots in latest_and_previous.items()
            if len(snapshots) > 1
        }
        discovery_succeeded = (
            (
                self.session.scalar(
                    select(func.count())
                    .select_from(GithubDiscoveryState)
                    .where(
                        GithubDiscoveryState.source_mapping_id.in_(mapping_ids),
                        GithubDiscoveryState.last_successful_at.is_not(None),
                    )
                )
                or 0
            )
            > 0
            if mapping_ids
            else False
        )
        status = self.status()
        state = self._topic_state(
            has_mapping=bool(mappings),
            auth_configured=bool(status["auth_configured"]),
            discovery_succeeded=discovery_succeeded,
            repositories=bool(repositories),
            snapshots=bool(latest),
            source_state=str(status["collector_state"]),
        )
        latest_at = max((snapshot.observed_at for snapshot in latest.values()), default=None)
        all_have_previous = bool(latest) and len(previous) == len(latest)
        stars_delta = (
            sum(
                latest[repository_id].stargazers_count - previous[repository_id].stargazers_count
                for repository_id in latest
            )
            if all_have_previous
            else None
        )
        forks_delta = (
            sum(
                latest[repository_id].forks_count - previous[repository_id].forks_count
                for repository_id in latest
            )
            if all_have_previous
            else None
        )
        previous_at = (
            min(snapshot.observed_at for snapshot in previous.values())
            if all_have_previous
            else None
        )
        cutoff = datetime.now(UTC) - timedelta(days=30)
        top_repositories = sorted(
            repositories,
            key=lambda repository: (
                latest[repository.id].stargazers_count if repository.id in latest else -1,
                repository.github_repository_id,
            ),
            reverse=True,
        )[:limit]
        return {
            "topic": {"slug": topic.slug, "canonical_name": topic.canonical_name},
            "source": "github",
            "state": state,
            "last_snapshot_at": latest_at,
            "last_successful_snapshot_at": status["last_successful_snapshot_at"],
            "collector_error": (
                "latest GitHub snapshot run was not fully successful"
                if state == "degraded"
                else None
            ),
            "summary": {
                "repositories_tracked": len(repositories),
                "stars_total": sum(snapshot.stargazers_count for snapshot in latest.values()),
                "forks_total": sum(snapshot.forks_count for snapshot in latest.values()),
                "repositories_pushed_30d": sum(
                    snapshot.pushed_at is not None and snapshot.pushed_at >= cutoff
                    for snapshot in latest.values()
                ),
                "stars_delta_since_previous_snapshot": stars_delta,
                "forks_delta_since_previous_snapshot": forks_delta,
                "previous_snapshot_at": previous_at,
                "latest_snapshot_at": latest_at,
            },
            "top_repositories": [
                self._development_repository(topic.id, repository, latest_and_previous)
                for repository in top_repositories
            ],
        }

    def _development_repository(
        self,
        topic_id: UUID,
        repository: GithubRepository,
        snapshots_by_repository: dict[UUID, list[GithubRepositorySnapshot]],
    ) -> dict[str, Any]:
        snapshots = snapshots_by_repository[repository.id]
        latest = snapshots[0] if snapshots else None
        previous = snapshots[1] if len(snapshots) > 1 else None
        matches = self.session.scalars(
            select(GithubTopicRepositoryMatch)
            .where(
                GithubTopicRepositoryMatch.topic_id == topic_id,
                GithubTopicRepositoryMatch.repository_id == repository.id,
            )
            .order_by(GithubTopicRepositoryMatch.discovery_rank)
        ).all()
        return {
            "github_repository_id": repository.github_repository_id,
            "full_name": repository.full_name,
            "description": repository.description,
            "html_url": repository.html_url,
            "language": latest.language if latest is not None else repository.language,
            "stars": latest.stargazers_count if latest is not None else None,
            "forks": latest.forks_count if latest is not None else None,
            "pushed_at": latest.pushed_at if latest is not None else repository.pushed_at_github,
            "archived": repository.archived,
            "disabled": repository.disabled,
            "latest_snapshot_at": latest.observed_at if latest is not None else None,
            "previous_snapshot_at": previous.observed_at if previous is not None else None,
            "stars_delta": (
                latest.stargazers_count - previous.stargazers_count
                if latest is not None and previous is not None
                else None
            ),
            "forks_delta": (
                latest.forks_count - previous.forks_count
                if latest is not None and previous is not None
                else None
            ),
            "match_evidence": [
                {
                    "matched_query": match.matched_query,
                    "source_mapping_id": str(match.source_mapping_id),
                    "discovery_rank": match.discovery_rank,
                    "discovery_run_id": str(match.last_ingestion_run_id),
                    "raw_checksum": self._match_raw_checksum(match),
                }
                for match in matches
            ],
        }

    def _topic_repositories(self, topic_id: UUID) -> list[GithubRepository]:
        return list(
            self.session.scalars(
                select(GithubRepository)
                .join(GithubTopicRepositoryMatch)
                .where(
                    GithubTopicRepositoryMatch.topic_id == topic_id,
                    GithubTopicRepositoryMatch.tracking_state == GithubTrackingState.TRACKED,
                )
                .order_by(GithubRepository.github_repository_id)
            )
            .unique()
            .all()
        )

    def _latest_two_snapshots(self, repository_id: UUID) -> list[GithubRepositorySnapshot]:
        return list(
            self.session.scalars(
                select(GithubRepositorySnapshot)
                .where(GithubRepositorySnapshot.repository_id == repository_id)
                .order_by(GithubRepositorySnapshot.observed_at.desc())
                .limit(2)
            ).all()
        )

    def _runs(self, source_id: UUID) -> list[IngestionRun]:
        return list(
            self.session.scalars(
                select(IngestionRun)
                .where(IngestionRun.source_id == source_id)
                .order_by(IngestionRun.started_at.desc())
            ).all()
        )

    def _latest_rate(self, resource: str) -> dict[str, Any] | None:
        raw = self.session.scalar(
            select(GithubRawResponse)
            .where(GithubRawResponse.rate_resource == resource)
            .order_by(GithubRawResponse.observed_at.desc())
            .limit(1)
        )
        if raw is None:
            return None
        return {
            "limit": raw.rate_limit,
            "remaining": raw.rate_remaining,
            "reset_at": raw.rate_reset_at,
            "resource": raw.rate_resource,
        }

    def _match_raw_checksum(self, match: GithubTopicRepositoryMatch) -> str | None:
        raw_id = match.metadata_.get("raw_response_id")
        if raw_id is None:
            return None
        try:
            raw = self.session.get(GithubRawResponse, UUID(str(raw_id)))
        except ValueError:
            return None
        return raw.payload_checksum if raw is not None else None

    def _tracked_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count(func.distinct(GithubTopicRepositoryMatch.repository_id))).where(
                    GithubTopicRepositoryMatch.tracking_state == GithubTrackingState.TRACKED
                )
            )
            or 0
        )

    @staticmethod
    def _topic_state(
        *,
        has_mapping: bool,
        auth_configured: bool,
        discovery_succeeded: bool,
        repositories: bool,
        snapshots: bool,
        source_state: str,
    ) -> str:
        if not has_mapping or not auth_configured:
            return "not_configured"
        if not discovery_succeeded:
            return "not_initialized"
        if not repositories:
            return "live"
        if not snapshots:
            return "not_initialized"
        return "degraded" if source_state == "degraded" else "live"

    @staticmethod
    def _empty_status(*, auth_configured: bool) -> dict[str, Any]:
        return {
            "source": "github",
            "enabled": False,
            "auth_configured": auth_configured,
            "collector_state": "not_configured",
            "last_run_at": None,
            "last_run_status": None,
            "last_discovery_at": None,
            "last_snapshot_at": None,
            "last_successful_snapshot_at": None,
            "tracked_repositories": 0,
            "snapshots": 0,
            "errors_last_run": 0,
            "search_rate": None,
            "core_rate": None,
        }
