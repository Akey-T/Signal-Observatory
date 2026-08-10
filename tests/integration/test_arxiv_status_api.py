from __future__ import annotations

import httpx
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from observatory_db.models import Source, Topic, TopicSourceMapping
from signal_observatory_api.main import create_app
from signal_observatory_config import Settings


@pytest.mark.asyncio
async def test_arxiv_status_is_not_initialized_before_collection(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        topic = Topic(
            canonical_name="Model Context Protocol",
            normalized_name="model context protocol",
            slug="model-context-protocol",
        )
        session.add_all(
            [
                source,
                topic,
                TopicSourceMapping(
                    topic=topic,
                    source=source,
                    enabled=True,
                    mapping_type="registry",
                    configuration={"search_terms": ["model context protocol"]},
                ),
            ]
        )
        session.commit()

    application = create_app(Settings(database_url=str(migrated_engine.url), environment="test"))
    application.state.engine = migrated_engine
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/sources/arxiv/status")

    assert response.status_code == 200
    assert response.json() == {
        "source": "arxiv",
        "enabled": True,
        "collector_state": "not_initialized",
        "last_run_at": None,
        "last_successful_run_at": None,
        "last_run_status": None,
        "tracked_topics": 1,
        "tracked_mappings": 1,
        "papers_observed": 0,
        "last_24h_new_papers": 0,
        "error_count_last_run": 0,
    }
