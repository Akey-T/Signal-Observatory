"""Minimal, source-agnostic collector framework."""

from collector_core.checkpoint import LocalCheckpointStore
from collector_core.contracts import (
    CheckpointStore,
    Collector,
    RateLimiter,
    RawStore,
    RetryPolicy,
    RunLogger,
)
from collector_core.models import CollectorContext, CollectorResult
from collector_core.rate_limiter import IntervalRateLimiter
from collector_core.raw_store import DataIntegrityError, LocalRawStore, RawRecord
from collector_core.retry import ExponentialRetryPolicy
from collector_core.run_logger import StructlogRunLogger

__all__ = [
    "CheckpointStore",
    "Collector",
    "CollectorContext",
    "CollectorResult",
    "DataIntegrityError",
    "ExponentialRetryPolicy",
    "IntervalRateLimiter",
    "LocalCheckpointStore",
    "LocalRawStore",
    "RateLimiter",
    "RawRecord",
    "RawStore",
    "RetryPolicy",
    "RunLogger",
    "StructlogRunLogger",
]
