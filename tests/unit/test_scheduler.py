from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from observatory_db import Base
from observatory_db.models import SchedulerExecution, SchedulerExecutionStatus, Source
from observatory_db.repositories import IngestionRunRepository
from observatory_db.session import create_database_engine
from observatory_operations import (
    PUNCTUALITY_CONTRACT,
    SchedulerLedger,
    SchedulerPunctualityVerifier,
    SchedulerTimingState,
    scheduler_timing,
)


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


def test_scheduler_timing_is_independent_from_collector_result() -> None:
    scheduled = datetime(2026, 8, 25, 2, tzinfo=UTC)
    execution = SchedulerExecution(
        job_name="arxiv_daily",
        source_name="arxiv",
        scheduled_at=scheduled,
        started_at=scheduled + timedelta(seconds=45),
        finished_at=scheduled + timedelta(minutes=2),
        status=SchedulerExecutionStatus.PARTIAL,
        metadata_={},
    )

    timing, delay = scheduler_timing(
        execution,
        now=scheduled + timedelta(hours=1),
    )

    assert timing is SchedulerTimingState.ON_TIME
    assert delay == 45
    assert execution.status is SchedulerExecutionStatus.PARTIAL


@pytest.mark.parametrize(
    ("delay_seconds", "expected"),
    [
        (0, SchedulerTimingState.ON_TIME),
        (299, SchedulerTimingState.ON_TIME),
        (300, SchedulerTimingState.ON_TIME),
        (301, SchedulerTimingState.LATE),
    ],
)
def test_scheduler_timing_boundary_is_inclusive_at_five_minutes(
    delay_seconds: int,
    expected: SchedulerTimingState,
) -> None:
    scheduled = datetime(2026, 8, 25, 2, tzinfo=UTC)
    execution = SchedulerExecution(
        job_name="arxiv_daily",
        source_name="arxiv",
        scheduled_at=scheduled,
        started_at=scheduled + timedelta(seconds=delay_seconds),
        finished_at=scheduled + timedelta(minutes=10),
        status=SchedulerExecutionStatus.SUCCEEDED,
        metadata_={},
    )

    timing, delay = scheduler_timing(execution, now=scheduled + timedelta(hours=1))

    assert timing is expected
    assert delay == delay_seconds


@pytest.mark.parametrize("completed_windows", [0, 1, 2])
def test_punctuality_verifier_remains_pending_before_three_windows(
    tmp_path,
    completed_windows: int,
) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2026, 8, 26, 2, tzinfo=UTC)
    now = start + timedelta(days=max(0, completed_windows - 1), hours=1)
    with Session(engine) as session:
        for index in range(completed_windows):
            scheduled = start + timedelta(days=index)
            session.add(
                SchedulerExecution(
                    job_name="arxiv_daily",
                    source_name="arxiv",
                    scheduled_at=scheduled,
                    started_at=scheduled + timedelta(seconds=20),
                    finished_at=scheduled + timedelta(minutes=5),
                    status=SchedulerExecutionStatus.SUCCEEDED,
                    metadata_={"punctuality_contract": PUNCTUALITY_CONTRACT},
                )
            )
        session.commit()

        report = SchedulerPunctualityVerifier(session, now=now).status(
            job_name="arxiv_daily",
            source_name="arxiv",
            schedule="0 2 * * *",
        )

    assert report["punctuality_state"] == "pending"
    assert report["qualification_completed"] == completed_windows
    assert report["exit_code"] == 1
    assert report["modified_records"] == 0
    engine.dispose()


