"""GitHub Repository identity, immutable daily snapshots, and provenance indexes."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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


class GithubTrackingState(StrEnum):
    CANDIDATE = "candidate"
    TRACKED = "tracked"
    IGNORED = "ignored"


class GithubMatchMethod(StrEnum):
    GITHUB_REPOSITORY_SEARCH = "GITHUB_REPOSITORY_SEARCH"


class GithubOperationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class GithubSnapshotMethod(StrEnum):
    FULL_200 = "full_200"
    CONDITIONAL_304 = "conditional_304"


class GithubRepository(Base):
    __tablename__ = "github_repositories"
    __table_args__ = (
        Index("ix_github_repositories_last_observed_at", "last_observed_at"),
        Index("ix_github_repositories_full_name", "full_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    github_repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    node_id: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_login: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(600), nullable=False)
    html_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    api_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(String(1000))
    language: Mapped[str | None] = mapped_column(String(200))
    default_branch: Mapped[str | None] = mapped_column(String(500))
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fork_parent_github_id: Mapped[int | None] = mapped_column(BigInteger)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visibility: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at_github: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at_github: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    pushed_at_github: Mapped[datetime | None] = mapped_column(UTCDateTime())
    first_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    snapshots: Mapped[list[GithubRepositorySnapshot]] = relationship(back_populates="repository")
    topic_matches: Mapped[list[GithubTopicRepositoryMatch]] = relationship(
        back_populates="repository"
    )
    poll_state: Mapped[GithubRepositoryPollState | None] = relationship(
        back_populates="repository", uselist=False
    )


class GithubRawResponse(Base):
    __tablename__ = "github_raw_responses"
    __table_args__ = (
        Index("ix_github_raw_responses_run_observed", "ingestion_run_id", "observed_at"),
        Index("ix_github_raw_responses_endpoint", "endpoint_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="RESTRICT"), index=True
    )
    topic_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), index=True
    )
    source_mapping_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), index=True
    )
    endpoint_type: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    request_url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_parameters: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(500))
    rate_limit: Mapped[int | None] = mapped_column(Integer)
    rate_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_reset_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    rate_resource: Mapped[str | None] = mapped_column(String(100))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    parse_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    snapshots: Mapped[list[GithubRepositorySnapshot]] = relationship(back_populates="raw_response")


class GithubRepositorySnapshot(Base):
    __tablename__ = "github_repository_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "observation_date", name="uq_github_repository_snapshots_daily"
        ),
        Index("ix_github_repository_snapshots_repo_observed", "repository_id", "observed_at"),
        Index("ix_github_repository_snapshots_repo_date", "repository_id", "observation_date"),
        CheckConstraint("stargazers_count >= 0", name="stargazers_count_nonnegative"),
        CheckConstraint("forks_count >= 0", name="forks_count_nonnegative"),
        CheckConstraint("open_issues_count >= 0", name="open_issues_count_nonnegative"),
        CheckConstraint("subscribers_count >= 0", name="subscribers_count_nonnegative"),
        CheckConstraint("size_kb >= 0", name="size_kb_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    full_name: Mapped[str] = mapped_column(String(600), nullable=False)
    stargazers_count: Mapped[int] = mapped_column(Integer, nullable=False)
    forks_count: Mapped[int] = mapped_column(Integer, nullable=False)
    open_issues_count: Mapped[int] = mapped_column(Integer, nullable=False)
    subscribers_count: Mapped[int] = mapped_column(Integer, nullable=False)
    size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str | None] = mapped_column(String(200))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(500))
    pushed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at_github: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    license_spdx: Mapped[str | None] = mapped_column(String(100))
    ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_response_id: Mapped[UUID] = mapped_column(
        ForeignKey("github_raw_responses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observation_method: Mapped[GithubSnapshotMethod] = mapped_column(
        Enum(
            GithubSnapshotMethod,
            native_enum=False,
            length=24,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    etag: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)

    repository: Mapped[GithubRepository] = relationship(back_populates="snapshots")
    raw_response: Mapped[GithubRawResponse] = relationship(back_populates="snapshots")


class GithubTopicRepositoryMatch(Base):
    __tablename__ = "github_topic_repository_matches"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "repository_id",
            "source_mapping_id",
            "matched_query",
            name="uq_github_topic_repository_matches_evidence",
        ),
        Index("ix_github_topic_repository_matches_topic_repo", "topic_id", "repository_id"),
        Index("ix_github_topic_repository_matches_mapping", "source_mapping_id"),
        Index("ix_github_topic_repository_matches_tracking", "tracking_state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="RESTRICT"), nullable=False
    )
    source_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    matched_query: Mapped[str] = mapped_column(Text, nullable=False)
    match_method: Mapped[GithubMatchMethod] = mapped_column(
        Enum(
            GithubMatchMethod,
            native_enum=False,
            length=40,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    discovery_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    first_discovered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_discovered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    first_ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    last_ingestion_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    tracking_state: Mapped[GithubTrackingState] = mapped_column(
        Enum(
            GithubTrackingState,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)

    repository: Mapped[GithubRepository] = relationship(back_populates="topic_matches")


class GithubRepositoryPollState(Base):
    __tablename__ = "github_repository_poll_states"
    __table_args__ = (Index("ix_github_poll_states_last_successful", "last_successful_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_successful_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_snapshot_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(500))
    last_status: Mapped[int | None] = mapped_column(Integer)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_eligible_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    repository: Mapped[GithubRepository] = relationship(back_populates="poll_state")


class GithubDiscoveryState(Base):
    __tablename__ = "github_discovery_states"
    __table_args__ = (Index("ix_github_discovery_states_topic", "topic_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    source_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_source_mappings.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    status: Mapped[GithubOperationStatus] = mapped_column(
        Enum(
            GithubOperationStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=GithubOperationStatus.PENDING,
        nullable=False,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_successful_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    next_eligible_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_ingestion_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.run_id", ondelete="RESTRICT")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
