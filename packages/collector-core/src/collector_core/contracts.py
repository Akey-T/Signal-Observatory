"""Narrow framework contracts required by future source collectors."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any, Protocol, TypeVar

from collector_core.models import CollectorContext, CollectorResult
from collector_core.raw_store import RawRecord

T = TypeVar("T")


class Collector(Protocol):
    name: str
    version: str

    async def collect(self, context: CollectorContext) -> CollectorResult: ...


class CheckpointStore(Protocol):
    def get(self, source: str) -> Mapping[str, Any] | None: ...

    def set(self, source: str, checkpoint: Mapping[str, Any]) -> None: ...


class RateLimiter(Protocol):
    async def acquire(self) -> None: ...


class RetryPolicy(Protocol):
    async def execute(self, operation: Callable[[], Awaitable[T]]) -> T: ...


class RawStore(Protocol):
    def write(
        self,
        *,
        source: str,
        payload: bytes,
        request_timestamp: datetime,
        collector_version: str,
        schema_version: str,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> RawRecord: ...

    def read(self, record: RawRecord) -> bytes: ...


class RunLogger(Protocol):
    def started(self, context: CollectorContext) -> None: ...

    def completed(self, context: CollectorContext, result: CollectorResult) -> None: ...

    def failed(self, context: CollectorContext, error: BaseException) -> None: ...
