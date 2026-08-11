from __future__ import annotations

import pytest

from github_collector import GithubQueryError, GithubRepositoryQueryBuilder
from observatory_db.models import TopicSourceMapping


def test_query_builder_uses_only_explicit_registry_values() -> None:
    mapping = TopicSourceMapping(
        configuration={"search_queries": [" topic:mcp ", "org:modelcontextprotocol"]},
        query=None,
    )

    assert GithubRepositoryQueryBuilder().from_mapping(mapping) == (
        "topic:mcp",
        "org:modelcontextprotocol",
    )


def test_query_builder_deduplicates_and_never_uses_topic_aliases() -> None:
    mapping = TopicSourceMapping(
        configuration={"search_queries": ["model context protocol", "model   context protocol"]},
        query=None,
    )
    assert GithubRepositoryQueryBuilder().from_mapping(mapping) == ("model context protocol",)


def test_query_builder_rejects_missing_explicit_query() -> None:
    mapping = TopicSourceMapping(configuration={}, query=None)
    with pytest.raises(GithubQueryError):
        GithubRepositoryQueryBuilder().from_mapping(mapping)
