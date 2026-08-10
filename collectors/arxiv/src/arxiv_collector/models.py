"""Typed values exchanged by the arXiv client, parser, and persistence layer."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArxivValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArxivRequest(ArxivValue):
    search_query: str = Field(min_length=1)
    start: int = Field(default=0, ge=0)
    max_results: int = Field(default=100, ge=1, le=2000)
    sort_by: str = Field(
        default="lastUpdatedDate", pattern=r"^(relevance|lastUpdatedDate|submittedDate)$"
    )
    sort_order: str = Field(default="ascending", pattern=r"^(ascending|descending)$")


class ArxivHTTPResponse(ArxivValue):
    request: ArxivRequest
    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes
    requested_at: datetime
    duration_ms: int = Field(ge=0)
    attempt: int = Field(ge=1)

    @field_validator("requested_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        return value.astimezone(UTC)


class ParsedArxivArticle(ArxivValue):
    arxiv_id: str
    latest_version: int | None
    title: str
    abstract: str
    published_at: datetime
    updated_at: datetime
    authors: tuple[str, ...]
    categories: tuple[str, ...]
    primary_category: str
    comment: str | None = None
    journal_ref: str | None = None
    doi: str | None = None
    license_url: str | None = None
    abs_url: str
    pdf_url: str | None = None
    is_withdrawn: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at", "updated_at")
    @classmethod
    def article_timestamps_are_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("article timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ParsedArxivFeed(ArxivValue):
    total_results: int = Field(ge=0)
    start_index: int = Field(ge=0)
    items_per_page: int = Field(ge=0)
    articles: tuple[ParsedArxivArticle, ...]
    feed_id: str | None = None
    feed_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("feed_updated_at")
    @classmethod
    def feed_timestamp_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("feed timestamp must be timezone-aware")
        return value.astimezone(UTC)


class PersistenceCounts(ArxivValue):
    papers_inserted: int = Field(default=0, ge=0)
    papers_updated: int = Field(default=0, ge=0)
    papers_existing: int = Field(default=0, ge=0)
    topic_matches_added: int = Field(default=0, ge=0)
    duplicate_papers: int = Field(default=0, ge=0)

    def add(self, other: PersistenceCounts) -> PersistenceCounts:
        return PersistenceCounts(
            papers_inserted=self.papers_inserted + other.papers_inserted,
            papers_updated=self.papers_updated + other.papers_updated,
            papers_existing=self.papers_existing + other.papers_existing,
            topic_matches_added=self.topic_matches_added + other.topic_matches_added,
            duplicate_papers=self.duplicate_papers + other.duplicate_papers,
        )


def string_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Copy response headers into a JSON-safe, case-preserving mapping."""

    return {str(key): str(value) for key, value in headers.items()}
