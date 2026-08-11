from __future__ import annotations

from pathlib import Path

import pytest

from github_collector import GithubJsonParser, GithubParseError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"


def test_parse_repository_uses_numeric_identity_and_distinct_subscribers() -> None:
    repository = GithubJsonParser().parse_repository((FIXTURES / "repository.json").read_bytes())

    assert repository.github_repository_id == 1001
    assert repository.full_name == "modelcontextprotocol/servers"
    assert repository.stargazers_count == 12800
    assert repository.subscribers_count == 210
    assert repository.topics == ("model-context-protocol", "mcp")


def test_parse_search_preserves_fork_parent_and_order() -> None:
    result = GithubJsonParser().parse_search((FIXTURES / "search_multiple.json").read_bytes())

    assert result.total_count == 3
    assert [repository.github_repository_id for repository in result.repositories] == [
        1001,
        1002,
        1003,
    ]
    assert result.repositories[-1].is_fork is True
    assert result.repositories[-1].fork_parent_github_id == 1001


def test_parse_empty_search_and_reject_malformed_payload() -> None:
    parser = GithubJsonParser()
    assert parser.parse_search((FIXTURES / "search_empty.json").read_bytes()).repositories == ()
    with pytest.raises(GithubParseError):
        parser.parse_search(b"not json")
