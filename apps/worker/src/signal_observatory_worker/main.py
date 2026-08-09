"""Gracefully managed worker skeleton without real external collectors."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import structlog

from observatory_db.session import create_database_engine, wait_for_database
from signal_observatory_api.logging import configure_logging
from signal_observatory_config import Settings, get_settings

logger = structlog.get_logger("worker")


async def serve(settings: Settings, *, stop_event: asyncio.Event | None = None) -> None:
    configure_logging(settings.log_level)
    engine = create_database_engine(settings.database_url)
    await asyncio.to_thread(
        wait_for_database,
        engine,
        attempts=settings.database_connect_attempts,
        delay_seconds=settings.database_connect_delay_seconds,
    )

    shutdown = stop_event or asyncio.Event()
    if stop_event is None:
        loop = asyncio.get_running_loop()
        for handled_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(handled_signal, shutdown.set)
            except NotImplementedError:
                signal.signal(
                    handled_signal, lambda _signum, _frame: loop.call_soon_threadsafe(shutdown.set)
                )

    ready_file = Path(settings.worker_ready_file)
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    ready_file.write_text("ready\n", encoding="utf-8")
    logger.info("worker_started", **settings.public_summary())
    try:
        await shutdown.wait()
    finally:
        ready_file.unlink(missing_ok=True)
        await asyncio.to_thread(engine.dispose)
        logger.info("worker_stopped")


def run() -> None:
    asyncio.run(serve(get_settings()))


if __name__ == "__main__":
    run()
