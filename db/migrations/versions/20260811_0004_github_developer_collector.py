"""Add GitHub Developer Collector identity, discovery, snapshot, and lineage schema.

Revision ID: 20260811_0004
Revises: 20260810_0003
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0004"
down_revision: str | None = "20260810_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TRACKING_STATE = sa.Enum(
    "candidate", "tracked", "ignored", name="githubtrackingstate", native_enum=False, length=16
)
MATCH_METHOD = sa.Enum(
    "GITHUB_REPOSITORY_SEARCH", name="githubmatchmethod", native_enum=False, length=40
)
OPERATION_STATUS = sa.Enum(
    "pending",
    "running",
    "succeeded",
    "partial",
    "failed",
    name="githuboperationstatus",
    native_enum=False,
    length=16,
)
SNAPSHOT_METHOD = sa.Enum(
    "full_200",
    "conditional_304",
    name="githubsnapshotmethod",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    op.create_table(
        "github_repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("node_id", sa.String(length=200), nullable=False),
        sa.Column("owner_login", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=600), nullable=False),
        sa.Column("html_url", sa.String(length=1000), nullable=False),
        sa.Column("api_url", sa.String(length=1000), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage", sa.String(length=1000), nullable=True),
        sa.Column("language", sa.String(length=200), nullable=True),
        sa.Column("default_branch", sa.String(length=500), nullable=True),
        sa.Column("is_fork", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fork_parent_github_id", sa.BigInteger(), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("created_at_github", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_github", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pushed_at_github", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_repositories")),
        sa.UniqueConstraint(
            "github_repository_id", name=op.f("uq_github_repositories_github_repository_id")
        ),
    )
    op.create_index(
        "ix_github_repositories_last_observed_at", "github_repositories", ["last_observed_at"]
    )
    op.create_index("ix_github_repositories_full_name", "github_repositories", ["full_name"])

    op.create_table(
        "github_raw_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=True),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint_type", sa.String(length=50), nullable=False),
        sa.Column("raw_path", sa.Text(), nullable=False),
        sa.Column("payload_checksum", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_url_hash", sa.String(length=64), nullable=False),
        sa.Column("query_parameters", JSON_TYPE, nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(length=500), nullable=True),
        sa.Column("last_modified", sa.String(length=500), nullable=True),
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        sa.Column("rate_remaining", sa.Integer(), nullable=True),
        sa.Column("rate_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rate_resource", sa.String(length=100), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("response_headers", JSON_TYPE, nullable=False),
        sa.Column("request_metadata", JSON_TYPE, nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_github_raw_responses_ingestion_run_id_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["github_repositories.id"],
            name=op.f("fk_github_raw_responses_repository_id_github_repositories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_github_raw_responses_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_github_raw_responses_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_raw_responses")),
        sa.UniqueConstraint("raw_path", name=op.f("uq_github_raw_responses_raw_path")),
    )
    op.create_index(
        "ix_github_raw_responses_run_observed",
        "github_raw_responses",
        ["ingestion_run_id", "observed_at"],
    )
    op.create_index("ix_github_raw_responses_endpoint", "github_raw_responses", ["endpoint_type"])
    for column in (
        "payload_checksum",
        "repository_id",
        "request_url_hash",
        "source_mapping_id",
        "topic_id",
    ):
        op.create_index(op.f(f"ix_github_raw_responses_{column}"), "github_raw_responses", [column])

    op.create_table(
        "github_repository_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("full_name", sa.String(length=600), nullable=False),
        sa.Column("stargazers_count", sa.Integer(), nullable=False),
        sa.Column("forks_count", sa.Integer(), nullable=False),
        sa.Column("open_issues_count", sa.Integer(), nullable=False),
        sa.Column("subscribers_count", sa.Integer(), nullable=False),
        sa.Column("size_kb", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=200), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("default_branch", sa.String(length=500), nullable=True),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_github", sa.DateTime(timezone=True), nullable=False),
        sa.Column("topics", JSON_TYPE, nullable=False),
        sa.Column("license_spdx", sa.String(length=100), nullable=True),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("raw_response_id", sa.Uuid(), nullable=False),
        sa.Column("observation_method", SNAPSHOT_METHOD, nullable=False),
        sa.Column("etag", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stargazers_count >= 0",
            name=op.f("ck_github_repository_snapshots_stargazers_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "forks_count >= 0",
            name=op.f("ck_github_repository_snapshots_forks_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "open_issues_count >= 0",
            name=op.f("ck_github_repository_snapshots_open_issues_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "subscribers_count >= 0",
            name=op.f("ck_github_repository_snapshots_subscribers_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "size_kb >= 0", name=op.f("ck_github_repository_snapshots_size_kb_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["github_repositories.id"],
            name=op.f("fk_github_repository_snapshots_repository_id_github_repositories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_github_repository_snapshots_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_response_id"],
            ["github_raw_responses.id"],
            name=op.f("fk_github_repository_snapshots_raw_response_id_github_raw_responses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_repository_snapshots")),
        sa.UniqueConstraint(
            "repository_id",
            "observation_date",
            name="uq_github_repository_snapshots_daily",
        ),
    )
    op.create_index(
        "ix_github_repository_snapshots_repo_observed",
        "github_repository_snapshots",
        ["repository_id", "observed_at"],
    )
    op.create_index(
        "ix_github_repository_snapshots_repo_date",
        "github_repository_snapshots",
        ["repository_id", "observation_date"],
    )
    op.create_index(
        op.f("ix_github_repository_snapshots_ingestion_run_id"),
        "github_repository_snapshots",
        ["ingestion_run_id"],
    )
    op.create_index(
        op.f("ix_github_repository_snapshots_raw_response_id"),
        "github_repository_snapshots",
        ["raw_response_id"],
    )

    op.create_table(
        "github_topic_repository_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("matched_query", sa.Text(), nullable=False),
        sa.Column("match_method", MATCH_METHOD, nullable=False),
        sa.Column("discovery_rank", sa.Integer(), nullable=False),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("last_ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("tracking_state", TRACKING_STATE, nullable=False),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_github_matches_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["github_repositories.id"],
            name=op.f("fk_github_matches_repository_id_github_repositories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_github_matches_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_github_matches_first_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_github_matches_last_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_topic_repository_matches")),
        sa.UniqueConstraint(
            "topic_id",
            "repository_id",
            "source_mapping_id",
            "matched_query",
            name="uq_github_topic_repository_matches_evidence",
        ),
    )
    op.create_index(
        "ix_github_topic_repository_matches_topic_repo",
        "github_topic_repository_matches",
        ["topic_id", "repository_id"],
    )
    op.create_index(
        "ix_github_topic_repository_matches_mapping",
        "github_topic_repository_matches",
        ["source_mapping_id"],
    )
    op.create_index(
        "ix_github_topic_repository_matches_tracking",
        "github_topic_repository_matches",
        ["tracking_state"],
    )

    op.create_table(
        "github_repository_poll_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(length=500), nullable=True),
        sa.Column("last_modified", sa.String(length=500), nullable=True),
        sa.Column("last_status", sa.Integer(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["github_repositories.id"],
            name=op.f("fk_github_poll_states_repository_id_github_repositories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_repository_poll_states")),
        sa.UniqueConstraint(
            "repository_id", name=op.f("uq_github_repository_poll_states_repository_id")
        ),
    )
    op.create_index(
        "ix_github_poll_states_last_successful",
        "github_repository_poll_states",
        ["last_successful_at"],
    )

    op.create_table(
        "github_discovery_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("status", OPERATION_STATUS, server_default="pending", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ingestion_run_id", sa.Uuid(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_github_discovery_states_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_github_discovery_states_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_github_discovery_states_last_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_discovery_states")),
        sa.UniqueConstraint(
            "source_mapping_id", name=op.f("uq_github_discovery_states_source_mapping_id")
        ),
    )
    op.create_index("ix_github_discovery_states_topic", "github_discovery_states", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_github_discovery_states_topic", table_name="github_discovery_states")
    op.drop_table("github_discovery_states")
    op.drop_index(
        "ix_github_poll_states_last_successful", table_name="github_repository_poll_states"
    )
    op.drop_table("github_repository_poll_states")
    op.drop_index(
        "ix_github_topic_repository_matches_tracking",
        table_name="github_topic_repository_matches",
    )
    op.drop_index(
        "ix_github_topic_repository_matches_mapping",
        table_name="github_topic_repository_matches",
    )
    op.drop_index(
        "ix_github_topic_repository_matches_topic_repo",
        table_name="github_topic_repository_matches",
    )
    op.drop_table("github_topic_repository_matches")
    op.drop_index(
        op.f("ix_github_repository_snapshots_raw_response_id"),
        table_name="github_repository_snapshots",
    )
    op.drop_index(
        op.f("ix_github_repository_snapshots_ingestion_run_id"),
        table_name="github_repository_snapshots",
    )
    op.drop_index(
        "ix_github_repository_snapshots_repo_date", table_name="github_repository_snapshots"
    )
    op.drop_index(
        "ix_github_repository_snapshots_repo_observed", table_name="github_repository_snapshots"
    )
    op.drop_table("github_repository_snapshots")
    for column in (
        "topic_id",
        "source_mapping_id",
        "request_url_hash",
        "repository_id",
        "payload_checksum",
    ):
        op.drop_index(op.f(f"ix_github_raw_responses_{column}"), table_name="github_raw_responses")
    op.drop_index("ix_github_raw_responses_endpoint", table_name="github_raw_responses")
    op.drop_index("ix_github_raw_responses_run_observed", table_name="github_raw_responses")
    op.drop_table("github_raw_responses")
    op.drop_index("ix_github_repositories_full_name", table_name="github_repositories")
    op.drop_index("ix_github_repositories_last_observed_at", table_name="github_repositories")
    op.drop_table("github_repositories")
