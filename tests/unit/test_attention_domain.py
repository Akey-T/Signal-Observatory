from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from attention_domain import (
    AttentionChannel,
    AttentionCoverageContract,
    AttentionDocumentIdentity,
    AttentionMetricDefinition,
    AttentionObservationIdentity,
    CanonicalEntity,
    CanonicalEvent,
    EntityType,
    EventCreationMethod,
)
from observatory_db.coverage_models import CoverageStrategy


def test_attention_concepts_are_distinct_and_metrics_are_explicit() -> None:
    metric = AttentionMetricDefinition(
        name="media_match_count",
        channel=AttentionChannel.MEDIA,
        unit="articles",
        description="Number of monitored media matches in a closed interval.",
        definition_version="media-count-v1",
    )

    assert metric.name == "MEDIA_MATCH_COUNT"
    metric.validate_unit("articles")
    with pytest.raises(ValueError, match="requires unit"):
        metric.validate_unit("pageviews")
    assert AttentionDocumentIdentity("gdelt", "url-sha256:abc").source_name == "gdelt"
    assert CanonicalEntity(EntityType.COMPANY, "OpenAI", "openai").canonical_name != metric.name


def test_metric_definition_rejects_analytical_scores() -> None:
    with pytest.raises(ValueError, match="outside E05"):
        AttentionMetricDefinition(
            name="Trend Score",
            channel=AttentionChannel.MEDIA,
            unit="score",
            description="Not a source observation.",
            definition_version="test-v1",
        )


def test_observation_identity_normalizes_utc_and_requires_a_real_window() -> None:
    start = datetime(2026, 9, 7, 10, tzinfo=timezone(timedelta(hours=10)))
    identity = AttentionObservationIdentity(
        topic_id=uuid4(),
        source_id=uuid4(),
        source_mapping_id=uuid4(),
        channel=AttentionChannel.MEDIA,
        metric_name="media_match_count",
        window_start=start,
        window_end=start + timedelta(hours=1),
    )

    assert identity.window_start.tzinfo is UTC
    assert identity.window_start.hour == 0
    assert identity.metric_name == "MEDIA_MATCH_COUNT"
    with pytest.raises(ValueError, match="window_end must be after"):
        AttentionObservationIdentity(
            topic_id=identity.topic_id,
            source_id=identity.source_id,
            source_mapping_id=identity.source_mapping_id,
            channel=identity.channel,
            metric_name=identity.metric_name,
            window_start=start,
            window_end=start,
        )


def test_canonical_events_require_curated_creation() -> None:
    event = CanonicalEvent("Housing subsidy announced", started_at=datetime(2026, 9, 7, tzinfo=UTC))
    assert event.creation_method is EventCreationMethod.CURATED
    with pytest.raises(ValueError, match="require review"):
        CanonicalEvent(
            "Candidate event",
            creation_method=EventCreationMethod.SYSTEM_CANDIDATE,
        )


def test_attention_coverage_reuses_existing_strategy_values() -> None:
    start = datetime(2026, 9, 7, tzinfo=UTC)
    contract = AttentionCoverageContract(
        strategy=CoverageStrategy.HISTORICAL_PLUS_FORWARD,
        expected_window_seconds=3600,
        supports_bounded_history=True,
        observed_windows=((start, start + timedelta(hours=1)),),
        missing_windows=((start + timedelta(hours=1), start + timedelta(hours=2)),),
        partial_windows=((start + timedelta(hours=2), start + timedelta(hours=3)),),
    )
    assert contract.strategy is CoverageStrategy.HISTORICAL_PLUS_FORWARD
    assert contract.observed_windows[0][0].tzinfo is UTC
    assert len(contract.missing_windows) == 1
    assert len(contract.partial_windows) == 1
    with pytest.raises(ValueError, match="bounded history"):
        AttentionCoverageContract(strategy=CoverageStrategy.HISTORICAL_PLUS_FORWARD)
