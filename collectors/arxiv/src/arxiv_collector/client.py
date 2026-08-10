"""Conservative single-connection client for the official arXiv metadata API."""

from __future__ import annotations

import asyncio
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Protocol

from arxiv_collector.models import ArxivHTTPResponse, ArxivRequest, string_headers

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class ArxivClientError(RuntimeError):
    """Base class for operator-visible arXiv request failures."""


class ArxivForbiddenError(ArxivClientError):
    """A 403 must stop the current run without automatic retry."""


class ArxivHTTPError(ArxivClientError):
    def __init__(self, response: ArxivHTTPResponse) -> None:
        super().__init__(f"arXiv API returned HTTP {response.status_code}")
        self.response = response


class ArxivTransportError(ArxivClientError):
    """Raised when a response could not be received."""


class Transport(Protocol):
    async def __call__(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> tuple[int, Mapping[str, str], bytes]: ...


ResponseSink = Callable[[ArxivHTTPResponse], Awaitable[None]]
MonotonicClock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]
WallClock = Callable[[], datetime]


class MinimumIntervalLimiter:
    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: MonotonicClock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if minimum_interval_seconds < 3:
            raise ValueError("arXiv request interval cannot be less than three seconds")
        self.minimum_interval_seconds = minimum_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_request_started: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._last_request_started is not None:
                remaining = self.minimum_interval_seconds - (now - self._last_request_started)
                if remaining > 0:
                    await self._sleep(remaining)
                    now = self._clock()
            self._last_request_started = now


class ArxivClient:
    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        minimum_interval_seconds: float = 3.0,
        timeout_seconds: float = 30.0,
        retry_attempts: int = 3,
        transport: Transport | None = None,
        clock: MonotonicClock = time.monotonic,
        wall_clock: WallClock = lambda: datetime.now(UTC),
        sleep: Sleep = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if retry_attempts < 1 or retry_attempts > 5:
            raise ValueError("retry_attempts must be between one and five")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not user_agent.strip():
            raise ValueError("a descriptive arXiv User-Agent is required")
        self.base_url = base_url
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self._transport = transport or self._urllib_transport
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._jitter = jitter
        self._limiter = MinimumIntervalLimiter(minimum_interval_seconds, clock=clock, sleep=sleep)
        self._connection_lock = asyncio.Lock()

    async def get(
        self,
        request: ArxivRequest,
        *,
        on_response: ResponseSink,
    ) -> ArxivHTTPResponse:
        async with self._connection_lock:
            for attempt in range(1, self.retry_attempts + 1):
                await self._limiter.acquire()
                started = self._clock()
                requested_at = self._wall_clock().astimezone(UTC)
                try:
                    status_code, headers, body = await self._transport(
                        self._url(request),
                        {
                            "Accept": "application/atom+xml",
                            "User-Agent": self.user_agent,
                        },
                        self.timeout_seconds,
                    )
                except (TimeoutError, ConnectionError, OSError) as error:
                    if attempt == self.retry_attempts:
                        error_type = type(error).__name__
                        raise ArxivTransportError(
                            f"arXiv request failed after {attempt} attempt(s): {error_type}"
                        ) from error
                    await self._backoff(attempt)
                    continue

                response = ArxivHTTPResponse(
                    request=request,
                    status_code=status_code,
                    headers=string_headers(headers),
                    body=body,
                    requested_at=requested_at,
                    duration_ms=max(0, round((self._clock() - started) * 1000)),
                    attempt=attempt,
                )
                await on_response(response)
                if status_code == 403:
                    raise ArxivForbiddenError(
                        "arXiv API returned 403; collection stopped without retry"
                    )
                if 200 <= status_code < 300:
                    return response
                if status_code not in TRANSIENT_STATUS_CODES or attempt == self.retry_attempts:
                    raise ArxivHTTPError(response)
                await self._backoff(attempt, response.headers.get("Retry-After"))
        raise AssertionError("arXiv request loop ended unexpectedly")

    def _url(self, request: ArxivRequest) -> str:
        parameters = urllib.parse.urlencode(
            {
                "search_query": request.search_query,
                "start": request.start,
                "max_results": request.max_results,
                "sortBy": request.sort_by,
                "sortOrder": request.sort_order,
            }
        )
        return f"{self.base_url}?{parameters}"

    async def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        minimum = self._limiter.minimum_interval_seconds
        retry_after_seconds = 0.0
        if retry_after is not None:
            try:
                retry_after_seconds = max(0.0, float(retry_after))
            except ValueError:
                retry_after_seconds = 0.0
        exponential = min(30.0, minimum * (2 ** (attempt - 1)))
        delay = max(retry_after_seconds, exponential + self._jitter())
        await self._sleep(delay)

    @staticmethod
    async def _urllib_transport(
        url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        def request() -> tuple[int, Mapping[str, str], bytes]:
            api_request = urllib.request.Request(url, headers=dict(headers), method="GET")
            try:
                with urllib.request.urlopen(api_request, timeout=timeout_seconds) as response:
                    return response.status, dict(response.headers.items()), response.read()
            except urllib.error.HTTPError as error:
                return error.code, dict(error.headers.items()), error.read()
            except urllib.error.URLError as error:
                reason = error.reason
                if isinstance(reason, TimeoutError):
                    raise reason from error
                raise ConnectionError(str(reason)) from error

        return await asyncio.to_thread(request)
