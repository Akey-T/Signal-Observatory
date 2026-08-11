"""Idempotent GitHub Silver persistence with immutable Raw and daily snapshots."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from collector_core.raw_store import RawRecord
from github_collector.models import GithubHTTPResponse, GithubRepositoryData
from observatory_db.github_models import (
    GithubMatchMethod,
    GithubRawResponse,
    GithubRepository,
    GithubRepositoryPollState,
    GithubRepositorySnapshot,
    GithubSnapshotMethod,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import IngestionRun, TopicSourceMapping


class GithubPersistence:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_raw_response(
        self,
        *,
        response: GithubHTTPResponse,
        run: IngestionRun,
        raw_record: RawRecord,
        mapping: TopicSourceMapping | None = None,
        repository: GithubRepository | None = None,
    ) -> GithubRawResponse:
        existing = self.session.scalar(
            select(GithubRawResponse).where(GithubRawResponse.raw_path == str(raw_record.directory))
        )
        if existing is not None:
            return existing
        rate = response.rate_limit
        raw_response = GithubRawResponse(
            ingestion_run_id=run.run_id,
            repository_id=repository.id if repository is not None else None,
            topic_id=mapping.topic_id if mapping is not None else None,
            source_mapping_id=mapping.id if mapping is not None else None,
            endpoint_type=response.request.endpoint_type,
            raw_path=str(raw_record.directory),
            payload_checksum=raw_record.sha256,
            observed_at=response.requested_at,
            request_url_hash=hashlib.sha256(response.request.url.encode("utf-8")).hexdigest(),
            query_parameters=dict(response.request.query_parameters),
            http_status=response.status_code,
            etag=self._header(response.headers, "etag"),
            last_modified=self._header(response.headers, "last-modified"),
            rate_limit=rate.limit,
            rate_remaining=rate.remaining,
            rate_reset_at=rate.reset_at,
            rate_resource=rate.resource,
            retry_after_seconds=rate.retry_after_seconds,
            response_headers=response.headers,
            request_metadata={
                "collector_version": raw_record.collector_version,
                "schema_version": raw_record.schema_version,
                "attempt": response.attempts,
                "final_url_changed": response.final_url != response.request.url,
            },
        )
        self.session.add(raw_response)
        self.session.flush()
        return raw_response

    def record_parse_error(self, raw_response: GithubRawResponse, error: BaseException) -> None:
        raw_response.parse_error = f"{type(error).__name__}: {error}"
        self.session.flush()

    def upsert_repository(
        self, data: GithubRepositoryData, *, observed_at: datetime
    ) -> tuple[GithubRepository, bool]:
        timestamp = self._utc(observed_at)
        repository = self.session.scalar(
            select(GithubRepository).where(
                GithubRepository.github_repository_id == data.github_repository_id
            )
        )
        created = repository is None
        values = self._repository_values(data)
        if repository is None:
            repository = GithubRepository(
                github_repository_id=data.github_repository_id,
                first_observed_at=timestamp,
                last_observed_at=timestamp,
                **values,
            )
            self.session.add(repository)
        else:
            for field, value in values.items():
                setattr(repository, field, value)
            repository.last_observed_at = max(repository.last_observed_at, timestamp)
        self.session.flush()
        return repository, created

    def upsert_match(
        self,
        *,
        repository: GithubRepository,
        mapping: TopicSourceMapping,
        query: str,
        rank: int,
        run: IngestionRun,
        observed_at: datetime,
        tracking_state: GithubTrackingState,
        raw_response: GithubRawResponse,
    ) -> bool:
        match = self.session.scalar(
            select(GithubTopicRepositoryMatch).where(
                GithubTopicRepositoryMatch.topic_id == mapping.topic_id,
                GithubTopicRepositoryMatch.repository_id == repository.id,
                GithubTopicRepositoryMatch.source_mapping_id == mapping.id,
                GithubTopicRepositoryMatch.matched_query == query,
            )
        )
        timestamp = self._utc(observed_at)
        if match is None:
            self.session.add(
                GithubTopicRepositoryMatch(
                    topic_id=mapping.topic_id,
                    repository_id=repository.id,
                    source_mapping_id=mapping.id,
                    matched_query=query,
                    match_method=GithubMatchMethod.GITHUB_REPOSITORY_SEARCH,
                    discovery_rank=rank,
                    first_discovered_at=timestamp,
                    last_discovered_at=timestamp,
                    first_ingestion_run_id=run.run_id,
                    last_ingestion_run_id=run.run_id,
                    tracking_state=tracking_state,
                    metadata_={"raw_response_id": str(raw_response.id)},
                )
            )
            self.session.flush()
            return True
        match.last_discovered_at = max(match.last_discovered_at, timestamp)
        match.last_ingestion_run_id = run.run_id
        match.discovery_rank = min(match.discovery_rank, rank)
        if match.tracking_state is not GithubTrackingState.IGNORED:
            match.tracking_state = tracking_state
        match.metadata_ = {"raw_response_id": str(raw_response.id)}
        self.session.flush()
        return False

    def create_full_snapshot(
        self,
        *,
        repository: GithubRepository,
        data: GithubRepositoryData,
        run: IngestionRun,
        raw_response: GithubRawResponse,
        observed_at: datetime,
        etag: str | None,
    ) -> tuple[GithubRepositorySnapshot, bool]:
        timestamp = self._utc(observed_at)
        existing = self._daily_snapshot(repository.id, timestamp.date())
        if existing is not None:
            self.mark_poll_success(
                repository=repository,
                observed_at=timestamp,
                snapshot=existing,
                raw_response=raw_response,
            )
            return existing, False
        snapshot = GithubRepositorySnapshot(
            repository_id=repository.id,
            observed_at=timestamp,
            observation_date=timestamp.date(),
            full_name=data.full_name,
            stargazers_count=data.stargazers_count,
            forks_count=data.forks_count,
            open_issues_count=data.open_issues_count,
            subscribers_count=data.subscribers_count,
            size_kb=data.size_kb,
            language=data.language,
            archived=data.archived,
            disabled=data.disabled,
            default_branch=data.default_branch,
            pushed_at=data.pushed_at_github,
            updated_at_github=data.updated_at_github,
            topics=list(data.topics),
            license_spdx=data.license_spdx,
            ingestion_run_id=run.run_id,
            raw_response_id=raw_response.id,
            observation_method=GithubSnapshotMethod.FULL_200,
            etag=etag,
        )
        self.session.add(snapshot)
        self.session.flush()
        self.mark_poll_success(
            repository=repository,
            observed_at=timestamp,
            snapshot=snapshot,
            raw_response=raw_response,
        )
        return snapshot, True

    def create_unchanged_snapshot(
        self,
        *,
        repository: GithubRepository,
        run: IngestionRun,
        raw_response: GithubRawResponse,
        observed_at: datetime,
    ) -> tuple[GithubRepositorySnapshot, bool]:
        timestamp = self._utc(observed_at)
        existing = self._daily_snapshot(repository.id, timestamp.date())
        if existing is not None:
            self.mark_poll_success(
                repository=repository,
                observed_at=timestamp,
                snapshot=existing,
                raw_response=raw_response,
            )
            return existing, False
        previous = self.session.scalar(
            select(GithubRepositorySnapshot)
            .where(GithubRepositorySnapshot.repository_id == repository.id)
            .order_by(GithubRepositorySnapshot.observed_at.desc())
            .limit(1)
        )
        if previous is None:
            raise ValueError("GitHub returned 304 before a baseline snapshot exists")
        snapshot = GithubRepositorySnapshot(
            repository_id=repository.id,
            observed_at=timestamp,
            observation_date=timestamp.date(),
            full_name=repository.full_name,
            stargazers_count=previous.stargazers_count,
            forks_count=previous.forks_count,
            open_issues_count=previous.open_issues_count,
            subscribers_count=previous.subscribers_count,
            size_kb=previous.size_kb,
            language=previous.language,
            archived=previous.archived,
            disabled=previous.disabled,
            default_branch=previous.default_branch,
            pushed_at=previous.pushed_at,
            updated_at_github=previous.updated_at_github,
            topics=list(previous.topics),
            license_spdx=previous.license_spdx,
            ingestion_run_id=run.run_id,
            raw_response_id=raw_response.id,
            observation_method=GithubSnapshotMethod.CONDITIONAL_304,
            etag=raw_response.etag or previous.etag,
        )
        self.session.add(snapshot)
        self.session.flush()
        self.mark_poll_success(
            repository=repository,
            observed_at=timestamp,
            snapshot=snapshot,
            raw_response=raw_response,
        )
        return snapshot, True

    def mark_poll_success(
        self,
        *,
        repository: GithubRepository,
        observed_at: datetime,
        snapshot: GithubRepositorySnapshot,
        raw_response: GithubRawResponse,
    ) -> GithubRepositoryPollState:
        state = self._poll_state(repository)
        state.last_checked_at = self._utc(observed_at)
        state.last_successful_at = self._utc(observed_at)
        state.last_snapshot_at = snapshot.observed_at
        state.etag = raw_response.etag or snapshot.etag
        state.last_modified = raw_response.last_modified
        state.last_status = raw_response.http_status
        state.consecutive_failures = 0
        state.next_eligible_at = None
        state.last_error = None
        self.session.flush()
        return state

    def mark_poll_failure(
        self,
        *,
        repository: GithubRepository,
        observed_at: datetime,
        status: int | None,
        error: BaseException,
        next_eligible_at: datetime | None = None,
    ) -> GithubRepositoryPollState:
        state = self._poll_state(repository)
        state.last_checked_at = self._utc(observed_at)
        state.last_status = status
        state.consecutive_failures += 1
        state.next_eligible_at = next_eligible_at
        state.last_error = f"{type(error).__name__}: {error}"
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

    def _daily_snapshot(
        self, repository_id: UUID, observation_date: date
    ) -> GithubRepositorySnapshot | None:
        return self.session.scalar(
            select(GithubRepositorySnapshot).where(
                GithubRepositorySnapshot.repository_id == repository_id,
                GithubRepositorySnapshot.observation_date == observation_date,
            )
        )

    @staticmethod
    def _repository_values(data: GithubRepositoryData) -> dict[str, object]:
        return {
            "node_id": data.node_id,
            "owner_login": data.owner_login,
            "name": data.name,
            "full_name": data.full_name,
            "html_url": data.html_url,
            "api_url": data.api_url,
            "description": data.description,
            "homepage": data.homepage,
            "language": data.language,
            "default_branch": data.default_branch,
            "is_fork": data.is_fork,
            "fork_parent_github_id": data.fork_parent_github_id,
            "archived": data.archived,
            "disabled": data.disabled,
            "visibility": data.visibility,
            "created_at_github": data.created_at_github,
            "updated_at_github": data.updated_at_github,
            "pushed_at_github": data.pushed_at_github,
            "metadata_": data.metadata,
        }

    @staticmethod
    def _header(headers: dict[str, str], name: str) -> str | None:
        return next((value for key, value in headers.items() if key.casefold() == name), None)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("GitHub persistence timestamps must be timezone-aware")
        return value.astimezone(UTC)
