from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from signal_observatory_api.main import create_app
from signal_observatory_config import Settings
from topic_registry.loader import TopicRegistryLoader
from topic_registry.sync import TopicRegistrySyncService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "topic_registry"


@pytest.mark.asyncio
async def test_read_only_topic_endpoints(migrated_engine: Engine) -> None:
    registry = TopicRegistryLoader(FIXTURES / "valid").load()
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(registry, applied_by="api-test")

    application = create_app(Settings(database_url=str(migrated_engine.url), environment="test"))
    application.state.engine = migrated_engine
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listing = await client.get("/api/topics", params={"search": "MCP"})
        canonical_search = await client.get(
            "/api/topics", params={"search": "Model Context", "category": "ai-systems"}
        )
        status_filter = await client.get("/api/topics", params={"status": "active"})
        pagination = await client.get("/api/topics", params={"limit": 1, "offset": 1})
        detail = await client.get("/api/topics/model-context-protocol")
        categories = await client.get("/api/categories")
        status = await client.get("/api/topic-registry/status")
        missing = await client.get("/api/topics/not-present")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert canonical_search.json()["total"] == 1
    assert status_filter.json()["total"] == 1
    assert pagination.json()["total"] == 1
    assert pagination.json()["items"] == []
    assert detail.status_code == 200
    assert detail.json()["aliases"][0]["value"] == "MCP"
    assert {item["source"] for item in detail.json()["sources"]} == {"github", "wikipedia"}
    assert categories.json()[0]["slug"] == "ai-systems"
    assert status.json()["version"] == 1
    assert missing.status_code == 404