def test_manual_ingestion_run_cannot_satisfy_punctuality(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 26, 3, tzinfo=UTC)
    with Session(engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        session.add(source)
        session.flush()
        repository = IngestionRunRepository(session)
        run = repository.start(
            source=source,
            collector_version="test",
            checkpoint_before={"mode": "incremental", "trigger": "manual"},
        )
        repository.complete(
            run,
            records_requested=0,
            records_received=0,
            records_inserted=0,
            records_updated=0,
            records_skipped=0,
            error_count=0,
        )
        session.commit()

        report = SchedulerPunctualityVerifier(session, now=now).status(
            job_name="arxiv_daily",
            source_name="arxiv",
            schedule="0 2 * * *",
        )

    assert report["punctuality_state"] == "pending"
    assert report["qualification_completed"] == 0
    assert report["evidence"] == []
    engine.dispose()


def test_contract_planning_does_not_rewrite_historical_late_execution(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    scheduled = datetime(2026, 8, 24, 2, tzinfo=UTC)
    started = scheduled + timedelta(hours=6)
    with Session(engine) as session:
        session.add(
            SchedulerExecution(
                job_name="arxiv_daily",
                source_name="arxiv",
                scheduled_at=scheduled,
                started_at=started,
                finished_at=started + timedelta(minutes=2),
                status=SchedulerExecutionStatus.PARTIAL,
                metadata_={"historical": True},
            )
        )
        session.commit()

    created = SchedulerLedger(engine).plan(
        "arxiv_daily",
        "arxiv",
        scheduled,
        metadata={"punctuality_contract": PUNCTUALITY_CONTRACT},
    )

    with Session(engine) as session:
        row = session.scalar(select(SchedulerExecution))
        assert row is not None
        assert not created
        assert row.started_at == started
        assert row.status is SchedulerExecutionStatus.PARTIAL
        assert row.metadata_ == {"historical": True}
    engine.dispose()


def test_v2_planning_does_not_retag_an_existing_v1_future_window(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    planned = datetime(2026, 9, 25, 2, tzinfo=UTC)
    assert ledger.plan(
        "arxiv_daily",
        "arxiv",
        planned,
        metadata={"punctuality_contract": "scheduler-punctuality-v1"},
    )
    assert not ledger.plan(
        "arxiv_daily",
        "arxiv",
        planned,
        metadata={"punctuality_contract": PUNCTUALITY_CONTRACT},
    )
    assert ledger.plan(
        "arxiv_daily",
        "arxiv",
        planned + timedelta(days=1),
        metadata={"punctuality_contract": PUNCTUALITY_CONTRACT},
    )
    with Session(engine) as session:
        rows = session.scalars(
            select(SchedulerExecution).order_by(SchedulerExecution.scheduled_at)
        ).all()
        assert [row.metadata_["punctuality_contract"] for row in rows] == [
            "scheduler-punctuality-v1",
            "scheduler-punctuality-v2",
        ]
    engine.dispose()


def test_v2_status_skips_an_already_planned_v1_future_window(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    planned = datetime(2026, 9, 25, 2, tzinfo=UTC)
    assert SchedulerLedger(engine).plan(
        "arxiv_daily",
        "arxiv",
        planned,
        metadata={"punctuality_contract": "scheduler-punctuality-v1"},
    )
    with Session(engine) as session:
        report = SchedulerPunctualityVerifier(session, now=planned - timedelta(hours=1)).status(
            job_name="arxiv_daily", source_name="arxiv", schedule="0 2 * * *"
        )

    assert report["punctuality_state"] == "pending"
    assert report["qualification_completed"] == 0
    assert report["next_qualification_window"] == planned + timedelta(days=1)
    assert report["modified_records"] == 0
    engine.dispose()


def test_v2_qualification_ignores_failed_v1_windows_without_rewriting_them(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    first_v2 = datetime(2026, 9, 26, 2, tzinfo=UTC)
    with Session(engine) as session:
        for index in range(3):
            old = first_v2 - timedelta(days=3 - index)
            fresh = first_v2 + timedelta(days=index)
            session.add_all(
                [
                    SchedulerExecution(
                        job_name="arxiv_daily",
                        source_name="arxiv",
                        scheduled_at=old,
                        started_at=old + timedelta(hours=2),
                        finished_at=old + timedelta(hours=3),
                        status=SchedulerExecutionStatus.SUCCEEDED,
                        metadata_={"punctuality_contract": "scheduler-punctuality-v1"},
                    ),
                    SchedulerExecution(
                        job_name="arxiv_daily",
                        source_name="arxiv",
                        scheduled_at=fresh,
                        started_at=fresh + timedelta(seconds=300),
                        finished_at=fresh + timedelta(minutes=10),
                        status=SchedulerExecutionStatus.PARTIAL,
                        metadata_={"punctuality_contract": PUNCTUALITY_CONTRACT},
                    ),
                ]
            )
        session.commit()
        report = SchedulerPunctualityVerifier(
            session, now=first_v2 + timedelta(days=2, hours=1)
        ).status(job_name="arxiv_daily", source_name="arxiv", schedule="0 2 * * *")
        old_rows = session.scalars(
            select(SchedulerExecution).where(SchedulerExecution.scheduled_at < first_v2)
        ).all()

    assert report["qualification_contract"] == "scheduler-punctuality-v2"
    assert report["punctuality_state"] == "passed"
    assert report["qualification_on_time"] == 3
    assert report["qualification_late"] == 0
    assert len(report["evidence"]) == 3
    assert report["modified_records"] == 0
    assert all(
        row.metadata_["punctuality_contract"] == "scheduler-punctuality-v1" for row in old_rows
    )
    engine.dispose()


@pytest.mark.parametrize(
    ("terminal_status", "expected_field"),
    [
        (SchedulerExecutionStatus.MISSED, "qualification_missed"),
        (SchedulerExecutionStatus.INTERRUPTED, "qualification_interrupted"),
    ],
)
def test_v2_qualification_rejects_missed_or_interrupted_window(
    terminal_status: SchedulerExecutionStatus, expected_field: str
) -> None:
    scheduled = datetime(2026, 9, 26, 2, tzinfo=UTC)
    row = SchedulerExecution(
        job_name="arxiv_daily",
        source_name="arxiv",
        scheduled_at=scheduled,
        started_at=(scheduled if terminal_status is SchedulerExecutionStatus.INTERRUPTED else None),
        finished_at=scheduled + timedelta(minutes=1),
        status=terminal_status,
        metadata_={"punctuality_contract": PUNCTUALITY_CONTRACT},
    )
    session = Mock(spec=Session)
    session.scalars.return_value.all.return_value = [row]
    report = SchedulerPunctualityVerifier(session, now=scheduled + timedelta(minutes=2)).status(
        job_name="arxiv_daily", source_name="arxiv", schedule="0 2 * * *"
    )

    assert report["punctuality_state"] == "failed"
    assert report[expected_field] == 1
    assert report["modified_records"] == 0


def test_v2_qualification_rejects_duplicate_window() -> None:
    scheduled = datetime(2026, 9, 26, 2, tzinfo=UTC)
    row = SchedulerExecution(
        job_name="arxiv_daily",
        source_name="arxiv",
        scheduled_at=scheduled,
        started_at=scheduled + timedelta(seconds=1),
        finished_at=scheduled + timedelta(minutes=1),
        status=SchedulerExecutionStatus.SUCCEEDED,
        metadata_={"punctuality_contract": PUNCTUALITY_CONTRACT},
    )
    session = Mock(spec=Session)
    session.scalars.return_value.all.return_value = [row, row]
    report = SchedulerPunctualityVerifier(session, now=scheduled + timedelta(minutes=2)).status(
        job_name="arxiv_daily", source_name="arxiv", schedule="0 2 * * *"
    )

    assert report["punctuality_state"] == "failed"
    assert report["qualification_duplicates"] == 1
    assert report["modified_records"] == 0


def test_punctuality_verifier_requires_three_tagged_real_windows(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2026, 8, 23, 2, tzinfo=UTC)
    statuses = [
        SchedulerExecutionStatus.SUCCEEDED,
        SchedulerExecutionStatus.PARTIAL,
        SchedulerExecutionStatus.FAILED,
    ]
    with Session(engine) as session:
        for index in range(7):
            scheduled = start - timedelta(days=4) + timedelta(days=index)
            status = statuses[index - 4] if index >= 4 else SchedulerExecutionStatus.SUCCEEDED
            session.add(
                SchedulerExecution(
                    job_name="arxiv_daily",
                    source_name="arxiv",
                    scheduled_at=scheduled,
                    started_at=scheduled + timedelta(seconds=30 + index),
                    finished_at=scheduled + timedelta(minutes=5),
                    status=status,
                    metadata_=(
                        {"punctuality_contract": PUNCTUALITY_CONTRACT} if index >= 4 else {}
                    ),
                )
            )
        session.commit()

        report = SchedulerPunctualityVerifier(
            session,
            now=start + timedelta(days=2, hours=1),
        ).status(
            job_name="arxiv_daily",
            source_name="arxiv",
            schedule="0 2 * * *",
        )

    assert report["continuity_state"] == "passed"
    assert report["punctuality_state"] == "passed"
    assert report["qualification_completed"] == 3
    assert report["qualification_on_time"] == 3
    assert report["qualification_late"] == 0
    assert report["evidence"][1]["collector_status"] == "partial"
    assert report["evidence"][2]["collector_status"] == "failed"
    assert report["modified_records"] == 0
    engine.dispose()


def test_punctuality_verifier_fails_late_and_missing_windows(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2026, 8, 23, 2, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            SchedulerExecution(
                job_name="arxiv_daily",
                source_name="arxiv",
                scheduled_at=start,
                started_at=start + timedelta(seconds=301),
                finished_at=start + timedelta(minutes=10),
                status=SchedulerExecutionStatus.SUCCEEDED,
                metadata_={"punctuality_contract": PUNCTUALITY_CONTRACT},
            )
        )
        session.commit()
        report = SchedulerPunctualityVerifier(
            session,
            now=start + timedelta(days=2, hours=1),
        ).status(
            job_name="arxiv_daily",
            source_name="arxiv",
            schedule="0 2 * * *",
        )

    assert report["punctuality_state"] == "failed"
    assert report["qualification_late"] == 1
    assert report["qualification_missing"] == [
        "2026-08-24T02:00:00+00:00",
        "2026-08-25T02:00:00+00:00",
    ]
    assert report["exit_code"] == 2
    engine.dispose()
