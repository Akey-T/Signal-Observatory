from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from sqlalchemy import select
from sqlalchemy.orm import Session

from observatory_db import Base
from observatory_db.models import SchedulerExecution, SchedulerExecutionStatus
from observatory_db.session import create_database_engine
from observatory_operations import SchedulerLedger


def test_scheduler_ledger_persists_and_reconciles_elapsed_windows(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    now = datetime(2026, 8, 13, 2, 5, tzinfo=UTC)
    due = now - timedelta(minutes=5)
    future = now + timedelta(days=1)

    ledger.plan("arxiv_daily", "arxiv", due)
    ledger.plan("arxiv_daily", "arxiv", future)
    ledger.plan("arxiv_daily", "arxiv", future)
    reconciled = ledger.reconcile("arxiv_daily", now=now)

    assert [(item.scheduled_at, item.status) for item in reconciled] == [
        (due, SchedulerExecutionStatus.MISSED)
    ]
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(SchedulerExecution).order_by(SchedulerExecution.scheduled_at)
            ).all()
        )
        assert [row.status for row in rows] == [
            SchedulerExecutionStatus.MISSED,
            SchedulerExecutionStatus.SCHEDULED,
        ]
        assert rows[0].error_type == "worker_unavailable_at_due_time"
    engine.dispose()


def test_scheduler_ledger_records_success_and_interrupted_restart(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    scheduled = datetime(2026, 8, 13, 2, tzinfo=UTC)

    ledger.plan("arxiv_daily", "arxiv", scheduled)
    assert ledger.start("arxiv_daily", scheduled, now=scheduled)
    ledger.finish(
        "arxiv_daily",
        scheduled,
        now=scheduled + timedelta(minutes=1),
        status=SchedulerExecutionStatus.SUCCEEDED,
    )

    interrupted = scheduled + timedelta(days=1)
    ledger.plan("arxiv_daily", "arxiv", interrupted)
    assert ledger.start("arxiv_daily", interrupted, now=interrupted)
    assert not ledger.start("arxiv_daily", interrupted, now=interrupted)
    reconciled = ledger.reconcile("arxiv_daily", now=interrupted + timedelta(minutes=2))

    assert len(reconciled) == 1
    assert reconciled[0].status == SchedulerExecutionStatus.INTERRUPTED
    with Session(engine) as session:
        statuses = list(
            session.scalars(
                select(SchedulerExecution.status).order_by(SchedulerExecution.scheduled_at)
            ).all()
        )
        assert statuses == [
            SchedulerExecutionStatus.SUCCEEDED,
            SchedulerExecutionStatus.INTERRUPTED,
        ]
    engine.dispose()


def test_scheduler_ledger_preserves_partial_as_a_distinct_terminal_state(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    scheduled = datetime(2026, 8, 13, 2, tzinfo=UTC)

    assert ledger.plan("arxiv_daily", "arxiv", scheduled)
    assert not ledger.plan("arxiv_daily", "arxiv", scheduled)
    assert ledger.start("arxiv_daily", scheduled, now=scheduled)
    ledger.finish(
        "arxiv_daily",
        scheduled,
        now=scheduled + timedelta(minutes=1),
        status=SchedulerExecutionStatus.PARTIAL,
        error_type="collector_partial",
    )

    with Session(engine) as session:
        row = session.scalar(select(SchedulerExecution))
        assert row is not None
        assert row.status == SchedulerExecutionStatus.PARTIAL
        assert row.error_type == "collector_partial"
    engine.dispose()


def test_scheduler_window_claim_is_atomic_across_connections(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    scheduled = datetime(2026, 8, 13, 2, tzinfo=UTC)
    ledger.plan("arxiv_daily", "arxiv", scheduled)
    barrier = Barrier(2)

    def claim() -> bool:
        barrier.wait()
        return ledger.start("arxiv_daily", scheduled, now=scheduled)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: claim(), range(2)))

    assert sorted(results) == [False, True]
    engine.dispose()
