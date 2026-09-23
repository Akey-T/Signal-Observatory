"""Source-neutral Attention Domain Silver models.

These tables intentionally persist only Documents, measured Observations, and their Evidence
links. Canonical Entity and Event governance remains contract-only until a later Epic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from attention_domain import (
    AttentionChannel,
    AttentionDocumentType,
    AttentionEvidenceRole,
    AttentionObservationState,
)
from observatory_db.base import Base, UTCDateTime, utc_now
from observatory_db.models import JSON_TYPE


class AttentionDocument(Base):
    """A source-provided evidence document without a full-text/body requirement."""

    __tablename__ = "attention_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_document_key",
            name="uq_attention_documents_source_key",
        ),
        CheckConstraint(
            "last_observed_at >= first_observed_at",
            name="document_observation_order",
        ),
        Index("ix_attention_documents_source_observed", "source_id", "last_observed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    source_document_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2000))
    title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    first_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    document_type: Mapped[AttentionDocumentType] = mapped_column(
        Enum(
            AttentionDocumentType,
            native_enum=False,
            length=24,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    evidence_links: Mapped[list[AttentionObservationEvidence]] = relationship(
        back_populates="document"
    )


class AttentionObservation(Base):
    """One measured Topic/source/channel/metric over a closed UTC time window."""

    __tablename__ = "attention_observations"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "source_id",
            "source_mapping_id",
            "channel",
            "metric_name",
            "window_start",
            "window_end",
            name="uq_attention_observations_identity",
        ),
        CheckConstraint("window_end > window_start", name="observation_window_order"),
        Index(
            "ix_attention_observations_topic_window",
            "topic_id",
            "window_start",
            "window_end",
        ),
        Index(
            "ix_attention_observations_source_channel",
            "source_id",
            "channel",
            "window_start",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    source_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[AttentionChannel] = mapped_column(
        Enum(
            AttentionChannel,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    window_end: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    collection_state: Mapped[AttentionObservationState] = mapped_column(
        Enum(
            AttentionObservationState,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    ingestion_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT")
    )
    first_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    evidence_links: Mapped[list[AttentionObservationEvidence]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )


class AttentionObservationEvidence(Base):
    """A sampled or otherwise role-labelled document supporting an observation."""

    __tablename__ = "attention_observation_evidence"
    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "document_id",
            "evidence_role",
            name="uq_attention_observation_evidence_relation",
        ),
        CheckConstraint("rank IS NULL OR rank >= 0", name="evidence_rank_nonnegative"),
        Index("ix_attention_observation_evidence_document", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    observation_id: Mapped[UUID] = mapped_column(
        ForeignKey("attention_observations.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("attention_documents.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_role: Mapped[AttentionEvidenceRole] = mapped_column(
        Enum(
            AttentionEvidenceRole,
            native_enum=False,
            length=24,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    observation: Mapped[AttentionObservation] = relationship(back_populates="evidence_links")
    document: Mapped[AttentionDocument] = relationship(back_populates="evidence_links")
