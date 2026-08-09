"""Validated values exchanged by all collectors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CollectorContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    source: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    request_timestamp: datetime
    collector_version: str = Field(min_length=1, max_length=100)
    schema_version: str = Field(min_length=1, max_length=100)
    checkpoint_before: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("request_timestamp must be timezone-aware")
        return value.astimezone(UTC)


class CollectorResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    records_requested: int = Field(default=0, ge=0)
    records_received: int = Field(default=0, ge=0)
    records_inserted: int = Field(default=0, ge=0)
    records_updated: int = Field(default=0, ge=0)
    records_skipped: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    checkpoint_after: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
