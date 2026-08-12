from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from arxiv_collector import ArxivClient, ArxivCollectionService
from collector_core import LocalRawStore
from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivPaper,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.base import utc_now
from observatory_db.models import IngestionRun, Source, Topic, TopicSourceMapping
from signal_observatory_api.main import create_app
from signal_observatory_config import Settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv"


def add_topic(
    session: Session,
    source: Source,
    *,
    slug: str,
    mapped: bool,
) -> tuple[Topic, TopicSourceMapping | None]:
    topic = Topic(
        canonical_name=slug.replace("-", " ").title(),
        normalized_name=slug.replace("-", " "),
        slug=slug,
    )
    session.add(topic)
    if not mapped:
        session.flush()
        return topic, None
    mapping = TopicSourceMapping(
        topic=topic,
        source=source,
        enabled=True,
        mapping_type="registry",
        configuration={"search_terms": [slug.replace("-", " ")]},
    )
    session.add(mapping)
    session.flush()
    return topic, mapping


@pytest.mark.asyncio
async def test_research_api_states_summary_latest_papers_and_provenance(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    now = utc_now()
    with Session(migrated_engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        session.add(source)
        session.flush()
        live_topic, live_mapping = add_topic(
            session, source, slug="model-context-protocol", mapped=True
        )
        zero_topic, zero_mapping = add_topic(
            session, source, slug="research-with-zero-papers", mapped=True
        )
        add_topic(session, source, slug="configured-not-initialized", mapped=True)
        add_topic(session, source, slug="topic-without-arxiv", mapped=False)
        assert live_mapping is not None
        assert zero_mapping is not None
        live_mapping_id = live_mapping.id
        session.commit()

        async def transport(
            _url: str, _headers: Mapping[str, str], _timeout: float
        ) -> tuple[int, Mapping[str, str], bytes]:
            return 200, {}, (FIXTURES / "single_result.xml").read_bytes()

        client = ArxivClient(
            base_url="https://export.arxiv.org/api/query",
            user_agent="Signal-Observatory/test",
            transport=transport,  # type: ignore[arg-type]
            wall_clock=lambda: now,
        )
        runtime_settings = Settings(
            database_url=str(migrated_engine.url),
            environment="test",
            raw_data_path=tmp_path,
            arxiv_page_size=5,
            arxiv_large_query_threshold=100,
        )
        summary = await ArxivCollectionService(
            session,
            runtime_settings,
            client=client,
            raw_store=LocalRawStore(tmp_path),
            now=lambda: now,
        ).collect(topic_slugs=[live_topic.slug])
        assert summary.status == "succeeded"
        paper = session.scalar(select(ArxivPaper))
        assert paper is not None
        paper.published_at = now - timedelta(days=2)
        zero_cursor = ArxivCollectionCursor(
            topic_id=zero_topic.id,
            source_mapping_id=zero_mapping.id,
            cursor_key="incremental",
            mode="incremental",
            status=ArxivCursorStatus.SUCCEEDED,
            next_start=0,
            checkpoint={},
            last_successful_run_at=now,
            last_query_from=now - timedelta(days=2),
            last_query_until=now,
        )
        session.add(zero_cursor)
        session.commit()

    application = create_app(runtime_settings)
    application.state.engine = migrated_engine
    asgi_transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as api_client:
        live = await api_client.get("/api/topics/model-context-protocol/research")
        zero = await api_client.get("/api/topics/research-with-zero-papers/research")
        not_initialized = await api_client.get("/api/topics/configured-not-initialized/research")
        not_configured = await api_client.get("/api/topics/topic-without-arxiv/research")
        missing = await api_client.get("/api/topics/unknown-topic/research")

    assert live.status_code == 200
    live_payload = live.json()
    assert live_payload["state"] == "live"
    assert live_payload["summary"] == {
        "papers_total": 1,
        "papers_7d": 1,
        "papers_30d": 1,
        "unique_authors_30d": 2,
    }
    assert len(live_payload["latest_papers"]) == 1
    api_paper = live_payload["latest_papers"][0]
    assert api_paper["arxiv_id"] == "2608.01234"
    assert api_paper["matched_query"] == 'all:"model context protocol"'
    assert api_paper["raw_checksum"]
    assert zero.json()["state"] == "live"
    assert zero.json()["summary"]["papers_total"] == 0
    assert not_initialized.json()["state"] == "not_initialized"
    assert not_configured.json()["state"] == "not_configured"
    assert missing.status_code == 404

    with Session(migrated_engine) as session:
        stored_paper = session.scalar(
            select(ArxivPaper).where(ArxivPaper.arxiv_id == api_paper["arxiv_id"])
        )
        assert stored_paper is not None
        match = session.scalar(
            select(ArxivTopicMatch).where(ArxivTopicMatch.paper_id == stored_paper.id)
        )
        observation = session.scalar(
            select(ArxivPaperObservation).where(ArxivPaperObservation.paper_id == stored_paper.id)
        )
        assert match is not None
        assert observation is not None
        mapping = session.get(TopicSourceMapping, match.source_mapping_id)
        run = session.get(IngestionRun, match.last_ingestion_run_id)
        raw = session.get(ArxivRawResponse, observation.raw_response_id)
        assert mapping is not None
        assert run is not None
        assert raw is not None
        assert raw.payload_checksum == api_paper["raw_checksum"]
        raw_record = LocalRawStore(tmp_path).load(tmp_path / raw.raw_path)
        assert LocalRawStore(tmp_path).read(raw_record).startswith(b"<?xml")

        cursor = session.scalar(
            select(ArxivCollectionCursor).where(
                ArxivCollectionCursor.source_mapping_id == live_mapping_id,
                ArxivCollectionCursor.cursor_key == "incremental",
            )
        )
        assert cursor is not None
        cursor.status = ArxivCursorStatus.FAILED
        cursor.last_error = "temporary upstream failure"
        session.commit()

    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as api_client:
        degraded = await api_client.get("/api/topics/model-context-protocol/research")
    assert degraded.json()["state"] == "degraded"
    assert degraded.json()["collector_error"] == "temporary upstream failure"
    assert degraded.json()["summary"]["papers_total"] == 1
