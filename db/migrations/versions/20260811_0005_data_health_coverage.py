"""Add the rebuildable Topic-by-Source coverage projection.

Revision ID: 20260811_0005
Revises: 20260811_0004
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0005"
down_revision: str | None = "20260811_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
COVERAGE_STATUS = sa.Enum(
    "complete",
    "partial",
    "forward_only",
    "empty",
    "unknown",
    name="coveragestatus",
    native_enum=False,
    length=24,
)
COVERAGE_STRATEGY = sa.Enum(
    "historical_backfill",
    "forward_snapshot",
    "event_stream",
    "unknown",
    name="coveragestrategy",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "topic_source_coverage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("coverage_status", COVERAGE_STATUS, nullable=False),
        sa.Column("coverage_strategy", COVERAGE_STRATEGY, nullable=False),
        sa.Column("coverage_start", sa.Date(), nullable=True),
        sa.Column("coverage_end", sa.Date(), nullable=True),
        sa.Column("target_start", sa.Date(), nullable=True),
        sa.Column("target_end", sa.Date(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expected_observation_count", sa.Integer(), nullable=True),
        sa.Column("missing_observation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("partial_reason", sa.Text(), nullable=True),
        sa.Column("derived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derivation_version", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "observation_count >= 0", name="ck_topic_source_coverage_observation_count_nonnegative"
        ),
        sa.CheckConstraint(
            "expected_observation_count IS NULL OR expected_observation_count >= 0",
            name="ck_topic_source_coverage_expected_observation_count_nonnegative",
        ),
        sa.CheckConstraint(
            "missing_observation_count >= 0",
            name="ck_topic_source_coverage_missing_observation_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_topic_source_coverage_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name="fk_topic_source_coverage_topic_id_topics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_topic_source_coverage"),
        sa.UniqueConstraint("topic_id", "source_id", name="uq_topic_source_coverage_identity"),
    )
    op.create_index(
        "ix_topic_source_coverage_source_status",
        "topic_source_coverage",
        ["source_id", "coverage_status"],
    )
    op.create_index("ix_topic_source_coverage_topic", "topic_source_coverage", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_topic_source_coverage_topic", table_name="topic_source_coverage")
    op.drop_index("ix_topic_source_coverage_source_status", table_name="topic_source_coverage")
    op.drop_table("topic_source_coverage")
