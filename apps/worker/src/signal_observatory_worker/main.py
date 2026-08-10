"""Gracefully managed worker skeleton without real external collectors."""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from arxiv_collector import ArxivCollectionService
from observatory_db.session import create_database_engine, wait_for_database
from signal_observatory_api.logging import configure_logging
from signal_observatory_config import Settings, get_settings

logger = structlog.get_logger("worker")


def next_arxiv_run(schedule: str, now: datetime) -> datetime:
    """Resolve the supported daily UTC cron shape: ``minute hour * * *``."""

    parts = schedule.split()
    if len(parts) != 5 or parts[2:] != ["*", "*", "*"]:
        raise ValueError("ARXIV_SCHEDULE must use daily UTC cron format: minute hour * * *")
    try:
        minute, hour = int(parts[0]), int(parts[1])
    except ValueError as error:
        raise ValueError("ARXIV_SCHEDULE minute and hour must be integers") from error
    if not 0 <= minute <= 59 or not 0 <= hour <= 23:
        raise ValueError("ARXIV_SCHEDULE hour/minute is outside the valid range")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("scheduler time must be timezone-aware")
    current = now.astimezone(UTC)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate if candidate > current else candidate + timedelta(days=1)


async def arxiv_scheduler(
    settings: Settings,
    engine: Engine,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        now = datetime.now(UTC)
        scheduled = next_arxiv_run(settings.arxiv_schedule, now)
        delay = max(0.0, (scheduled - now).total_seconds())
        logger.info("arxiv_collection_scheduled", scheduled_at=scheduled.isoformat())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            return
        except TimeoutError:
            pass
        try:
            with Session(engine) as session:
                summary = await ArxivCollectionService(session, settings).collect()
            logger.info(
                "arxiv_scheduled_collection_finished",
                run_id=str(summary.run_id),
                status=summary.status,
                api_requests=summary.api_requests,
                records_received=summary.entries_received,
            )
        except Exception as error:
            logger.exception(
                "arxiv_scheduled_collection_failed",
                error_type=type(error).__name__,
            )


async def serve(settings: Settings, *, stop_event: asyncio.Event | None = None) -> None:
    configure_logging(settings.log_level)
    next_arxiv_run(settings.arxiv_schedule, datetime.now(UTC))
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
    scheduler_task = asyncio.create_task(arxiv_scheduler(settings, engine, shutdown))
    logger.info("worker_started", **settings.public_summary())
    try:
        await shutdown.wait()
    finally:
        await scheduler_task
        ready_file.unlink(missing_ok=True)
        await asyncio.to_thread(engine.dispose)
        logger.info("worker_stopped")


def run() -> None:
    asyncio.run(serve(get_settings()))


if __name__ == "__main__":
    run()
