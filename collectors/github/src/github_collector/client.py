"""Authenticated, rate-aware client for the official GitHub REST API."""

from __future__ import annotations

import asyncio
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime

from github_collector.models import GithubHTTPResponse, GithubRateLimit, GithubRequest

TRANSIENT_STATUS_CODES = frozenset({500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "etag",
        "last-modified",
        "link",
        "location",
        "retry-after",
        "x-github-api-version-selected",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-ratelimit-resource",
        "x-ratelimit-used",
    }
)

Transport = Callable[
    [str, Mapping[str, str], float],
    Awaitable[tuple[int, Mapping[str, str], bytes, str]],
]
ResponseSink = Callable[[GithubHTTPResponse], Awaitable[None]]
AttemptSink = Callable[[int], Awaitable[None]]
Clock = Callable[[], float]
WallClock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


class GithubClientError(RuntimeError):
    """Base class for operator-visible GitHub failures."""


class GithubNotConfiguredError(GithubClientError):
    """Raised before network access when required authentication is missing."""


class GithubBudgetExhaustedError(GithubClientError):
    def __init__(self, resource: str, rate_limit: GithubRateLimit) -> None:
        super().__init__(f"GitHub {resource} rate budget is below the configured floor")
        self.resource = resource
        self.rate_limit = rate_limit


class GithubHTTPError(GithubClientError):
    def __init__(self, response: GithubHTTPResponse) -> None:
        super().__init__(f"GitHub API returned HTTP {response.status_code}")
        self.response = response


class GithubRateLimitError(GithubHTTPError):
    """Raised after Raw capture when primary or secondary limits stop a request."""


class GithubTransportError(GithubClientError):
    """Raised when no HTTP response was received after bounded retries."""


