"""Truthful Topic Research observations derived from persisted Silver data."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from arxiv_collector import ArxivQueryService
from signal_observatory_api.topics import database_session

router = APIRouter(prefix="/api/topics", tags=["research"])


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchTopicResponse(ResearchModel):
    slug: str
    canonical_name: str


class ResearchSummaryResponse(ResearchModel):
    papers_total: int
    papers_7d: int
    papers_30d: int
    unique_authors_30d: int


class ResearchPaperResponse(ResearchModel):
    arxiv_id: str
    title: str
    authors: list[str]
    published_at: datetime
    updated_at: datetime
    primary_category: str
    categories: list[str]
    abstract: str
    abs_url: str
    matched_query: str
    source_mapping_id: str
    ingestion_run_id: str
    raw_checksum: str | None


class TopicResearchResponse(ResearchModel):
    topic: ResearchTopicResponse
    source: Literal["arxiv"]
    state: Literal["not_configured", "not_initialized", "live", "degraded"]
    last_observed_at: datetime | None
    collector_error: str | None
    summary: ResearchSummaryResponse
    latest_papers: list[ResearchPaperResponse]


@router.get("/{slug}/research", response_model=TopicResearchResponse)
def topic_research(
    slug: str,
    session: Annotated[Session, Depends(database_session)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> TopicResearchResponse:
    result = ArxivQueryService(session).research(slug, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    return TopicResearchResponse.model_validate(result)
