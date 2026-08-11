from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from github_collector import (
    GithubBudgetExhaustedError,
    GithubClient,
    GithubHTTPError,
    GithubHTTPResponse,
    GithubNotConfiguredError,
    GithubRateLimitError,
    GithubRateLimitManager,
    GithubRequest,
    next_link,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"
NOW = datetime(2026, 8, 11, 2, tzinfo=UTC)


def request(*, endpoint: str = "repository", etag: str | None = None) -> GithubRequest:
    return GithubRequest(
        endpoint_type=endpoint,
        url="https://api.github.com/repos/modelcontextprotocol/servers",
        github_repository_id=1001,
        etag=etag,
    )


@pytest.mark.asyncio
async def test_authentication_is_required_by_default_and_never_returned() -> None:
    with pytest.raises(GithubNotConfiguredError):
        GithubClient(token=None, api_version="2022-11-28", user_agent="Signal Observatory test")

    observed_headers: dict[str, str] = {}

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        observed_headers.update(headers)
        return 200, {"ETag": '"repo-v1"'}, b"{}", url

    responses: list[GithubHTTPResponse] = []

    async def capture_response(value: GithubHTTPResponse) -> None:
        responses.append(value)

    client = GithubClient(
        token="secret-value",
        api_version="2022-11-28",
        user_agent="Signal Observatory test",
        min_core_remaining=0,
        transport=transport,
    )
    response = await client.get(request(), on_response=capture_response)

    assert observed_headers["Authorization"] == "Bearer secret-value"
    assert observed_headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert "Authorization" not in response.headers
    assert "secret-value" not in repr(response)


@pytest.mark.asyncio
async def test_conditional_request_sends_etag_and_accepts_304() -> None:
    seen: dict[str, str] = {}

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        seen.update(headers)
        return 304, {"ETag": '"repo-v1"'}, b"", url

    client = GithubClient(
        token="token",
        api_version="2022-11-28",
        user_agent="Signal Observatory test",
        min_core_remaining=0,
        transport=transport,
    )
    response = await client.get(request(etag='"repo-v1"'), on_response=lambda value: _done())
    assert seen["If-None-Match"] == '"repo-v1"'
    assert response.status_code == 304


@pytest.mark.asyncio
async def test_retry_after_and_secondary_rate_limit_are_honored() -> None:
    calls = 0
    sleeps: list[float] = []

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return (
                403,
                {
                    "Retry-After": "3",
                    "X-RateLimit-Remaining": "20",
                    "X-RateLimit-Resource": "core",
                },
                (FIXTURES / "rate_limit_secondary.json").read_bytes(),
                url,
            )
        return 200, {"X-RateLimit-Remaining": "19", "X-RateLimit-Resource": "core"}, b"{}", url

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = GithubClient(
        token="token",
        api_version="2022-11-28",
        user_agent="Signal Observatory test",
        min_core_remaining=0,
        transport=transport,
        sleep=sleep,
    )
    received: list[GithubHTTPResponse] = []

    async def capture_response(value: GithubHTTPResponse) -> None:
        received.append(value)

    response = await client.get(request(), on_response=capture_response)
    assert response.status_code == 200
    assert [item.status_code for item in received] == [403, 200]
    assert sleeps == [3.0]


@pytest.mark.asyncio
async def test_primary_reset_wait_and_429_are_bounded() -> None:
    calls = 0
    sleeps: list[float] = []

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return (
                429,
                {
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(round((NOW + timedelta(seconds=2)).timestamp())),
                    "X-RateLimit-Resource": "core",
                },
                (FIXTURES / "rate_limit_primary.json").read_bytes(),
                url,
            )
        return 200, {"X-RateLimit-Remaining": "10", "X-RateLimit-Resource": "core"}, b"{}", url

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = GithubClient(
        token="token",
        api_version="2022-11-28",
        user_agent="Signal Observatory test",
        min_core_remaining=0,
        transport=transport,
        wall_clock=lambda: NOW,
        sleep=sleep,
    )
    await client.get(request(), on_response=lambda value: _done())
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_403_is_not_always_a_rate_limit() -> None:
    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        return 403, {"X-RateLimit-Remaining": "50"}, b'{"message":"Forbidden"}', url

    client = GithubClient(
        token="token",
        api_version="2022-11-28",
        user_agent="Signal Observatory test",
        min_core_remaining=0,
        transport=transport,
    )
    with pytest.raises(GithubHTTPError) as captured:
        await client.get(request(), on_response=lambda value: _done())
    assert not isinstance(captured.value, GithubRateLimitError)


@pytest.mark.asyncio
async def test_search_floor_stops_discovery_without_blocking_core() -> None:
    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        return 200, {"X-RateLimit-Remaining": "499", "X-RateLimit-Resource": "core"}, b"{}", url

    client = GithubClient(
        token="token",
        api_version="2022-11-28",
        user_agent="Signal Observatory test",
        min_core_remaining=100,
        min_search_remaining=2,
        transport=transport,
    )
    client.rate_limits.update({"X-RateLimit-Remaining": "2", "X-RateLimit-Resource": "search"})
    with pytest.raises(GithubBudgetExhaustedError):
        await client.get(request(endpoint="repository_search"), on_response=lambda value: _done())
    assert (await client.get(request(), on_response=lambda value: _done())).status_code == 200


def test_rate_headers_and_official_link_pagination_are_parsed() -> None:
    headers = json.loads((FIXTURES / "headers.json").read_text(encoding="utf-8"))
    manager = GithubRateLimitManager()
    search = manager.update(headers["search_page_1"])
    core = manager.update(headers["repository"])

    assert search.resource == "search"
    assert search.remaining == 29
    assert core.resource == "core"
    assert core.limit == 5000
    assert next_link(headers["search_page_1"]) == (
        "https://api.github.com/search/repositories?q=mcp&page=2"
    )


async def _done() -> None:
    return None
