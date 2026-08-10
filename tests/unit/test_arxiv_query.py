from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arxiv_collector import ArxivQueryBuilder, ArxivQueryError
from observatory_db.models import Source, TopicSourceMapping


def mapping(*terms: object, enabled: bool = True, source: str = "arxiv") -> TopicSourceMapping:
    return TopicSourceMapping(
        enabled=enabled,
        source=Source(name=source, kind="api", metadata_={}),
        configuration={"search_terms": list(terms)},
    )


def test_query_builder_preserves_explicit_registry_terms_deterministically() -> None:
    builder = ArxivQueryBuilder()
    source_mapping = mapping("model context protocol", 'tool "calling"')
    expected = r'(all:"model context protocol" OR all:"tool \"calling\"")'
    assert builder.from_mapping(source_mapping) == expected
    assert builder.from_mapping(source_mapping) == expected


def test_query_builder_adds_utc_submitted_window() -> None:
    query = ArxivQueryBuilder().with_submitted_window(
        'all:"retrieval augmented generation"',
        window_from=datetime(2026, 1, 1, tzinfo=UTC),
        window_until=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert query.endswith("submittedDate:[202601010000 TO 202602010000]")


@pytest.mark.parametrize(
    "source_mapping",
    [
        mapping("term", enabled=False),
        mapping("term", source="github"),
        mapping(),
        mapping(""),
        mapping("same", "same"),
        mapping(42),
    ],
)
def test_query_builder_rejects_disabled_or_invalid_mapping(
    source_mapping: TopicSourceMapping,
) -> None:
    with pytest.raises(ArxivQueryError):
        ArxivQueryBuilder().from_mapping(source_mapping)
