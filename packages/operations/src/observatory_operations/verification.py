"""Read-only acceptance helpers for real cross-day and scheduler evidence."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from collector_core import DataIntegrityError, LocalRawStore
from github_collector import GithubQueryService
from observatory_db.github_models import (
    GithubRepositoryPollState,
    GithubRepositorySnapshot,
    GithubSnapshotMethod,
    GithubTopicRepositoryMatch,
)
from observatory_db.models import IngestionRun, IngestionStatus, Source, Topic
from observatory_operations.coverage import MissingObservationDetector
from observatory_operations.integrity import RawIntegrityVerifier
from signal_observatory_config import Settings


class GithubCrossDayVerifier:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.integrity = RawIntegrityVerifier(session, settings.raw_data_path)
        self.raw_store = LocalRawStore(settings.raw_data_path)

    def verify(self) -> dict[str, Any]:
        snapshots = list(
            self.session.scalars(
                select(GithubRepositorySnapshot)
                .options(selectinload(GithubRepositorySnapshot.raw_response))
                .order_by(
                    GithubRepositorySnapshot.repository_id,
                    GithubRepositorySnapshot.observation_date,
                )
            ).all()
        )
        dates = sorted({snapshot.observation_date for snapshot in snapshots})
        by_repository: dict[UUID, list[GithubRepositorySnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            by_repository[snapshot.repository_id].append(snapshot)
        cross_day = {
            repository_id: rows for repository_id, rows in by_repository.items() if len(rows) >= 2
        }
        changed = unchanged = 0
        integrity_failures: list[str] = []
        poll_inconsistencies: list[str] = []
        fabricated_dates: list[str] = []
        for repository_id, rows in by_repository.items():
            for snapshot in rows:
                if snapshot.observation_date != snapshot.observed_at.astimezone(UTC).date():
                    fabricated_dates.append(str(snapshot.id))
                reason = self._snapshot_raw_mismatch(snapshot)
                if reason:
                    integrity_failures.append(f"{snapshot.id}: {reason}")
            for previous, current in zip(rows, rows[1:], strict=False):
                if self._signature(previous) == self._signature(current):
                    unchanged += 1
                else:
                    changed += 1
            poll = self.session.scalar(
                select(GithubRepositoryPollState).where(
                    GithubRepositoryPollState.repository_id == repository_id
                )
            )
            latest = rows[-1]
            if poll is None or poll.last_snapshot_at != latest.observed_at:
                poll_inconsistencies.append(str(repository_id))

        delta_failures = self._verify_topic_deltas()
        missing_dates = MissingObservationDetector.between(dates)
        if len(dates) < 2 or not cross_day:
            status = "pending"
            exit_code = 1
            message = "Only one real UTC observation date exists. No data was modified."
        elif integrity_failures or poll_inconsistencies or fabricated_dates or delta_failures:
            status = "failed"
            exit_code = 2
            message = "Persisted cross-day evidence is inconsistent. No data was modified."
        else:
            status = "passed"
            exit_code = 0
            message = "Real cross-day Snapshot evidence is internally consistent."
        return {
            "status": status,
            "exit_code": exit_code,
            "message": message,
            "observation_dates": [day.isoformat() for day in dates],
            "observation_date_count": len(dates),
            "repositories_with_multiple_dates": len(cross_day),
            "changed_transitions": changed,
            "unchanged_transitions": unchanged,
            "missing_intermediate_dates": [day.isoformat() for day in missing_dates],
            "snapshot_raw_mismatches": integrity_failures,
            "fabricated_date_mismatches": fabricated_dates,
            "delta_mismatches": delta_failures,
            "poll_state_inconsistencies": poll_inconsistencies,
            "modified_records": 0,
        }

    def _snapshot_raw_mismatch(self, snapshot: GithubRepositorySnapshot) -> str | None:
        if snapshot.observation_method != GithubSnapshotMethod.FULL_200:
            return None
        raw = snapshot.raw_response
        path = self.integrity.resolve_path(raw.raw_path, "github")
        try:
            record = self.raw_store.load(path)
            if record.sha256 != raw.payload_checksum:
                return "DB and Raw metadata checksums differ"
            payload = json.loads(self.raw_store.read(record))
        except (OSError, KeyError, TypeError, ValueError, DataIntegrityError) as error:
            return str(error)
        comparisons = {
            "full_name": snapshot.full_name,
            "stargazers_count": snapshot.stargazers_count,
            "forks_count": snapshot.forks_count,
            "open_issues_count": snapshot.open_issues_count,
            "subscribers_count": snapshot.subscribers_count,
            "size": snapshot.size_kb,
        }
        mismatched = [key for key, expected in comparisons.items() if payload.get(key) != expected]
        return (
            f"Snapshot differs from immutable Raw fields: {', '.join(mismatched)}"
            if mismatched
            else None
        )

    def _verify_topic_deltas(self) -> list[str]:
        failures: list[str] = []
        service = GithubQueryService(self.session, self.settings)
        topic_slugs = list(
            self.session.scalars(
                select(Topic.slug)
                .join(GithubTopicRepositoryMatch, GithubTopicRepositoryMatch.topic_id == Topic.id)
                .join(
                    GithubRepositorySnapshot,
                    GithubRepositorySnapshot.repository_id
                    == GithubTopicRepositoryMatch.repository_id,
                )
                .distinct()
                .order_by(Topic.slug)
            ).all()
        )
        for slug in topic_slugs:
            development = service.development(slug, limit=100000)
            if development is None:
                failures.append(f"{slug}: development projection missing")
                continue
            repositories = development["top_repositories"]
            summary = development["summary"]
            observed_repositories = [
                repository
                for repository in repositories
                if repository["latest_snapshot_at"] is not None
            ]
            all_have_previous = bool(observed_repositories) and all(
                repository["stars_delta"] is not None and repository["forks_delta"] is not None
                for repository in observed_repositories
            )
            expected_stars = (
                sum(int(repository["stars_delta"]) for repository in observed_repositories)
                if all_have_previous
                else None
            )
            expected_forks = (
                sum(int(repository["forks_delta"]) for repository in observed_repositories)
                if all_have_previous
                else None
            )
            actual_stars = summary["stars_delta_since_previous_snapshot"]
            actual_forks = summary["forks_delta_since_previous_snapshot"]
            if actual_stars != expected_stars:
                failures.append(f"{slug}: star delta mismatch")
            if actual_forks != expected_forks:
                failures.append(f"{slug}: fork delta mismatch")
        return failures

    @staticmethod
    def _signature(snapshot: GithubRepositorySnapshot) -> tuple[Any, ...]:
        return (
            snapshot.stargazers_count,
            snapshot.forks_count,
            snapshot.open_issues_count,
            snapshot.subscribers_count,
            snapshot.size_kb,
            snapshot.pushed_at,
            snapshot.archived,
            snapshot.disabled,
        )


class ArxivSoakVerifier:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.now = (now or datetime.now(UTC)).astimezone(UTC)

    def verify(self, *, days: int = 7) -> dict[str, Any]:
        if days < 1 or days > 90:
            raise ValueError("soak days must be between 1 and 90")
        source = self.session.scalar(select(Source).where(Source.name == "arxiv"))
        runs: list[IngestionRun] = []
        if source is not None:
            all_runs = list(
                self.session.scalars(
                    select(IngestionRun)
                    .where(IngestionRun.source_id == source.id)
                    .order_by(IngestionRun.started_at)
                ).all()
            )
            runs = [
                run
                for run in all_runs
                if run.metadata_.get("mode") == "incremental"
                and run.metadata_.get("trigger") == "scheduled"
            ]
        if not runs:
            return {
                "status": "pending",
                "exit_code": 1,
                "days_required": days,
                "expected_scheduled_windows": days,
                "actual_scheduled_runs": 0,
                "successful": 0,
                "partial": 0,
                "failed": 0,
                "missing": 0,
                "remaining_future_windows": days,
                "duplicate_scheduling": 0,
                "cursor_anomalies": 0,
                "message": "No scheduler-tagged arXiv run exists yet. No data was modified.",
                "modified_records": 0,
            }

        first_day = runs[0].started_at.astimezone(UTC).date()
        expected_days = [first_day + timedelta(days=index) for index in range(days)]
        schedule_time = self._schedule_time(self.settings.arxiv_schedule)
        due_days = [
            day
            for day in expected_days
            if datetime.combine(day, schedule_time, tzinfo=UTC) <= self.now
        ]
        counts = Counter(run.started_at.astimezone(UTC).date() for run in runs)
        missing = [day for day in due_days if counts[day] == 0]
        duplicates = sum(max(0, counts[day] - 1) for day in expected_days)
        selected = [run for run in runs if run.started_at.astimezone(UTC).date() in expected_days]
        status_counts = Counter(run.status.value for run in selected)
        cursor_anomalies = sum(
            1
            for run in selected
            if run.finished_at is None or run.status == IngestionStatus.RUNNING
        )
        complete = len({run.started_at.astimezone(UTC).date() for run in selected}) >= days
        if missing or duplicates or cursor_anomalies:
            status = "failed"
            exit_code = 2
            message = "The scheduler soak contains missing, duplicate, or unfinished windows."
        elif complete:
            status = "passed"
            exit_code = 0
            message = "The required scheduler windows are present; partial runs remain visible."
        else:
            status = "pending"
            exit_code = 1
            message = "The scheduler soak is still accumulating real elapsed-time windows."
        return {
            "status": status,
            "exit_code": exit_code,
            "days_required": days,
            "window_start": expected_days[0],
            "window_end": expected_days[-1],
            "expected_scheduled_windows": days,
            "actual_scheduled_runs": len(selected),
            "successful": status_counts[IngestionStatus.SUCCEEDED.value],
            "partial": status_counts[IngestionStatus.PARTIAL.value],
            "failed": status_counts[IngestionStatus.FAILED.value],
            "missing": len(missing),
            "missing_dates": [day.isoformat() for day in missing],
            "remaining_future_windows": max(0, days - len(due_days)),
            "duplicate_scheduling": duplicates,
            "cursor_anomalies": cursor_anomalies,
            "message": message,
            "modified_records": 0,
        }

    @staticmethod
    def _schedule_time(schedule: str) -> time:
        parts = schedule.split()
        if len(parts) != 5:
            raise ValueError("ARXIV_SCHEDULE must be a five-field UTC cron")
        return time(hour=int(parts[1]), minute=int(parts[0]), tzinfo=UTC)
