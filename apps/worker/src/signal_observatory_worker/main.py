"""Gracefully managed scheduler shared by independent source collectors."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from arxiv_collector import ArxivCollectionService
from github_collector import GithubCollectionService
from observatory_db.session import create_database_engine, wait_for_database
from observatory_operations import CoverageDeriver
from signal_observatory_api.logging import configure_logging
from signal_observatory_config import Settings, get_settings

logger = structlog.get_logger("worker")
WallClock = Callable[[], datetime]
Job = Callable[[], Awaitable[None]]


def next_cron_run(schedule: str, now: datetime, *, setting_name: str) -> datetime:
    """Resolve conservative daily or weekly UTC cron: ``minute hour * * [*|0-6]``."""

    parts = schedule.split()
    if len(parts) != 5 or parts[2:4] != ["*", "*"]:
        raise ValueError(f"{setting_name} must use UTC cron format: minute hour * * weekday")
    try:
        minute, hour = int(parts[0]), int(parts[1])
    except ValueError as error:
        raise ValueError(f"{setting_name} minute and hour must be integers") from error
    if not 0 <= minute <= 59 or not 0 <= hour <= 23:
        raise ValueError(f"{setting_name} hour/minute is outside the valid range")
    weekday = parts[4]
    if weekday != "*":
        try:
            weekday_value = int(weekday)
        except ValueError as error:
            raise ValueError(f"{setting_name} weekday must be * or 0-6") from error
        if not 0 <= weekday_value <= 6:
            raise ValueError(f"{setting_name} weekday must be * or 0-6")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("scheduler time must be timezone-aware")
    current = now.astimezone(UTC)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday == "*":
        return candidate if candidate > current else candidate + timedelta(days=1)
    cron_today = (current.weekday() + 1) % 7
    days_ahead = (int(weekday) - cron_today) % 7
    candidate += timedelta(days=days_ahead)
    return candidate if candidate > current else candidate + timedelta(days=7)


def next_arxiv_run(schedule: str, now: datetime) -> datetime:
    """Backward-compatible validated arXiv daily schedule resolver."""

    if schedule.split()[-1:] != ["*"]:
        raise ValueError("ARXIV_SCHEDULE must use daily UTC cron format: minute hour * * *")
    return next_cron_run(schedule, now, setting_name="ARXIV_SCHEDULE")


async def wait_until_due(
    scheduled_at: datetime,
    stop_event: asyncio.Event,
    *,
    wall_clock: WallClock = lambda: datetime.now(UTC),
    poll_seconds: float = 60.0,
) -> bool:
    """Poll wall time so host sleep cannot strand one long monotonic timer."""

    while not stop_event.is_set():
        now = wall_clock().astimezone(UTC)
        remaining = (scheduled_at - now).total_seconds()
        if remaining <= 0:
            return True
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=min(poll_seconds, remaining))
            return False
        except TimeoutError:
            continue
    return False


async def scheduled_job(
    *,
    name: str,
    schedule: str,
    setting_name: str,
    stop_event: asyncio.Event,
    execution_lock: asyncio.Lock,
    job: Job,
    wall_clock: WallClock = lambda: datetime.now(UTC),
) -> None:
    while not stop_event.is_set():
        scheduled_at = next_cron_run(schedule, wall_clock(), setting_name=setting_name)
        logger.info("collector_job_scheduled", job=name, scheduled_at=scheduled_at.isoformat())
        if not await wait_until_due(scheduled_at, stop_event, wall_clock=wall_clock):
            return
        try:
            async with execution_lock:
                if stop_event.is_set():
                    return
                await job()
        except Exception as error:
            logger.exception(
                "scheduled_collector_job_failed",
                job=name,
                error_type=type(error).__name__,
            )


async def scheduler_host(
    settings: Settings,
    engine: Engine,
    stop_event: asyncio.Event,
) -> None:
    execution_lock = asyncio.Lock()

    async def collect_arxiv() -> None:
        with Session(engine) as session:
            summary = await ArxivCollectionService(session, settings).collect(trigger="scheduled")
            CoverageDeriver(session).rebuild()
        logger.info(
            "arxiv_scheduled_collection_finished",
            run_id=str(summary.run_id),
            status=summary.status,
            api_requests=summary.api_requests,
            records_received=summary.entries_received,
        )

    async def snapshot_github() -> None:
        with Session(engine) as session:
            summary = await GithubCollectionService(session, settings).snapshot()
            CoverageDeriver(session).rebuild()
        logger.info(
            "github_scheduled_snapshot_finished",
            run_id=str(summary.run_id),
            status=summary.status,
            requests=summary.requests_sent,
            snapshots=summary.snapshots_created,
        )

    async def discover_github() -> None:
        with Session(engine) as session:
            summary = await GithubCollectionService(session, settings).discover()
            CoverageDeriver(session).rebuild()
        logger.info(
            "github_scheduled_discovery_finished",
            run_id=str(summary.run_id),
            status=summary.status,
            requests=summary.requests_sent,
            repositories=summary.unique_repositories,
        )

    tasks = [
        asyncio.create_task(
            scheduled_job(
                name="arxiv_daily",
                schedule=settings.arxiv_schedule,
                setting_name="ARXIV_SCHEDULE",
                stop_event=stop_event,
                execution_lock=execution_lock,
                job=collect_arxiv,
            )
        ),
        asyncio.create_task(
            scheduled_job(
                name="github_daily_snapshot",
                schedule=settings.github_snapshot_schedule,
                setting_name="GITHUB_SNAPSHOT_SCHEDULE",
                stop_event=stop_event,
                execution_lock=execution_lock,
                job=snapshot_github,
            )
        ),
        asyncio.create_task(
            scheduled_job(
                name="github_weekly_discovery",
                schedule=settings.github_discovery_schedule,
                setting_name="GITHUB_DISCOVERY_SCHEDULE",
                stop_event=stop_event,
                execution_lock=execution_lock,
                job=discover_github,
            )
        ),
    ]
    try:
        await stop_event.wait()
    finally:
        await asyncio.gather(*tasks)


async def serve(settings: Settings, *, stop_event: asyncio.Event | None = None) -> None:
    configure_logging(settings.log_level)
    next_arxiv_run(settings.arxiv_schedule, datetime.now(UTC))
    next_cron_run(
        settings.github_snapshot_schedule,
        datetime.now(UTC),
        setting_name="GITHUB_SNAPSHOT_SCHEDULE",
    )
    next_cron_run(
        settings.github_discovery_schedule,
        datetime.now(UTC),
        setting_name="GITHUB_DISCOVERY_SCHEDULE",
    )
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
                    handled_signal,
                    lambda _signum, _frame: loop.call_soon_threadsafe(shutdown.set),
                )

    ready_file = Path(settings.worker_ready_file)
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    ready_file.write_text("ready\n", encoding="utf-8")
    scheduler_task = asyncio.create_task(scheduler_host(settings, engine, shutdown))
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
