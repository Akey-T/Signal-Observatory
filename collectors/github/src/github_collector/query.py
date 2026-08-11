"""Deterministic GitHub Repository search queries from explicit Registry mappings."""

from __future__ import annotations

from collections.abc import Mapping

from observatory_db.models import TopicSourceMapping


class GithubQueryError(ValueError):
    """Raised when an enabled mapping lacks an explicit usable query."""


class GithubRepositoryQueryBuilder:
    def from_mapping(self, mapping: TopicSourceMapping) -> tuple[str, ...]:
        configured = mapping.configuration.get("search_queries", [])
        if isinstance(configured, str):
            configured = [configured]
        if not isinstance(configured, list):
            raise GithubQueryError("GitHub mapping search_queries must be an array")
        values = tuple(self._query(value) for value in configured)
        if not values and mapping.query:
            values = (self._query(mapping.query),)
        if not values:
            raise GithubQueryError("enabled GitHub mapping requires an explicit search query")
        return tuple(dict.fromkeys(values))

    @staticmethod
    def search_parameters(query: str, *, page: int, per_page: int) -> Mapping[str, str | int]:
        return {"q": query, "sort": "stars", "order": "desc", "page": page, "per_page": per_page}

    @staticmethod
    def _query(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise GithubQueryError("GitHub search query must be a non-empty string")
        return " ".join(value.split())
