"""Minimal read-only Topic Registry API."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from observatory_db.models import TopicStatus
from topic_registry.queries import TopicQueryService, topic_to_dict

router = APIRouter(prefix="/api", tags=["topics"])


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AliasResponse(APIModel):
    value: str
    normalized_alias: str
    type: str
    match_mode: str
    case_sensitive: bool
    status: str
    confidence: float
    metadata: dict[str, Any]


class SourceMappingResponse(APIModel):
    source: str
    enabled: bool
    mapping_type: str
    external_identifier: str | None
    query: str | None
    configuration: dict[str, Any]


class TopicResponse(APIModel):
    topic_id: str
    canonical_name: str
    slug: str
    description: str | None
    category: str | None
    status: str
    monitoring_priority: int
    deprecated_at: datetime | None
    registry_version: int | None
    metadata: dict[str, Any]
    aliases: list[AliasResponse]
    sources: list[SourceMappingResponse]


class TopicListResponse(APIModel):
    items: list[TopicResponse]
    total: int
    limit: int
    offset: int


class CategoryResponse(APIModel):
    id: str
    name: str
    slug: str
    description: str | None
    parent: str | None
    sort_order: int


class RegistryStatusResponse(APIModel):
    version: int
    checksum: str
    last_synced_at: datetime
    topic_count: int
    active_topics: int
    alias_count: int
    source_mapping_count: int
    warnings: int


def database_session(request: Request) -> Iterator[Session]:
    engine: Engine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not ready",
        )
    with Session(engine) as session:
        yield session


@router.get("/topics", response_model=TopicListResponse)
def list_topics(
    session: Annotated[Session, Depends(database_session)],
    category: str | None = None,
    topic_status: Annotated[TopicStatus | None, Query(alias="status")] = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TopicListResponse:
    topics, total = TopicQueryService(session).list_topics(
        category=category,
        status=topic_status,
        search=search,
        limit=limit,
        offset=offset,
    )
    return TopicListResponse(
        items=[TopicResponse.model_validate(topic_to_dict(topic)) for topic in topics],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/topics/{slug}", response_model=TopicResponse)
def topic_detail(
    slug: str, session: Annotated[Session, Depends(database_session)]
) -> TopicResponse:
    topic = TopicQueryService(session).get_topic(slug)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    return TopicResponse.model_validate(topic_to_dict(topic))


@router.get("/categories", response_model=list[CategoryResponse])
def categories(
    session: Annotated[Session, Depends(database_session)],
) -> list[CategoryResponse]:
    return [
        CategoryResponse(
            id=str(category.id),
            name=category.name,
            slug=category.slug,
            description=category.description,
            parent=category.parent.slug if category.parent else None,
            sort_order=category.sort_order,
        )
        for category in TopicQueryService(session).list_categories()
    ]


@router.get("/topic-registry/status", response_model=RegistryStatusResponse)
def registry_status(
    session: Annotated[Session, Depends(database_session)],
) -> RegistryStatusResponse:
    result = TopicQueryService(session).registry_status()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="topic registry has not been synchronized",
        )
    return RegistryStatusResponse.model_validate(result)
