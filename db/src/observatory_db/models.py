"""Normalized Silver-layer relational models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from observatory_db.base import Base, UTCDateTime, utc_now

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QualityStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class TopicStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"


class AliasStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class AliasType(StrEnum):
    NAME = "name"
    ABBREVIATION = "abbreviation"
    SPELLING = "spelling"
    PRODUCT_NAME = "product_name"
    RELATED_TERM = "related_term"
    SEARCH_TERM = "search_term"


class MatchMode(StrEnum):
    EXACT = "exact"
    PHRASE = "phrase"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    aliases: Mapped[list[TopicAlias]] = relationship(back_populates="source")
    topic_mappings: Mapped[list[TopicSourceMapping]] = relationship(back_populates="source")
    ingestion_runs: Mapped[list[IngestionRun]] = relationship(back_populates="source")


class TopicCategory(TimestampMixin, Base):
    __tablename__ = "topic_categories"
    __table_args__ = (CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("topic_categories.id", ondelete="RESTRICT"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    parent: Mapped[TopicCategory | None] = relationship(
        back_populates="children", remote_side="TopicCategory.id"
    )
    children: Mapped[list[TopicCategory]] = relationship(back_populates="parent")
    topics: Mapped[list[Topic]] = relationship(back_populates="category")


class Topic(TimestampMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint(
            "monitoring_priority >= 0 AND monitoring_priority <= 100",
            name="monitoring_priority_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(250), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(250), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(250), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("topic_categories.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[TopicStatus] = mapped_column(
        Enum(
            TopicStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=TopicStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    monitoring_priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    deprecated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    registry_version: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    category: Mapped[TopicCategory | None] = relationship(back_populates="topics")
    aliases: Mapped[list[TopicAlias]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    source_mappings: Mapped[list[TopicSourceMapping]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class TopicAlias(TimestampMixin, Base):
    __tablename__ = "topic_aliases"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "normalized_alias",
            name="uq_topic_aliases_source_normalized_alias",
        ),
        UniqueConstraint(
            "topic_id",
            "normalized_alias",
            name="uq_topic_aliases_topic_normalized_alias",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(250), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(250), nullable=False)
    alias_type: Mapped[AliasType] = mapped_column(
        Enum(
            AliasType,
            native_enum=False,
            length=24,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AliasType.NAME,
        nullable=False,
    )
    match_mode: Mapped[MatchMode] = mapped_column(
        Enum(
            MatchMode,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=MatchMode.EXACT,
        nullable=False,
    )
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[AliasStatus] = mapped_column(
        Enum(
            AliasStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AliasStatus.ACTIVE,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    topic: Mapped[Topic] = relationship(back_populates="aliases")
    source: Mapped[Source | None] = relationship(back_populates="aliases")


class TopicSourceMapping(TimestampMixin, Base):
    __tablename__ = "topic_source_mappings"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "source_id", "mapping_type", name="uq_topic_source_mappings_identity"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mapping_type: Mapped[str] = mapped_column(String(100), default="registry", nullable=False)
    external_identifier: Mapped[str | None] = mapped_column(String(500))
    query: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    topic: Mapped[Topic] = relationship(back_populates="source_mappings")
    source: Mapped[Source] = relationship(back_populates="topic_mappings")


class TopicRegistryVersion(Base):
    __tablename__ = "topic_registry_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("source_file_count >= 0", name="source_file_count_nonnegative"),
        CheckConstraint("topic_count >= 0", name="topic_count_nonnegative"),
        CheckConstraint("alias_count >= 0", name="alias_count_nonnegative"),
        CheckConstraint("mapping_count >= 0", name="mapping_count_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    source_file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_count: Mapped[int] = mapped_column(Integer, nullable=False)
    alias_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_by: Mapped[str] = mapped_column(String(200), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    audit_entries: Mapped[list[TopicRegistryAuditLog]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class TopicRegistryAuditLog(Base):
    __tablename__ = "topic_registry_audit_log"
    __table_args__ = (
        Index("ix_topic_registry_audit_version_timestamp", "version_id", "timestamp"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_registry_versions.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(500), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    version: Mapped[TopicRegistryVersion] = relationship(back_populates="audit_entries")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("records_requested >= 0", name="records_requested_nonnegative"),
        CheckConstraint("records_received >= 0", name="records_received_nonnegative"),
        CheckConstraint("records_inserted >= 0", name="records_inserted_nonnegative"),
        CheckConstraint("records_updated >= 0", name="records_updated_nonnegative"),
        CheckConstraint("records_skipped >= 0", name="records_skipped_nonnegative"),
        CheckConstraint("error_count >= 0", name="error_count_nonnegative"),
        Index("ix_ingestion_runs_source_started_at", "source_id", "started_at"),
    )

    run_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(
            IngestionStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=IngestionStatus.RUNNING,
        nullable=False,
    )
    records_requested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkpoint_before: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    checkpoint_after: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    collector_version: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    source: Mapped[Source] = relationship(back_populates="ingestion_runs")
    errors: Mapped[list[IngestionError]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    quality_checks: Mapped[list[DataQualityCheck]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class IngestionError(Base):
    __tablename__ = "ingestion_errors"
    __table_args__ = (Index("ix_ingestion_errors_run_occurred_at", "run_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    error_type: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    record_identifier: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    run: Mapped[IngestionRun] = relationship(back_populates="errors")


class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"
    __table_args__ = (Index("ix_data_quality_checks_run_name", "run_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="CASCADE")
    )
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[QualityStatus] = mapped_column(
        Enum(
            QualityStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    observed: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    expected: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    run: Mapped[IngestionRun | None] = relationship(back_populates="quality_checks")
