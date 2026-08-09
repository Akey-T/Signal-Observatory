"""Bounded exponential retries for transient collector operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class ExponentialRetryPolicy:
    def __init__(
        self,
        *,
        attempts: int = 3,
        initial_delay_seconds: float = 0.5,
        maximum_delay_seconds: float = 8.0,
        retryable: tuple[type[Exception], ...] = (TimeoutError, ConnectionError),
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least one")
        if initial_delay_seconds < 0 or maximum_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        self.attempts = attempts
        self.initial_delay_seconds = initial_delay_seconds
        self.maximum_delay_seconds = maximum_delay_seconds
        self.retryable = retryable

    async def execute(self, operation: Callable[[], Awaitable[T]]) -> T:
        delay = self.initial_delay_seconds
        for attempt in range(1, self.attempts + 1):
            try:
                return await operation()
            except self.retryable:
                if attempt == self.attempts:
                    raise
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.maximum_delay_seconds)
        raise AssertionError("retry loop ended unexpectedly")
