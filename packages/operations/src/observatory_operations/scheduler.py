"""Durable scheduler-window planning and terminal evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from observatory_db.models import SchedulerExecution, SchedulerExecutionStatus


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

    def plan(self, job_name: str, source_name: str, scheduled_at: datetime) -> bool:
        """Insert one plan atomically; return false when it already exists."""

        window = self._utc(scheduled_at)
        with Session(self.engine) as session:
            session.add(
                SchedulerExecution(
                    job_name=job_name,
                    source_name=source_name,
                    scheduled_at=window,
                    status=SchedulerExecutionStatus.SCHEDULED,
                    metadata_={},
                )
            )
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                existing_source = session.scalar(
                    select(SchedulerExecution.source_name).where(
                        SchedulerExecution.job_name == job_name,
                        SchedulerExecution.scheduled_at == window,
                    )
                )
                if existing_source is None:
                    raise
                if existing_source != source_name:
                    raise RuntimeError(
                        "scheduler window already exists with a different source"
                    ) from None
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
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduler evidence timestamp must be timezone-aware")
        return value.astimezone(UTC)