class GithubRateLimitManager:
    """Track GitHub's independent resource budgets from actual response headers."""

    def __init__(self) -> None:
        self._budgets: dict[str, GithubRateLimit] = {}

    def update(self, headers: Mapping[str, str]) -> GithubRateLimit:
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        resource = normalized.get("x-ratelimit-resource")
        rate_limit = GithubRateLimit(
            resource=resource,
            limit=self._integer(normalized.get("x-ratelimit-limit")),
            remaining=self._integer(normalized.get("x-ratelimit-remaining")),
            reset_at=self._reset_time(normalized.get("x-ratelimit-reset")),
            retry_after_seconds=self._integer(normalized.get("retry-after")),
        )
        if resource is not None:
            self._budgets[resource] = rate_limit
        return rate_limit

    def budget(self, resource: str) -> GithubRateLimit | None:
        return self._budgets.get(resource)

    def require_floor(self, resource: str, floor: int) -> None:
        budget = self.budget(resource)
        if budget is not None and budget.remaining is not None and budget.remaining <= floor:
            raise GithubBudgetExhaustedError(resource, budget)

    @staticmethod
    def _integer(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return max(0, int(value))
        except ValueError:
            return None

    @staticmethod
    def _reset_time(value: str | None) -> datetime | None:
        seconds = GithubRateLimitManager._integer(value)
        return None if seconds is None else datetime.fromtimestamp(seconds, tz=UTC)


class GithubClient:
    def __init__(
        self,
        *,
        token: str | None,
        api_version: str,
        user_agent: str,
        require_auth: bool = True,
        allow_anonymous_smoke: bool = False,
        timeout_seconds: float = 30.0,
        concurrency: int = 1,
        retry_attempts: int = 3,
        min_core_remaining: int = 100,
        min_search_remaining: int = 2,
        max_rate_limit_wait_seconds: float = 60.0,
        transport: Transport | None = None,
        wall_clock: WallClock = lambda: datetime.now(UTC),
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if require_auth and not token:
            raise GithubNotConfiguredError("GitHub authentication is not configured.")
        if not token and not allow_anonymous_smoke:
            raise GithubNotConfiguredError("GitHub authentication is not configured.")
        if not 1 <= concurrency <= 4:
            raise ValueError("GitHub concurrency must be between one and four")
        if not 1 <= retry_attempts <= 5:
            raise ValueError("GitHub retry attempts must be between one and five")
        if timeout_seconds <= 0:
            raise ValueError("GitHub timeout must be positive")
        if not api_version.strip() or not user_agent.strip():
            raise ValueError("GitHub API version and User-Agent are required")
        self._token = token
        self.api_version = api_version
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.min_core_remaining = min_core_remaining
        self.min_search_remaining = min_search_remaining
        self.max_rate_limit_wait_seconds = max_rate_limit_wait_seconds
        self.rate_limits = GithubRateLimitManager()
        self._transport = transport or self._urllib_transport
        self._wall_clock = wall_clock
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._semaphore = asyncio.Semaphore(concurrency)

    async def get(
        self,
        request: GithubRequest,
        *,
        on_response: ResponseSink,
        on_attempt: AttemptSink | None = None,
    ) -> GithubHTTPResponse:
        resource = "search" if request.endpoint_type == "repository_search" else "core"
        floor = self.min_search_remaining if resource == "search" else self.min_core_remaining
        self.rate_limits.require_floor(resource, floor)
        async with self._semaphore:
            for attempt in range(1, self.retry_attempts + 1):
                if on_attempt is not None:
                    await on_attempt(attempt)
                requested_at = self._wall_clock().astimezone(UTC)
                try:
                    status, headers, payload, final_url = await self._transport(
                        request.url, self._headers(request), self.timeout_seconds
                    )
                except (TimeoutError, ConnectionError, OSError) as error:
                    if attempt == self.retry_attempts:
                        raise GithubTransportError(
                            f"GitHub request failed after {attempt} attempt(s): "
                            f"{type(error).__name__}"
                        ) from error
                    await self._sleep(self._backoff_seconds(attempt))
                    continue

                safe_headers = safe_response_headers(headers)
                response = GithubHTTPResponse(
                    request=request,
                    status_code=status,
                    headers=safe_headers,
                    payload=payload,
                    requested_at=requested_at,
                    final_url=final_url,
                    rate_limit=self.rate_limits.update(headers),
                    attempts=attempt,
                )
                await on_response(response)
                if 200 <= status < 300 or status == 304:
                    return response
                if self._is_rate_limited(response):
                    if attempt == self.retry_attempts:
                        raise GithubRateLimitError(response)
                    wait_seconds = self._rate_wait_seconds(response, attempt)
                    if wait_seconds > self.max_rate_limit_wait_seconds:
                        raise GithubRateLimitError(response)
                    await self._sleep(wait_seconds)
                    continue
                if status in TRANSIENT_STATUS_CODES and attempt < self.retry_attempts:
                    await self._sleep(self._backoff_seconds(attempt))
                    continue
                raise GithubHTTPError(response)
        raise AssertionError("GitHub request loop ended unexpectedly")

    def _headers(self, request: GithubRequest) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.api_version,
            "User-Agent": self.user_agent,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if request.etag:
            headers["If-None-Match"] = request.etag
        return headers

    def _is_rate_limited(self, response: GithubHTTPResponse) -> bool:
        if response.status_code == 429:
            return True
        if response.status_code != 403:
            return False
        if (
            response.rate_limit.remaining == 0
            or response.rate_limit.retry_after_seconds is not None
        ):
            return True
        try:
            body = json.loads(response.payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        message = str(body.get("message", "")).casefold() if isinstance(body, dict) else ""
        return "secondary rate limit" in message or "abuse" in message

    def _rate_wait_seconds(self, response: GithubHTTPResponse, attempt: int) -> float:
        retry_after = response.rate_limit.retry_after_seconds
        if retry_after is not None:
            return float(retry_after)
        reset_at = response.rate_limit.reset_at
        if response.rate_limit.remaining == 0 and reset_at is not None:
            return max(0.0, (reset_at - self._wall_clock().astimezone(UTC)).total_seconds())
        return self._backoff_seconds(attempt)

    def _backoff_seconds(self, attempt: int) -> float:
        return min(30.0, float(2 ** (attempt - 1))) + self._jitter()

    @staticmethod
    async def _urllib_transport(
        url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        def request() -> tuple[int, Mapping[str, str], bytes, str]:
            api_request = urllib.request.Request(url, headers=dict(headers), method="GET")
            try:
                with urllib.request.urlopen(api_request, timeout=timeout_seconds) as response:
                    return (
                        response.status,
                        dict(response.headers.items()),
                        response.read(),
                        response.geturl(),
                    )
            except urllib.error.HTTPError as error:
                return error.code, dict(error.headers.items()), error.read(), error.geturl()
            except urllib.error.URLError as error:
                reason = error.reason
                if isinstance(reason, TimeoutError):
                    raise reason from error
                raise ConnectionError(str(reason)) from error

        return await asyncio.to_thread(request)


def build_url(base_url: str, path: str, parameters: Mapping[str, str | int] | None = None) -> str:
    base = base_url.rstrip("/")
    encoded = urllib.parse.urlencode(parameters or {})
    url = f"{base}/{path.lstrip('/')}"
    return f"{url}?{encoded}" if encoded else url


def next_link(headers: Mapping[str, str]) -> str | None:
    link = next((value for key, value in headers.items() if key.casefold() == "link"), None)
    if link is None:
        return None
    for item in link.split(","):
        sections = [section.strip() for section in item.split(";")]
        if len(sections) >= 2 and any(section == 'rel="next"' for section in sections[1:]):
            target = sections[0]
            if target.startswith("<") and target.endswith(">"):
                return target[1:-1]
    return None


def safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).casefold() in SAFE_RESPONSE_HEADERS
    }
