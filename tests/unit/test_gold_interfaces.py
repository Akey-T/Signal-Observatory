from datetime import UTC, datetime
from uuid import uuid4

import pytest

from observatory_analytics import GoldMetric


def test_gold_metric_requires_a_valid_utc_window() -> None:
    metric = GoldMetric(
        topic_id=uuid4(),
        metric_name="observations",
        window_start=datetime(2026, 8, 1, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, tzinfo=UTC),
        value=10,
        definition_version="1",
    )
    assert metric.window_start.tzinfo is UTC


def test_gold_metric_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GoldMetric(
            topic_id=uuid4(),
            metric_name="observations",
            window_start=datetime(2026, 8, 1),  # noqa: DTZ001 - verifies rejection
            window_end=datetime(2026, 8, 2, tzinfo=UTC),
            value=10,
            definition_version="1",
        )
