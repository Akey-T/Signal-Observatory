from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from collector_core import CollectorContext, CollectorResult


def test_context_normalizes_timestamp_to_utc() -> None:
    context = CollectorContext(
        run_id=uuid4(),
        source="example-api",
        request_timestamp=datetime(2026, 8, 9, 13, tzinfo=timezone(timedelta(hours=10))),
        collector_version="1.0.0",
        schema_version="1",
    )

    assert context.request_timestamp == datetime(2026, 8, 9, 3, tzinfo=UTC)


def test_context_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        CollectorContext(
            run_id=uuid4(),
            source="example-api",
            request_timestamp=datetime(2026, 8, 9),  # noqa: DTZ001 - verifies rejection
            collector_version="1.0.0",
            schema_version="1",
        )


def test_result_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        CollectorResult(records_received=-1)
