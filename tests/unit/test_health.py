import httpx
import pytest

from signal_observatory_api.main import create_app
from signal_observatory_config import Settings


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    application = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", environment="test")
    )
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "api", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_readiness_is_unavailable_before_lifespan_startup() -> None:
    application = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", environment="test")
    )
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


@pytest.mark.asyncio
async def test_readiness_is_healthy_during_validated_lifespan() -> None:
    application = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", environment="test")
    )
    transport = httpx.ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert application.state.ready is False
