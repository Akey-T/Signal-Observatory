"""Truthful Topic Developer observations derived from persisted GitHub snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from github_collector import GithubQueryService
from signal_observatory_api.topics import application_settings, database_session
from signal_observatory_config import Settings

router = APIRouter(prefix="/api/topics", tags=["development"])


class DevelopmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DevelopmentTopicResponse(DevelopmentModel):
    slug: str
    canonical_name: str


class DevelopmentSummaryResponse(DevelopmentModel):
    repositories_tracked: int
    stars_total: int
    forks_total: int
    repositories_pushed_30d: int
    stars_delta_since_previous_snapshot: int | None
    forks_delta_since_previous_snapshot: int | None
    previous_snapshot_at: datetime | None
    latest_snapshot_at: datetime | None


class DevelopmentMatchEvidenceResponse(DevelopmentModel):
    matched_query: str
    source_mapping_id: str
    discovery_rank: int
    discovery_run_id: str
    raw_checksum: str | None


class DevelopmentRepositoryResponse(DevelopmentModel):
    github_repository_id: int
    full_name: str
    description: str | None
    html_url: str
    language: str | None
    stars: int | None
    forks: int | None
    pushed_at: datetime | None
    archived: bool
    disabled: bool
    latest_snapshot_at: datetime | None
    previous_snapshot_at: datetime | None
    stars_delta: int | None
    forks_delta: int | None
    match_evidence: list[DevelopmentMatchEvidenceResponse]


class TopicDevelopmentResponse(DevelopmentModel):
    topic: DevelopmentTopicResponse
    source: Literal["github"]
    state: Literal["not_configured", "not_initialized", "live", "degraded"]
    last_snapshot_at: datetime | None
    last_successful_snapshot_at: datetime | None
    collector_error: str | None
    summary: DevelopmentSummaryResponse
    top_repositories: list[DevelopmentRepositoryResponse]


@router.get("/{slug}/development", response_model=TopicDevelopmentResponse)
def topic_development(
    slug: str,
    session: Annotated[Session, Depends(database_session)],
    settings: Annotated[Settings, Depends(application_settings)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> TopicDevelopmentResponse:
    result = GithubQueryService(session, settings).development(slug, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    return TopicDevelopmentResponse.model_validate(result)
