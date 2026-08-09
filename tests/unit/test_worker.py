from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from signal_observatory_config import Settings
from signal_observatory_worker.main import serve


@pytest.mark.asyncio
async def test_worker_readiness_lifecycle(tmp_path: Path) -> None:
    ready_file = tmp_path / "worker-ready"
    stop_event = asyncio.Event()
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
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
