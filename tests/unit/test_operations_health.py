from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from observatory_db.models import IngestionRun, IngestionStatus, Source
from observatory_operations import (
    CollectorState,
    FreshnessState,
    OperationsService,
    OverallState,
    freshness_state,
)

NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(hours=12), FreshnessState.FRESH),
        (timedelta(hours=48), FreshnessState.STALE),
        (timedelta(hours=96), FreshnessState.VERY_STALE),
    ],
)
def test_freshness_states_are_threshold_driven(age: timedelta, expected: FreshnessState) -> None:
    assert (
        freshness_state(
            NOW - age,
            now=NOW,
            fresh_hours=36,
            very_stale_hours=72,
        )
        == expected
    )


def test_freshness_is_unknown_without_persisted_time() -> None:
    assert (
        freshness_state(None, now=NOW, fresh_hours=36, very_stale_hours=72)
        == FreshnessState.UNKNOWN
    )


@pytest.mark.parametrize(
    ("configured", "active_mappings", "run_status", "freshness", "expected"),
    [
        (False, 1, IngestionStatus.SUCCEEDED, FreshnessState.FRESH, CollectorState.NOT_CONFIGURED),
        (True, 1, None, FreshnessState.UNKNOWN, CollectorState.NOT_INITIALIZED),
        (True, 1, IngestionStatus.SUCCEEDED, FreshnessState.FRESH, CollectorState.HEALTHY),
        (True, 1, IngestionStatus.PARTIAL, FreshnessState.FRESH, CollectorState.DEGRADED),
        (True, 1, IngestionStatus.FAILED, FreshnessState.FRESH, CollectorState.FAILED),
        (True, 1, IngestionStatus.SUCCEEDED, FreshnessState.STALE, CollectorState.DEGRADED),
    ],
)
def test_collector_state_keeps_health_separate_from_coverage(
    configured: bool,
    active_mappings: int,
    run_status: IngestionStatus | None,
    freshness: FreshnessState,
    expected: CollectorState,
) -> None:
    source = Source(name="fixture", kind="api", is_active=True, metadata_={})
    latest = (
        IngestionRun(
            source=source,
            status=run_status,
            collector_version="test",
            metadata_={},
        )
        if run_status is not None
        else None
    )
    assert (
        OperationsService._collector_state(
            source=source,
            active_mappings=active_mappings,
            latest=latest,
            freshness=freshness,
            configured=configured,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("active_states", "partial", "unknown", "missing", "expected"),
    [
        ([], 0, 0, 0, OverallState.NOT_STARTED),
        ([CollectorState.HEALTHY], 0, 0, 0, OverallState.HEALTHY),
        ([CollectorState.HEALTHY], 1, 0, 0, OverallState.DEGRADED),
        ([CollectorState.HEALTHY], 0, 1, 0, OverallState.DEGRADED),
        ([CollectorState.HEALTHY], 0, 0, 1, OverallState.DEGRADED),
        ([CollectorState.DEGRADED], 0, 0, 0, OverallState.DEGRADED),
        ([CollectorState.FAILED], 0, 0, 0, OverallState.FAILED),
    ],
)
def test_overall_state_is_deterministic(
    active_states: list[CollectorState],
    partial: int,
    unknown: int,
    missing: int,
    expected: OverallState,
) -> None:
    active = [
        {"collector_state": state.value, "implemented": True, "enabled": True}
        for state in active_states
    ]
    coverage_summary = {
        "complete": 0,
        "partial": partial,
        "forward_only": 0,
        "empty": 0,
        "unknown": unknown,
    }
    assert (
        OperationsService._overall_state(
            active,
            coverage_summary,
            missing_snapshot_dates=missing,
        )
        == expected
    )


def test_scheduler_anomaly_degrades_an_otherwise_healthy_observatory() -> None:
    assert (
        OperationsService._overall_state(
            [{"collector_state": "healthy", "implemented": True, "enabled": True}],
            {"complete": 1, "partial": 0, "forward_only": 0, "empty": 0, "unknown": 0},
            missing_snapshot_dates=0,
            scheduler_anomalies=1,
        )
        == OverallState.DEGRADED
    )
