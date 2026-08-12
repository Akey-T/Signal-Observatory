from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from observatory_db.coverage_models import (
    CoverageStatus,
    CoverageStrategy,
    TopicSourceCoverage,
)
from observatory_db.models import (
    IngestionRun,
    IngestionStatus,
    Source,
    Topic,
    TopicSourceMapping,
)
from signal_observatory_api.main import create_app
from signal_observatory_config import Settings


@pytest.mark.asyncio
async def test_operations_and_coverage_endpoints_are_truthful(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 11, 9, tzinfo=UTC)
    with Session(migrated_engine) as session:
        sources = {
            name: Source(name=name, kind="api", metadata_={})
            for name in ("arxiv", "github", "hacker_news", "wikipedia")
        }
        topic = Topic(
            canonical_name="Model Context Protocol",
            normalized_name="model context protocol",
            slug="model-context-protocol",
        )
        session.add_all([*sources.values(), topic])
        session.flush()
        for source in sources.values():
            session.add(
                TopicSourceMapping(
                    topic_id=topic.id,
                    source_id=source.id,
                    enabled=True,
                    mapping_type="registry",
                    configuration={},
                )
            )
        session.add_all(
            [
                IngestionRun(
                    source_id=sources["arxiv"].id,
                    started_at=now,
                    finished_at=now,
                    status=IngestionStatus.PARTIAL,
                    collector_version="test",
                    error_count=1,
                    metadata_={"mode": "incremental"},
                ),
                IngestionRun(
                    source_id=sources["github"].id,
                    started_at=now,
                    finished_at=now,
                    status=IngestionStatus.SUCCEEDED,
                    collector_version="test",
                    metadata_={"mode": "snapshot"},
                ),
                TopicSourceCoverage(
                    topic_id=topic.id,
                    source_id=sources["arxiv"].id,
                    coverage_status=CoverageStatus.PARTIAL,
                    coverage_strategy=CoverageStrategy.HISTORICAL_BACKFILL,
                    coverage_start=datetime(2026, 7, 1, tzinfo=UTC).date(),
                    coverage_end=datetime(2026, 8, 1, tzinfo=UTC).date(),
                    target_start=datetime(2026, 7, 1, tzinfo=UTC).date(),
                    target_end=datetime(2026, 8, 11, tzinfo=UTC).date(),
                    last_successful_run_at=now,
                    observation_count=12,
                    missing_observation_count=1,
                    partial_reason="One cursor window remains incomplete.",
                    derived_at=now,
                    derivation_version="coverage-v1",
                    metadata_={"partial_mapping_count": 1},
                ),
                TopicSourceCoverage(
                    topic_id=topic.id,
                    source_id=sources["github"].id,
                    coverage_status=CoverageStatus.FORWARD_ONLY,
                    coverage_strategy=CoverageStrategy.FORWARD_SNAPSHOT,
                    coverage_start=now.date(),
                    coverage_end=now.date(),
                    first_observed_at=now,
                    last_observed_at=now,
                    last_successful_run_at=now,
                    observation_count=1,
                    expected_observation_count=1,
                    missing_observation_count=0,
                    derived_at=now,
                    derivation_version="coverage-v1",
                    metadata_={
                        "historical_backfill": "unavailable_by_design",
                        "partial_mapping_count": 0,
                    },
                ),
            ]
        )
        session.commit()

    settings = Settings(
        _env_file=None,
        database_url=str(migrated_engine.url),
        environment="test",
        github_token=SecretStr("fixture-token"),
        backup_path=tmp_path / "backups",
    )
    application = create_app(settings)
    application.state.engine = migrated_engine
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        operations = await client.get("/api/operations")
        coverage = await client.get("/api/coverage", params={"status": "partial"})
        topic_coverage = await client.get("/api/topics/model-context-protocol/coverage")

    assert operations.status_code == 200
    operations_payload = operations.json()
    assert operations_payload["overall_state"] == "degraded"
    assert len(operations_payload["sources"]) == 4
    assert operations_payload["sources"][0]["collector_state"] == "degraded"
    assert operations_payload["sources"][1]["collector_state"] == "healthy"
    assert operations_payload["coverage_summary"]["partial"] == 1
    assert operations_payload["coverage_summary"]["forward_only"] == 1
    assert operations_payload["data_quality"]["partial_mappings"] == 1
    assert operations_payload["data_quality"]["raw_checksum_failures"] is None
    assert operations_payload["data_protection"] == {
        "latest_backup": None,
        "latest_verified_backup": None,
        "latest_verified_backup_age_seconds": None,
        "latest_restore_drill": None,
    }

    assert coverage.status_code == 200
    assert coverage.json()["total"] == 1
    assert coverage.json()["items"][0]["coverage_status"] == "partial"

    assert topic_coverage.status_code == 200
    channels = topic_coverage.json()["channels"]
    assert channels[0]["coverage"]["coverage_status"] == "partial"
    assert channels[1]["coverage"]["coverage_status"] == "forward_only"
    assert channels[2]["collection_state"] == "not_started"
    assert channels[3]["coverage"] is None
