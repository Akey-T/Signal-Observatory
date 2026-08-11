"""Read-only collector status endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from arxiv_collector import ArxivQueryService
from github_collector import GithubQueryService
from signal_observatory_api.topics import application_settings, database_session
from signal_observatory_config import Settings

router = APIRouter(prefix="/api/sources", tags=["sources"])


class ArxivStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    enabled: bool
    collector_state: str
    last_run_at: datetime | None
    last_successful_run_at: datetime | None
    last_run_status: str | None
    tracked_topics: int
    tracked_mappings: int
    papers_observed: int
    last_24h_new_papers: int
    error_count_last_run: int


class GithubStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    enabled: bool
    auth_configured: bool
    collector_state: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_discovery_at: datetime | None
    last_snapshot_at: datetime | None
    last_successful_snapshot_at: datetime | None
    tracked_repositories: int
    snapshots: int
    errors_last_run: int
    search_rate: dict[str, Any] | None
    core_rate: dict[str, Any] | None


@router.get("/arxiv/status", response_model=ArxivStatusResponse)
def arxiv_status(
    session: Annotated[Session, Depends(database_session)],
) -> ArxivStatusResponse:
    return ArxivStatusResponse.model_validate(ArxivQueryService(session).status())


@router.get("/github/status", response_model=GithubStatusResponse)
def github_status(
    session: Annotated[Session, Depends(database_session)],
    settings: Annotated[Settings, Depends(application_settings)],
) -> GithubStatusResponse:
    return GithubStatusResponse.model_validate(GithubQueryService(session, settings).status())
