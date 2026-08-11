"""Rebuildable Topic-by-Source data coverage projections."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from observatory_db.base import Base, UTCDateTime, utc_now
from observatory_db.models import JSON_TYPE


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FORWARD_ONLY = "forward_only"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class CoverageStrategy(StrEnum):
    HISTORICAL_BACKFILL = "historical_backfill"
    FORWARD_SNAPSHOT = "forward_snapshot"
    EVENT_STREAM = "event_stream"
    UNKNOWN = "unknown"


class TopicSourceCoverage(Base):
    """Current deterministic projection; never an administrator-authored completeness claim."""

    __tablename__ = "topic_source_coverage"
    __table_args__ = (
        UniqueConstraint("topic_id", "source_id", name="uq_topic_source_coverage_identity"),
        CheckConstraint("observation_count >= 0", name="observation_count_nonnegative"),
        CheckConstraint(
            "expected_observation_count IS NULL OR expected_observation_count >= 0",
            name="expected_observation_count_nonnegative",
        ),
        CheckConstraint(
            "missing_observation_count >= 0",
            name="missing_observation_count_nonnegative",
        ),
        Index("ix_topic_source_coverage_source_status", "source_id", "coverage_status"),
        Index("ix_topic_source_coverage_topic", "topic_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    coverage_status: Mapped[CoverageStatus] = mapped_column(
        Enum(
            CoverageStatus,
            native_enum=False,
            length=24,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    coverage_strategy: Mapped[CoverageStrategy] = mapped_column(
        Enum(
            CoverageStrategy,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    coverage_start: Mapped[date | None] = mapped_column(Date)
    coverage_end: Mapped[date | None] = mapped_column(Date)
    target_start: Mapped[date | None] = mapped_column(Date)
    target_end: Mapped[date | None] = mapped_column(Date)
    first_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_successful_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    observation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_observation_count: Mapped[int | None] = mapped_column(Integer)
    missing_observation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_reason: Mapped[str | None] = mapped_column(Text)
    derived_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    derivation_version: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
