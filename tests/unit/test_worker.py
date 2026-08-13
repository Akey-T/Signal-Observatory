from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from observatory_db import Base
from observatory_db.session import create_database_engine
from signal_observatory_config import Settings
from signal_observatory_worker.main import (
    next_arxiv_run,
    next_cron_run,
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
