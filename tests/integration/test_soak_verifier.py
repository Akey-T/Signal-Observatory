from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from observatory_db.models import IngestionRun, IngestionStatus, Source
from observatory_operations import ArxivSoakVerifier
from signal_observatory_config import Settings


def test_soak_is_pending_without_scheduler_tagged_runs(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        session.add(Source(name="arxiv", kind="api", metadata_={}))
        session.commit()
        report = ArxivSoakVerifier(
            session,
            Settings(_env_file=None),
            now=datetime(2026, 8, 11, 12, tzinfo=UTC),
        ).verify(days=7)

    assert report["status"] == "pending"
    assert report["actual_scheduled_runs"] == 0
    assert report["remaining_future_windows"] == 7
    assert report["modified_records"] == 0


def test_soak_accepts_visible_partial_runs_after_seven_real_windows(
    migrated_engine: Engine,
) -> None:
    start = datetime(2026, 8, 12, 2, tzinfo=UTC)
    with Session(migrated_engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        session.add(source)
        session.flush()
        for index in range(7):
            started_at = start + timedelta(days=index)
            session.add(
                IngestionRun(
                    source_id=source.id,
                    started_at=started_at,
                    finished_at=started_at + timedelta(minutes=5),
                    status=(IngestionStatus.PARTIAL if index == 3 else IngestionStatus.SUCCEEDED),
                    collector_version="test",
                    metadata_={"mode": "incremental", "trigger": "scheduled"},
                )
            )
        session.commit()
        report = ArxivSoakVerifier(
            session,
            Settings(_env_file=None),
            now=datetime(2026, 8, 18, 3, tzinfo=UTC),
        ).verify(days=7)

    assert report["status"] == "passed"
    assert report["successful"] == 6
    assert report["partial"] == 1
    assert report["missing"] == 0
    assert report["duplicate_scheduling"] == 0


def test_soak_surfaces_missing_and_duplicate_scheduler_windows(
    migrated_engine: Engine,
) -> None:
    start = datetime(2026, 8, 12, 2, tzinfo=UTC)
    with Session(migrated_engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        session.add(source)
        session.flush()
        for offset in (0, 0, 2):
            started_at = start + timedelta(days=offset)
            session.add(
                IngestionRun(
                    source_id=source.id,
                    started_at=started_at,
                    finished_at=started_at + timedelta(minutes=5),
                    status=IngestionStatus.SUCCEEDED,
                    collector_version="test",
                    metadata_={"mode": "incremental", "trigger": "scheduled"},
                )
            )
        session.commit()
        report = ArxivSoakVerifier(
            session,
            Settings(_env_file=None),
            now=datetime(2026, 8, 14, 3, tzinfo=UTC),
        ).verify(days=7)

    assert report["status"] == "failed"
    assert report["missing_dates"] == ["2026-08-13"]
    assert report["duplicate_scheduling"] == 1
