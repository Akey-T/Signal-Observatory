from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from tests.integration.test_github_discovery import FakeWallClock, add_mapping, client, settings

from collector_core import LocalRawStore
from github_collector import GithubCollectionService
from observatory_db.github_models import (
    GithubRawResponse,
    GithubRepository,
    GithubRepositorySnapshot,
    GithubTopicRepositoryMatch,
)
from observatory_db.models import (
    IngestionRun,
    IngestionStatus,
    Source,
    Topic,
    TopicSourceMapping,
)
from signal_observatory_api.main import create_app

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"


@pytest.mark.asyncio
async def test_development_api_states_aggregates_delta_and_full_provenance(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))

    async def search_transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        fixture = "search_empty.json" if "zero-results" in url else "search_single.json"
        return (
            200,
            {"X-RateLimit-Remaining": "20", "X-RateLimit-Resource": "search"},
            (FIXTURES / fixture).read_bytes(),
            url,
        )

    snapshot_call = 0

    async def snapshot_transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        nonlocal snapshot_call
        snapshot_call += 1
        fixture = "repository.json" if snapshot_call == 1 else "repository_changed.json"
        etag = '"repo-v1"' if snapshot_call == 1 else '"repo-v2"'
        return (
            200,
            {"ETag": etag, "X-RateLimit-Remaining": "4990", "X-RateLimit-Resource": "core"},
            (FIXTURES / fixture).read_bytes(),
            url,
        )

    runtime_settings = settings(tmp_path)
    runtime_settings.database_url = str(migrated_engine.url)
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        live_mapping = add_mapping(
            session, source, slug="model-context-protocol", query="model context protocol"
        )
        live_mapping_id = live_mapping.id
        add_mapping(session, source, slug="zero-results", query="zero-results")
        add_mapping(session, source, slug="not-initialized", query="not-initialized")
        session.add(
            Topic(
                canonical_name="No GitHub Mapping",
                normalized_name="no github mapping",
                slug="no-github-mapping",
            )
        )
        session.commit()
        await GithubCollectionService(
            session,
            runtime_settings,
            client=client(search_transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        ).discover(topic_slugs=["model-context-protocol", "zero-results"], max_results=1)
        snapshot_service = GithubCollectionService(
            session,
            runtime_settings,
            client=client(snapshot_transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        await snapshot_service.snapshot(topic_slugs=["model-context-protocol"])
        clock.advance(timedelta(days=1))
        second_snapshot = await snapshot_service.snapshot(topic_slugs=["model-context-protocol"])
        assert second_snapshot.run_id is not None

    application = create_app(runtime_settings)
    application.state.engine = migrated_engine
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        source_status = await api_client.get("/api/sources/github/status")
        live = await api_client.get("/api/topics/model-context-protocol/development")
        zero = await api_client.get("/api/topics/zero-results/development")
        not_initialized = await api_client.get("/api/topics/not-initialized/development")
        not_configured = await api_client.get("/api/topics/no-github-mapping/development")
        missing = await api_client.get("/api/topics/unknown/development")

    assert source_status.status_code == 200
    assert source_status.json()["collector_state"] == "healthy"
    assert source_status.json()["tracked_repositories"] == 1
    payload = live.json()
    assert payload["state"] == "live"
    assert payload["summary"]["repositories_tracked"] == 1
    assert payload["summary"]["stars_total"] == 12950
    assert payload["summary"]["forks_total"] == 1420
    assert payload["summary"]["stars_delta_since_previous_snapshot"] == 150
    assert payload["summary"]["forks_delta_since_previous_snapshot"] == 20
    assert payload["summary"]["previous_snapshot_at"] is not None
    assert len(payload["top_repositories"]) == 1
    evidence = payload["top_repositories"][0]["match_evidence"][0]
    assert evidence["matched_query"] == "model context protocol is:public fork:false"
    assert evidence["source_mapping_id"] == str(live_mapping_id)
    assert evidence["raw_checksum"]
    assert zero.json()["state"] == "live"
    assert zero.json()["summary"]["repositories_tracked"] == 0
    assert not_initialized.json()["state"] == "not_initialized"
    assert not_configured.json()["state"] == "not_configured"
    assert missing.status_code == 404

    with Session(migrated_engine) as session:
        repository = session.scalar(select(GithubRepository))
        match = session.scalar(select(GithubTopicRepositoryMatch))
        latest_snapshot = session.scalar(
            select(GithubRepositorySnapshot)
            .order_by(GithubRepositorySnapshot.observed_at.desc())
            .limit(1)
        )
        assert repository is not None
        assert match is not None
        assert latest_snapshot is not None
        mapping = session.get(TopicSourceMapping, match.source_mapping_id)
        run = session.get(IngestionRun, match.last_ingestion_run_id)
        raw_id = match.metadata_["raw_response_id"]
        raw = session.get(GithubRawResponse, UUID(str(raw_id)))
        assert mapping is not None
        assert run is not None
        assert raw is not None
        assert raw.payload_checksum == evidence["raw_checksum"]
        assert LocalRawStore(tmp_path).read(LocalRawStore(tmp_path).load(tmp_path / raw.raw_path))

        last_run = session.get(IngestionRun, second_snapshot.run_id)
        assert last_run is not None
        last_run.status = IngestionStatus.PARTIAL
        last_run.error_count = 1
        session.commit()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        degraded = await api_client.get("/api/topics/model-context-protocol/development")
    assert degraded.json()["state"] == "degraded"
    assert degraded.json()["summary"]["repositories_tracked"] == 1


@pytest.mark.asyncio
async def test_github_status_is_not_configured_without_token(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    runtime_settings = settings(tmp_path)
    runtime_settings.github_token = None
    with Session(migrated_engine) as session:
        session.add(Source(name="github", kind="api", metadata_={}))
        session.commit()
    application = create_app(runtime_settings)
    application.state.engine = migrated_engine
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        response = await api_client.get("/api/sources/github/status")
    assert response.status_code == 200
    assert response.json()["collector_state"] == "not_configured"
    assert response.json()["auth_configured"] is False
