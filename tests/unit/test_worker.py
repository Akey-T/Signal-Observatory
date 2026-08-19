from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import signal_observatory_worker.main as worker_main
from observatory_db import Base
from observatory_db.models import SchedulerExecution, SchedulerExecutionStatus
from observatory_db.session import create_database_engine
from observatory_operations import SchedulerLedger
from signal_observatory_config import Settings
from signal_observatory_worker.main import (
    elapsed_cron_runs,
    next_arxiv_run,
    next_cron_run,
    scheduled_job,
    scheduler_status_for_collector,
    serve,
    wait_until_due,
)


@pytest.mark.asyncio
async def test_worker_readiness_lifecycle(tmp_path: Path) -> None:
    ready_file = tmp_path / "worker-ready"
    database_url = f"sqlite+pysqlite:///{tmp_path / 'worker.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    stop_event = asyncio.Event()
    settings = Settings(
        database_url=database_url,
        environment="test",
        worker_ready_file=ready_file,
        database_connect_attempts=1,
        database_connect_delay_seconds=0,
    )

    worker = asyncio.create_task(serve(settings, stop_event=stop_event))
    for _attempt in range(100):
        if ready_file.is_file():
            break
        await asyncio.sleep(0.01)

    assert ready_file.read_text(encoding="utf-8") == "ready\n"
    stop_event.set()
    await asyncio.wait_for(worker, timeout=1)
    assert not ready_file.exists()


def test_daily_arxiv_schedule_uses_utc_and_rolls_to_next_day() -> None:
    before = next_arxiv_run("0 2 * * *", datetime(2026, 8, 10, 1, 30, tzinfo=UTC))
    after = next_arxiv_run("0 2 * * *", datetime(2026, 8, 10, 2, 30, tzinfo=UTC))
    assert before == datetime(2026, 8, 10, 2, tzinfo=UTC)
    assert after == datetime(2026, 8, 11, 2, tzinfo=UTC)


def test_weekly_github_schedule_uses_cron_sunday() -> None:
    scheduled = next_cron_run(
        "0 3 * * 0",
        datetime(2026, 8, 11, 4, tzinfo=UTC),
        setting_name="GITHUB_DISCOVERY_SCHEDULE",
    )

    assert scheduled == datetime(2026, 8, 16, 3, tzinfo=UTC)


