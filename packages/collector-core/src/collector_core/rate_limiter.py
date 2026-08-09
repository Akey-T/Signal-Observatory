"""In-process minimum-interval rate limiter."""

from __future__ import annotations

import asyncio
import time


class IntervalRateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._minimum_interval = 1 / requests_per_second
        self._last_acquired = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._minimum_interval - (now - self._last_acquired)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_acquired = time.monotonic()
