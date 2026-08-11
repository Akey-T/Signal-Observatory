"""Shared deterministic operations states."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum


class CollectorState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    NOT_INITIALIZED = "not_initialized"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    PAUSED = "paused"


class FreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    VERY_STALE = "very_stale"
    UNKNOWN = "unknown"


class OverallState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    NOT_STARTED = "not_started"


def freshness_state(
    observed_at: datetime | None,
    *,
    now: datetime,
    fresh_hours: int,
    very_stale_hours: int,
) -> FreshnessState:
    if observed_at is None:
        return FreshnessState.UNKNOWN
    reference = now.astimezone(UTC)
    observed = observed_at.astimezone(UTC)
    age_hours = max(0.0, (reference - observed).total_seconds() / 3600)
    if age_hours <= fresh_hours:
        return FreshnessState.FRESH
    if age_hours <= very_stale_hours:
        return FreshnessState.STALE
    return FreshnessState.VERY_STALE
