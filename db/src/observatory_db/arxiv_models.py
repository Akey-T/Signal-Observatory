"""Normalized arXiv metadata, collection state, and immutable lineage indexes."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from observatory_db.base import Base, UTCDateTime, utc_now
from observatory_db.models import JSON_TYPE


class ArxivMatchMethod(StrEnum):
    ARXIV_API_QUERY = "ARXIV_API_QUERY"


class ArxivCursorStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ArxivPaper(Base):
    __tablename__ = "arxiv_papers"
    __table_args__ = (
        Index("ix_arxiv_papers_published_at", "published_at"),
        Index("ix_arxiv_papers_updated_at", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    arxiv_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    latest_version: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    primary_category: Mapped[str] = mapped_column(String(100), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    journal_ref: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(500))
    license_url: Mapped[str | None] = mapped_column(String(1000))
    abs_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(1000))
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    authors: Mapped[list[ArxivPaperAuthor]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", order_by="ArxivPaperAuthor.position"
    )
    categories: Mapped[list[ArxivPaperCategory]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    topic_matches: Mapped[list[ArxivTopicMatch]] = relationship(back_populates="paper")
    observations: Mapped[list[ArxivPaperObservation]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class ArxivAuthor(Base):
    __tablename__ = "arxiv_authors"
    __table_args__ = (Index("ix_arxiv_authors_normalized_name", "normalized_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    papers: Mapped[list[ArxivPaperAuthor]] = relationship(back_populates="author")


class ArxivPaperAuthor(Base):
    __tablename__ = "arxiv_paper_authors"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("paper_id", "author_id", name="uq_arxiv_paper_authors_identity"),
    )

    paper_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_papers.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_authors.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    paper: Mapped[ArxivPaper] = relationship(back_populates="authors")
    author: Mapped[ArxivAuthor] = relationship(back_populates="papers")


class ArxivCategory(Base):
    __tablename__ = "arxiv_categories"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    papers: Mapped[list[ArxivPaperCategory]] = relationship(back_populates="category")


class ArxivPaperCategory(Base):
    __tablename__ = "arxiv_paper_categories"

    paper_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_papers.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_categories.id", ondelete="RESTRICT"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    paper: Mapped[ArxivPaper] = relationship(back_populates="categories")
    category: Mapped[ArxivCategory] = relationship(back_populates="papers")


class ArxivRawResponse(Base):
    __tablename__ = "arxiv_raw_responses"
    __table_args__ = (
        CheckConstraint("start_index >= 0", name="start_index_nonnegative"),
        CheckConstraint("max_results >= 0", name="max_results_nonnegative"),
        Index("ix_arxiv_raw_responses_run_observed", "ingestion_run_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    start_index: Mapped[int] = mapped_column(Integer, nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_by: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[str] = mapped_column(String(20), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    parsed_entry_count: Mapped[int | None] = mapped_column(Integer)
    parse_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    observations: Mapped[list[ArxivPaperObservation]] = relationship(
        back_populates="raw_response", cascade="all, delete-orphan"
    )


class ArxivPaperObservation(Base):
    __tablename__ = "arxiv_paper_observations"
    __table_args__ = (
        UniqueConstraint("paper_id", "raw_response_id", name="uq_arxiv_paper_observations_lineage"),
        Index("ix_arxiv_paper_observations_run", "ingestion_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_papers.id", ondelete="CASCADE"), nullable=False
    )
    raw_response_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_raw_responses.id", ondelete="CASCADE"), nullable=False
    )
    ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    arxiv_version: Mapped[int | None] = mapped_column(Integer)
    normalized_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    paper: Mapped[ArxivPaper] = relationship(back_populates="observations")
    raw_response: Mapped[ArxivRawResponse] = relationship(back_populates="observations")


class ArxivTopicMatch(Base):
    __tablename__ = "arxiv_topic_matches"
    __table_args__ = (
        UniqueConstraint(
            "paper_id",
            "topic_id",
            "source_mapping_id",
            "matched_query",
            name="uq_arxiv_topic_matches_explainable_identity",
        ),
        Index("ix_arxiv_topic_matches_topic_paper", "topic_id", "paper_id"),
        Index("ix_arxiv_topic_matches_mapping", "source_mapping_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(
        ForeignKey("arxiv_papers.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    source_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    matched_query: Mapped[str] = mapped_column(Text, nullable=False)
    match_method: Mapped[ArxivMatchMethod] = mapped_column(
        Enum(
            ArxivMatchMethod,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=ArxivMatchMethod.ARXIV_API_QUERY,
        nullable=False,
    )
    first_matched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_matched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    first_ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    last_ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    paper: Mapped[ArxivPaper] = relationship(back_populates="topic_matches")


class ArxivCollectionCursor(Base):
    __tablename__ = "arxiv_collection_cursors"
    __table_args__ = (
        UniqueConstraint(
            "source_mapping_id", "cursor_key", name="uq_arxiv_collection_cursors_mapping_key"
        ),
        CheckConstraint("next_start >= 0", name="next_start_nonnegative"),
        Index("ix_arxiv_collection_cursors_topic", "topic_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    source_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    cursor_key: Mapped[str] = mapped_column(String(250), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    last_successful_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_query_from: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_query_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_observed_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    window_from: Mapped[datetime | None] = mapped_column(UTCDateTime())
    window_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    next_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    status: Mapped[ArxivCursorStatus] = mapped_column(
        Enum(
            ArxivCursorStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=ArxivCursorStatus.PENDING,
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
