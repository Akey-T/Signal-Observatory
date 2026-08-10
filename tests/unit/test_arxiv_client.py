from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from arxiv_collector import ArxivClient, ArxivForbiddenError, ArxivRequest
from arxiv_collector.models import ArxivHTTPResponse


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_client_respects_minimum_interval_during_retry_and_preserves_responses() -> None:
    fake_time = FakeTime()
    starts: list[float] = []
    statuses = iter([503, 200])
    preserved: list[ArxivHTTPResponse] = []

    async def transport(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        starts.append(fake_time.monotonic())
        return next(statuses), {}, b"response"

    async def preserve(response: ArxivHTTPResponse) -> None:
        preserved.append(response)

    client = ArxivClient(
        base_url="https://export.arxiv.org/api/query",
        user_agent="Signal-Observatory/test",
        transport=transport,
        clock=fake_time.monotonic,
        wall_clock=lambda: datetime(2026, 8, 10, tzinfo=UTC),
        sleep=fake_time.sleep,
        jitter=lambda: 0,
    )
    response = await client.get(ArxivRequest(search_query='all:"test"'), on_response=preserve)

    assert response.status_code == 200
    assert [item.status_code for item in preserved] == [503, 200]
    assert starts[1] - starts[0] >= 3


@pytest.mark.asyncio
async def test_client_403_is_preserved_then_stops_without_retry() -> None:
    calls = 0
    preserved: list[ArxivHTTPResponse] = []

    async def transport(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        return 403, {}, b"forbidden"

    async def preserve(response: ArxivHTTPResponse) -> None:
        preserved.append(response)

    client = ArxivClient(
        base_url="https://export.arxiv.org/api/query",
        user_agent="Signal-Observatory/test",
        transport=transport,
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    with pytest.raises(ArxivForbiddenError, match="stopped"):
        await client.get(ArxivRequest(search_query='all:"test"'), on_response=preserve)
    assert calls == 1
    assert len(preserved) == 1


@pytest.mark.asyncio
async def test_client_uses_only_one_connection_at_a_time() -> None:
    fake_time = FakeTime()
    active = 0
    maximum_active = 0

    async def transport(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        return 200, {}, b"ok"

    async def preserve(_response: ArxivHTTPResponse) -> None:
        return None

    client = ArxivClient(
        base_url="https://export.arxiv.org/api/query",
        user_agent="Signal-Observatory/test",
        transport=transport,
        clock=fake_time.monotonic,
        sleep=fake_time.sleep,
    )
    await asyncio.gather(
        client.get(ArxivRequest(search_query='all:"one"'), on_response=preserve),
        client.get(ArxivRequest(search_query='all:"two"'), on_response=preserve),
    )
    assert maximum_active == 1
