"""Read-only operational health and coverage endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from observatory_db.coverage_models import CoverageStatus
from observatory_operations import CoverageQueryService, OperationsService
from signal_observatory_api.topics import application_settings, database_session
from signal_observatory_config import Settings

router = APIRouter(prefix="/api", tags=["operations"])


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoverageTopic(APIModel):
    id: str
    slug: str
    canonical_name: str


class CoverageItem(APIModel):
    topic: CoverageTopic
    source: str
    coverage_status: str
    coverage_strategy: str
    coverage_start: date | None
    coverage_end: date | None
    target_start: date | None
    target_end: date | None
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    last_successful_run_at: datetime | None
    observation_count: int
    expected_observation_count: int | None
    missing_observation_count: int
    partial_reason: str | None
    freshness: str
    derived_at: datetime
    derivation_version: str
    metadata: dict[str, Any]


class CoverageListResponse(APIModel):
    items: list[CoverageItem]
    total: int
    limit: int
    offset: int
    generated_at: datetime
    derivation_version: str


class TopicCoverageChannel(APIModel):
    channel: str
    label: str
    source: str
    collection_state: str
    coverage: CoverageItem | None


class TopicCoverageTopic(APIModel):
    slug: str
    canonical_name: str


class TopicCoverageResponse(APIModel):
    topic: TopicCoverageTopic
    channels: list[TopicCoverageChannel]
    generated_at: datetime


class SourceOperationalHealth(APIModel):
    source: str
    channel: str
    label: str
    display_name: str
    implemented: bool
    enabled: bool
    collector_state: str
    last_run_at: datetime | None
    last_successful_run_at: datetime | None
    latest_run_status: str | None
    active_mappings: int
    failed_mappings: int
    partial_mappings: int
    stale_mappings: int
    errors_last_run: int
    raw_responses_last_run: int
    freshness: str
    details: dict[str, Any]


class OperationsResponse(APIModel):
    overall_state: str
    explanation: str
    registry: dict[str, Any]
    sources: list[SourceOperationalHealth]
    coverage_summary: dict[str, int]
    data_quality: dict[str, Any]
    generated_at: datetime


@router.get("/operations", response_model=OperationsResponse)
def operations_overview(
    session: Annotated[Session, Depends(database_session)],
    settings: Annotated[Settings, Depends(application_settings)],
) -> OperationsResponse:
    return OperationsResponse.model_validate(OperationsService(session, settings).overview())


@router.get("/coverage", response_model=CoverageListResponse)
def coverage_list(
    session: Annotated[Session, Depends(database_session)],
    settings: Annotated[Settings, Depends(application_settings)],
    source: str | None = None,
    coverage_status: Annotated[CoverageStatus | None, Query(alias="status")] = None,
    topic: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CoverageListResponse:
    payload = CoverageQueryService(session, settings).list(
        source=source,
        status=coverage_status,
        topic=topic,
        limit=limit,
        offset=offset,
    )
    return CoverageListResponse.model_validate(payload)


@router.get("/topics/{slug}/coverage", response_model=TopicCoverageResponse)
def topic_coverage(
    slug: str,
    session: Annotated[Session, Depends(database_session)],
    settings: Annotated[Settings, Depends(application_settings)],
) -> TopicCoverageResponse:
    payload = CoverageQueryService(session, settings).topic(slug)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    return TopicCoverageResponse.model_validate(payload)
