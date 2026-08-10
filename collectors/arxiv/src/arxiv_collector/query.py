"""Deterministic translation from explicit Registry mappings to arXiv queries."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from observatory_db.models import TopicSourceMapping

CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")


class ArxivQueryError(ValueError):
    """Raised when a Registry mapping cannot form a safe arXiv API query."""


class ArxivQueryBuilder:
    def from_mapping(self, mapping: TopicSourceMapping) -> str:
        if not mapping.enabled:
            raise ArxivQueryError("disabled arXiv mappings cannot be queried")
        if mapping.source.name != "arxiv":
            raise ArxivQueryError("mapping source must be arxiv")
        raw_terms = mapping.configuration.get("search_terms")
        if not isinstance(raw_terms, list | tuple) or not raw_terms:
            raise ArxivQueryError("arXiv mapping requires explicit search_terms")
        terms = tuple(self._term(value) for value in raw_terms)
        if len(set(terms)) != len(terms):
            raise ArxivQueryError("arXiv mapping search_terms must be unique")
        expressions = tuple(f'all:"{term}"' for term in terms)
        return expressions[0] if len(expressions) == 1 else f"({' OR '.join(expressions)})"

    def with_submitted_window(
        self,
        query: str,
        *,
        window_from: datetime,
        window_until: datetime,
    ) -> str:
        start = self._utc(window_from)
        end = self._utc(window_until)
        if end <= start:
            raise ArxivQueryError("arXiv query window must have positive duration")
        start_value = start.strftime("%Y%m%d%H%M")
        end_value = end.strftime("%Y%m%d%H%M")
        return f"{query} AND submittedDate:[{start_value} TO {end_value}]"

    @staticmethod
    def _term(value: object) -> str:
        if not isinstance(value, str):
            raise ArxivQueryError("arXiv search terms must be strings")
        term = " ".join(value.strip().split())
        if not term:
            raise ArxivQueryError("arXiv search terms cannot be empty")
        if CONTROL_CHARACTER.search(term):
            raise ArxivQueryError("arXiv search terms cannot contain control characters")
        return term.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ArxivQueryError("arXiv query timestamps must be timezone-aware")
        return value.astimezone(UTC)
