"""Durable scheduler-window planning and terminal evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from observatory_db.models import SchedulerExecution, SchedulerExecutionStatus

PUNCTUALITY_CONTRACT = "scheduler-punctuality-v2"
DEFAULT_ON_TIME_THRESHOLD_SECONDS = 300


class SchedulerTimingState(StrEnum):
    ON_TIME = "on_time"
    LATE = "late"
    MISSED = "missed"
    INTERRUPTED = "interrupted"
    PENDING = "pending"


def scheduler_timing(
    execution: SchedulerExecution,
    *,
    now: datetime,
    threshold_seconds: int = DEFAULT_ON_TIME_THRESHOLD_SECONDS,
) -> tuple[SchedulerTimingState, float | None]:
    """Classify dispatch timing independently from the collector outcome."""

    observed_at = _utc(now)
    scheduled_at = _utc(execution.scheduled_at)
    if execution.status is SchedulerExecutionStatus.MISSED:
        return SchedulerTimingState.MISSED, None
    if execution.status is SchedulerExecutionStatus.INTERRUPTED:
        delay = _delay_seconds(execution.started_at, scheduled_at)
        return SchedulerTimingState.INTERRUPTED, delay
    if execution.started_at is None:
        if scheduled_at <= observed_at:
            return SchedulerTimingState.MISSED, None
        return SchedulerTimingState.PENDING, None
    delay = _delay_seconds(execution.started_at, scheduled_at)
    assert delay is not None
    state = (
        SchedulerTimingState.ON_TIME if delay <= threshold_seconds else SchedulerTimingState.LATE
    )
    return state, delay


def _delay_seconds(started_at: datetime | None, scheduled_at: datetime) -> float | None:
    if started_at is None:
        return None
    return round(max(0.0, (_utc(started_at) - scheduled_at).total_seconds()), 3)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler evidence timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _daily_schedule_time(schedule: str) -> time:
    parts = schedule.split()
    if len(parts) != 5 or parts[2:] != ["*", "*", "*"]:
        raise ValueError("punctuality verification requires a daily five-field UTC cron")
    try:
        minute, hour = int(parts[0]), int(parts[1])
    except ValueError as error:
        raise ValueError("scheduler minute and hour must be integers") from error
    if not 0 <= minute <= 59 or not 0 <= hour <= 23:
        raise ValueError("scheduler hour/minute is outside the valid range")
    return time(hour=hour, minute=minute, tzinfo=UTC)


def _latest_due_window(schedule: str, now: datetime) -> datetime:
    observed_at = _utc(now)
    schedule_time = _daily_schedule_time(schedule)
    candidate = datetime.combine(observed_at.date(), schedule_time, tzinfo=UTC)
    return candidate if candidate <= observed_at else candidate - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class ReconciledExecution:
    job_name: str
    source_name: str
    scheduled_at: datetime
    status: SchedulerExecutionStatus


class SchedulerLedger:
    """Persist plans before they are due and expose missed/interrupted windows after restart."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def leadership(self) -> Iterator[None]:
        """Allow one PostgreSQL scheduler host to reconcile and dispatch windows."""

        if self.engine.dialect.name != "postgresql":
            yield
            return
        with self.engine.connect() as connection:
            lock_id = 1_397_310_290
            acquired = bool(
                connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": lock_id},
                )
            )
            if not acquired:
                raise RuntimeError("another scheduler host owns the database leadership lock")
            try:
                yield
            finally:
                try:
                    connection.scalar(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": lock_id},
                    )
                except SQLAlchemyError:
                    connection.invalidate()

    def materialized_windows(self, job_name: str) -> tuple[datetime, ...]:
        """Return every known window so reconciliation can detect internal gaps."""

        with Session(self.engine) as session:
            values = tuple(
                session.scalars(
                    select(SchedulerExecution.scheduled_at)
                    .where(SchedulerExecution.job_name == job_name)
                    .order_by(SchedulerExecution.scheduled_at)
                )
                .unique()
                .all()
            )
        return tuple(self._utc(value) for value in values)

    def reconcile(self, job_name: str, *, now: datetime) -> tuple[ReconciledExecution, ...]:
        observed_at = self._utc(now)
        reconciled: list[ReconciledExecution] = []
        with Session(self.engine, expire_on_commit=False) as session:
            rows = list(
                session.scalars(
                    select(SchedulerExecution)
                    .where(
                        SchedulerExecution.job_name == job_name,
                        SchedulerExecution.status.in_(
                            (
                                SchedulerExecutionStatus.SCHEDULED,
                                SchedulerExecutionStatus.RUNNING,
                            )
                        ),
                    )
                    .order_by(SchedulerExecution.scheduled_at)
                ).all()
            )
            for row in rows:
                if row.status == SchedulerExecutionStatus.SCHEDULED:
                    if row.scheduled_at > observed_at:
                        continue
                    row.status = SchedulerExecutionStatus.MISSED
                    row.error_type = "worker_unavailable_at_due_time"
                else:
                    row.status = SchedulerExecutionStatus.INTERRUPTED
                    row.error_type = "worker_restarted_during_execution"
                row.finished_at = observed_at
                row.metadata_ = {**row.metadata_, "reconciled_at": observed_at.isoformat()}
                reconciled.append(
                    ReconciledExecution(
                        job_name=row.job_name,
                        source_name=row.source_name,
                        scheduled_at=row.scheduled_at,
                        status=row.status,
                    )
                )
            session.commit()
        return tuple(reconciled)

    def plan(
        self,
        job_name: str,
        source_name: str,
        scheduled_at: datetime,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Insert one plan atomically; return false when it already exists."""

        window = self._utc(scheduled_at)
        with Session(self.engine) as session:
            session.add(
                SchedulerExecution(
                    job_name=job_name,
                    source_name=source_name,
                    scheduled_at=window,
                    status=SchedulerExecutionStatus.SCHEDULED,
                    metadata_=metadata or {},
                )
            )
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(SchedulerExecution).where(
                        SchedulerExecution.job_name == job_name,
                        SchedulerExecution.scheduled_at == window,
                    )
                )
                if existing is None:
                    raise
                if existing.source_name != source_name:
                    raise RuntimeError(
                        "scheduler window already exists with a different source"
                    ) from None
                if metadata and existing.status is SchedulerExecutionStatus.SCHEDULED:
                    merged = dict(existing.metadata_)
                    for key, value in metadata.items():
                        merged.setdefault(key, value)
                    if merged != existing.metadata_:
                        existing.metadata_ = merged
                        session.commit()
                return False

    def start(self, job_name: str, scheduled_at: datetime, *, now: datetime) -> bool:
        window = self._utc(scheduled_at)
        started_at = self._utc(now)
        with Session(self.engine) as session:
            claimed = session.scalar(
                update(SchedulerExecution)
                .where(
                    SchedulerExecution.job_name == job_name,
                    SchedulerExecution.scheduled_at == window,
                    SchedulerExecution.status == SchedulerExecutionStatus.SCHEDULED,
                )
                .values(
                    status=SchedulerExecutionStatus.RUNNING,
                    started_at=started_at,
                    error_type=None,
                )
                .returning(SchedulerExecution.id)
            )
            session.commit()
        return claimed is not None

    def finish(
        self,
        job_name: str,
        scheduled_at: datetime,
        *,
        now: datetime,
        status: SchedulerExecutionStatus,
        error_type: str | None = None,
    ) -> None:
        if status not in {
            SchedulerExecutionStatus.SUCCEEDED,
            SchedulerExecutionStatus.PARTIAL,
            SchedulerExecutionStatus.FAILED,
        }:
            raise ValueError("scheduler finish status must be succeeded, partial, or failed")
        window = self._utc(scheduled_at)
        finished_at = self._utc(now)
        with Session(self.engine) as session:
            finished = session.scalar(
                update(SchedulerExecution)
                .where(
                    SchedulerExecution.job_name == job_name,
                    SchedulerExecution.scheduled_at == window,
                    SchedulerExecution.status == SchedulerExecutionStatus.RUNNING,
                )
                .values(
                    status=status,
                    finished_at=finished_at,
                    error_type=error_type,
                )
                .returning(SchedulerExecution.id)
            )
            if finished is None:
                session.rollback()
                raise RuntimeError("scheduler execution is not running")
            session.commit()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return _utc(value)


class SchedulerPunctualityVerifier:
    """Read-only continuity and post-contract punctuality evidence."""

    def __init__(
        self,
        session: Session,
        *,
        now: datetime | None = None,
        threshold_seconds: int = DEFAULT_ON_TIME_THRESHOLD_SECONDS,
    ) -> None:
        if threshold_seconds < 0:
            raise ValueError("punctuality threshold cannot be negative")
        self.session = session
        self.now = _utc(now or datetime.now(UTC))
        self.threshold_seconds = threshold_seconds

    def status(
        self,
        *,
        job_name: str,
        source_name: str,
        schedule: str,
        continuity_days: int = 7,
        qualification_windows: int = 3,
    ) -> dict[str, Any]:
        if continuity_days < 1 or qualification_windows < 1:
            raise ValueError("scheduler evidence windows must be positive")
        rows = list(
            self.session.scalars(
                select(SchedulerExecution)
                .where(SchedulerExecution.job_name == job_name)
                .order_by(SchedulerExecution.scheduled_at)
            ).all()
        )
        by_window: dict[datetime, list[SchedulerExecution]] = {}
        for row in rows:
            by_window.setdefault(_utc(row.scheduled_at), []).append(row)

        continuity_due = _latest_due_window(schedule, self.now)
        continuity_windows = [
            continuity_due - timedelta(days=index) for index in reversed(range(continuity_days))
        ]
        continuity_missing = [window for window in continuity_windows if window not in by_window]
        continuity_duplicates = sum(
            max(0, len(by_window.get(window, [])) - 1) for window in continuity_windows
        )
        source_mismatches = sum(
            row.source_name != source_name
            for window in continuity_windows
            for row in by_window.get(window, [])
        )
        continuity_bad = 0
        for window in continuity_windows:
            for row in by_window.get(window, []):
                timing, _delay = scheduler_timing(
                    row, now=self.now, threshold_seconds=self.threshold_seconds
                )
                if timing in {
                    SchedulerTimingState.MISSED,
                    SchedulerTimingState.INTERRUPTED,
                }:
                    continuity_bad += 1
        continuity_observed = continuity_days - len(continuity_missing)
        if not rows:
            continuity_state = "pending"
        elif continuity_missing or continuity_duplicates or continuity_bad or source_mismatches:
            continuity_state = "failed"
        elif continuity_observed == continuity_days:
            continuity_state = "passed"
        else:
            continuity_state = "pending"

        tagged = [
            row for row in rows if row.metadata_.get("punctuality_contract") == PUNCTUALITY_CONTRACT
        ]
        qualification_start = min((_utc(row.scheduled_at) for row in tagged), default=None)
        qualification_expected = (
            [qualification_start + timedelta(days=index) for index in range(qualification_windows)]
            if qualification_start is not None
            else []
        )
        due_qualification = [window for window in qualification_expected if window <= self.now]
        timing_counts: Counter[str] = Counter()
        qualification_missing: list[datetime] = []
        qualification_duplicates = 0
        completed = 0
        evidence: list[dict[str, Any]] = []
        terminal = {
            SchedulerExecutionStatus.SUCCEEDED,
            SchedulerExecutionStatus.PARTIAL,
            SchedulerExecutionStatus.FAILED,
            SchedulerExecutionStatus.MISSED,
            SchedulerExecutionStatus.INTERRUPTED,
        }
        for window in due_qualification:
            matching = [
                row
                for row in by_window.get(window, [])
                if row.metadata_.get("punctuality_contract") == PUNCTUALITY_CONTRACT
            ]
            if not matching:
                qualification_missing.append(window)
                continue
            qualification_duplicates += max(0, len(matching) - 1)
            for row in matching:
                timing, delay = scheduler_timing(
                    row, now=self.now, threshold_seconds=self.threshold_seconds
                )
                timing_counts[timing.value] += 1
                if row.status in terminal:
                    completed += 1
                evidence.append(self._row_payload(row, timing, delay))

        disqualifying = sum(
            timing_counts[state.value]
            for state in (
                SchedulerTimingState.LATE,
                SchedulerTimingState.MISSED,
                SchedulerTimingState.INTERRUPTED,
            )
        )
        if qualification_missing or qualification_duplicates or disqualifying:
            punctuality_state = "failed"
            exit_code = 2
            message = "Post-deployment punctuality evidence failed its timing contract."
        elif qualification_start is not None and completed >= qualification_windows:
            punctuality_state = "passed"
            exit_code = 0
            message = "Three real post-deployment windows met the on-time threshold."
        else:
            punctuality_state = "pending"
            exit_code = 1
            message = "Post-deployment punctuality qualification is still accumulating."

        latest = rows[-1] if rows else None
        latest_timing: SchedulerTimingState | None = None
        latest_delay: float | None = None
        if latest is not None:
            latest_timing, latest_delay = scheduler_timing(
                latest, now=self.now, threshold_seconds=self.threshold_seconds
            )
        next_window = None
        if qualification_start is None:
            today_due = _latest_due_window(schedule, self.now)
            next_window = today_due + timedelta(days=1)
            while any(
                row.metadata_.get("punctuality_contract") != PUNCTUALITY_CONTRACT
                for row in by_window.get(next_window, [])
            ):
                next_window += timedelta(days=1)
        elif len(due_qualification) < qualification_windows:
            next_window = qualification_expected[len(due_qualification)]

        return {
            "job_name": job_name,
            "source_name": source_name,
            "schedule": schedule,
            "on_time_threshold_seconds": self.threshold_seconds,
            "continuity_state": continuity_state,
            "continuity_days_required": continuity_days,
            "continuity_windows_observed": continuity_observed,
            "continuity_missing": [value.isoformat() for value in continuity_missing],
            "continuity_duplicates": continuity_duplicates,
            "continuity_missed_or_interrupted": continuity_bad,
            "punctuality_state": punctuality_state,
            "qualification_contract": PUNCTUALITY_CONTRACT,
            "qualification_start": qualification_start,
            "qualification_required": qualification_windows,
            "qualification_completed": min(completed, qualification_windows),
            "qualification_on_time": timing_counts[SchedulerTimingState.ON_TIME.value],
            "qualification_late": timing_counts[SchedulerTimingState.LATE.value],
            "qualification_missed": timing_counts[SchedulerTimingState.MISSED.value],
            "qualification_interrupted": timing_counts[SchedulerTimingState.INTERRUPTED.value],
            "qualification_missing": [value.isoformat() for value in qualification_missing],
            "qualification_duplicates": qualification_duplicates,
            "next_qualification_window": next_window,
            "latest_execution": (
                self._row_payload(latest, latest_timing, latest_delay)
                if latest is not None and latest_timing is not None
                else None
            ),
            "evidence": evidence,
            "status": punctuality_state,
            "exit_code": exit_code,
            "message": message,
            "modified_records": 0,
        }

    @staticmethod
    def _row_payload(
        row: SchedulerExecution,
        timing: SchedulerTimingState,
        delay: float | None,
    ) -> dict[str, Any]:
        return {
            "execution_id": str(row.id),
            "scheduled_at": row.scheduled_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "dispatch_delay_seconds": delay,
            "timing_state": timing.value,
            "collector_status": row.status.value,
            "error_type": row.error_type,
        }
