"""Validated values exchanged inside the GitHub Developer Collector."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GithubValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GithubRateLimit(GithubValue):
    resource: str | None = None
    limit: int | None = Field(default=None, ge=0)
    remaining: int | None = Field(default=None, ge=0)
    reset_at: datetime | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0)

    @field_validator("reset_at")
    @classmethod
    def reset_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("rate reset must be timezone-aware")
        return value.astimezone(UTC)


class GithubRequest(GithubValue):
    endpoint_type: Literal["repository_search", "repository"]
    url: str
    query_parameters: dict[str, str | int] = Field(default_factory=dict)
    github_repository_id: int | None = None
    etag: str | None = None


class GithubHTTPResponse(GithubValue):
    request: GithubRequest
    status_code: int
    headers: dict[str, str]
    payload: bytes
    requested_at: datetime
    final_url: str
    rate_limit: GithubRateLimit
    attempts: int = Field(ge=1)

    @field_validator("requested_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        return value.astimezone(UTC)


class GithubRepositoryData(GithubValue):
    github_repository_id: int
    node_id: str
    owner_login: str
    name: str
    full_name: str
    html_url: str
    api_url: str
    description: str | None
    homepage: str | None
    language: str | None
    default_branch: str | None
    is_fork: bool
    fork_parent_github_id: int | None
    archived: bool
    disabled: bool
    visibility: str
    created_at_github: datetime
    updated_at_github: datetime
    pushed_at_github: datetime | None
    stargazers_count: int = Field(ge=0)
    forks_count: int = Field(ge=0)
    open_issues_count: int = Field(ge=0)
    subscribers_count: int = Field(ge=0)
    size_kb: int = Field(ge=0)
    topics: tuple[str, ...]
    license_spdx: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at_github", "updated_at_github", "pushed_at_github")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("GitHub timestamps must be timezone-aware")
        return value.astimezone(UTC)


class GithubSearchResult(GithubValue):
    total_count: int = Field(ge=0)
    incomplete_results: bool
    repositories: tuple[GithubRepositoryData, ...]
