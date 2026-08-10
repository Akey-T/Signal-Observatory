"""Read-only collector status endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from arxiv_collector import ArxivQueryService
from signal_observatory_api.topics import database_session

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


@router.get("/arxiv/status", response_model=ArxivStatusResponse)
def arxiv_status(
    session: Annotated[Session, Depends(database_session)],
) -> ArxivStatusResponse:
    return ArxivStatusResponse.model_validate(ArxivQueryService(session).status())
