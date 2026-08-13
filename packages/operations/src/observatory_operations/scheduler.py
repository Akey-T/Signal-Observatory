"""Durable scheduler-window planning and terminal evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
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

    def plan(self, job_name: str, source_name: str, scheduled_at: datetime) -> None:
        window = self._utc(scheduled_at)
        with Session(self.engine) as session:
            existing = session.scalar(
                select(SchedulerExecution).where(
                    SchedulerExecution.job_name == job_name,
                    SchedulerExecution.scheduled_at == window,
                )
            )
            if existing is None:
                session.add(
                    SchedulerExecution(
                        job_name=job_name,
                        source_name=source_name,
                        scheduled_at=window,
                        status=SchedulerExecutionStatus.SCHEDULED,
                        metadata_={},
                    )
                )
                session.commit()

    def start(self, job_name: str, scheduled_at: datetime, *, now: datetime) -> bool:
        window = self._utc(scheduled_at)
        started_at = self._utc(now)
        with Session(self.engine) as session:
            row = session.scalar(
                select(SchedulerExecution).where(
                    SchedulerExecution.job_name == job_name,
                    SchedulerExecution.scheduled_at == window,
                )
            )
            if row is None or row.status != SchedulerExecutionStatus.SCHEDULED:
                return False
            row.status = SchedulerExecutionStatus.RUNNING
            row.started_at = started_at
            row.error_type = None
            session.commit()
        return True

    def finish(
        self,
        job_name: str,
        scheduled_at: datetime,
        *,
        now: datetime,
        succeeded: bool,
        error_type: str | None = None,
    ) -> None:
        window = self._utc(scheduled_at)
        finished_at = self._utc(now)
        with Session(self.engine) as session:
            row = session.scalar(
                select(SchedulerExecution).where(
                    SchedulerExecution.job_name == job_name,
                    SchedulerExecution.scheduled_at == window,
                )
            )
            if row is None or row.status != SchedulerExecutionStatus.RUNNING:
                raise RuntimeError("scheduler execution is not running")
            row.status = (
                SchedulerExecutionStatus.SUCCEEDED if succeeded else SchedulerExecutionStatus.FAILED
            )
            row.finished_at = finished_at
            row.error_type = error_type
            session.commit()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduler evidence timestamp must be timezone-aware")
        return value.astimezone(UTC)