def test_reconciliation_materializes_every_elapsed_daily_window() -> None:
    windows = elapsed_cron_runs(
        "0 2 * * *",
        after=datetime(2026, 8, 13, 2, tzinfo=UTC),
        until=datetime(2026, 8, 16, 5, tzinfo=UTC),
        setting_name="ARXIV_SCHEDULE",
    )
    assert windows == (
        datetime(2026, 8, 14, 2, tzinfo=UTC),
        datetime(2026, 8, 15, 2, tzinfo=UTC),
        datetime(2026, 8, 16, 2, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_scheduled_job_persists_every_missed_window_after_long_downtime(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    first_window = datetime(2026, 8, 13, 2, tzinfo=UTC)
    ledger.plan("arxiv_daily", "arxiv", first_window)
    ledger.plan("arxiv_daily", "arxiv", datetime(2026, 8, 16, 2, tzinfo=UTC))
    stopped = asyncio.Event()
    stopped.set()

    async def unused_job() -> SchedulerExecutionStatus:
        raise AssertionError("a reconciled missed window must not be executed")

    await scheduled_job(
        name="arxiv_daily",
        source_name="arxiv",
        schedule="0 2 * * *",
        setting_name="ARXIV_SCHEDULE",
        stop_event=stopped,
        execution_lock=asyncio.Lock(),
        job=unused_job,
        ledger=ledger,
        wall_clock=lambda: datetime(2026, 8, 16, 5, tzinfo=UTC),
    )

    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(SchedulerExecution).order_by(SchedulerExecution.scheduled_at)
            ).all()
        )
        assert [row.scheduled_at for row in rows] == [
            datetime(2026, 8, day, 2, tzinfo=UTC) for day in range(13, 17)
        ]
        assert {row.status for row in rows} == {SchedulerExecutionStatus.MISSED}
    engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_job_persists_partial_without_promoting_it(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'scheduler.db'}")
    Base.metadata.create_all(engine)
    ledger = SchedulerLedger(engine)
    stopped = asyncio.Event()
    readings = iter(
        [
            datetime(2026, 8, 13, 1, 59, tzinfo=UTC),
            datetime(2026, 8, 13, 1, 59, tzinfo=UTC),
            datetime(2026, 8, 13, 2, tzinfo=UTC),
            datetime(2026, 8, 13, 2, tzinfo=UTC),
            datetime(2026, 8, 13, 2, 1, tzinfo=UTC),
        ]
    )

    async def partial_job() -> SchedulerExecutionStatus:
        stopped.set()
        return SchedulerExecutionStatus.PARTIAL

    await scheduled_job(
        name="arxiv_daily",
        source_name="arxiv",
        schedule="0 2 * * *",
        setting_name="ARXIV_SCHEDULE",
        stop_event=stopped,
        execution_lock=asyncio.Lock(),
        job=partial_job,
        ledger=ledger,
        wall_clock=lambda: next(readings),
    )

    with Session(engine) as session:
        row = session.scalar(select(SchedulerExecution))
        assert row is not None
        assert row.status == SchedulerExecutionStatus.PARTIAL
        assert row.error_type == "collector_partial"
    engine.dispose()


@pytest.mark.parametrize(
    ("collector_status", "expected"),
    [
        ("succeeded", SchedulerExecutionStatus.SUCCEEDED),
        ("partial", SchedulerExecutionStatus.PARTIAL),
        ("failed", SchedulerExecutionStatus.FAILED),
    ],
)
def test_collector_terminal_status_is_not_promoted_to_success(
    collector_status: str,
    expected: SchedulerExecutionStatus,
) -> None:
    assert scheduler_status_for_collector(collector_status) == expected


@pytest.mark.asyncio
async def test_scheduler_failure_removes_readiness_and_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_file = tmp_path / "worker-ready"
    database_url = f"sqlite+pysqlite:///{tmp_path / 'worker.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    settings = Settings(
        database_url=database_url,
        environment="test",
        worker_ready_file=ready_file,
        database_connect_attempts=1,
        database_connect_delay_seconds=0,
    )
    failure_release = asyncio.Event()
    cleanup_release = asyncio.Event()
    call_count = 0

    async def fail_scheduler_job(**_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await failure_release.wait()
            raise RuntimeError("forced scheduler failure")
        await cleanup_release.wait()

    monkeypatch.setattr(worker_main, "scheduled_job", fail_scheduler_job)

    worker = asyncio.create_task(serve(settings))
    for _attempt in range(100):
        if ready_file.is_file():
            break
        await asyncio.sleep(0.01)
    assert ready_file.is_file()
    failure_release.set()
    for _attempt in range(100):
        if not ready_file.exists():
            break
        await asyncio.sleep(0.01)
    assert not ready_file.exists()
    assert not worker.done()
    cleanup_release.set()
    with pytest.raises(RuntimeError, match="forced scheduler failure"):
        await worker


@pytest.mark.asyncio
async def test_wall_clock_poll_detects_due_time_after_host_sleep() -> None:
    before_sleep = datetime(2026, 8, 11, 1, 59, tzinfo=UTC)
    after_wake = datetime(2026, 8, 11, 2, 5, tzinfo=UTC)
    readings = iter([before_sleep, after_wake])

    assert await wait_until_due(
        before_sleep + timedelta(minutes=1),
        asyncio.Event(),
        wall_clock=lambda: next(readings),
        poll_seconds=0.001,
    )


@pytest.mark.parametrize("schedule", ["hourly", "0 * * * *", "70 2 * * *"])
def test_invalid_arxiv_schedule_is_rejected(schedule: str) -> None:
    with pytest.raises(ValueError, match="ARXIV_SCHEDULE"):
        next_arxiv_run(schedule, datetime(2026, 8, 10, tzinfo=UTC))
