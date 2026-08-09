"""Create the initial Silver schema.

Revision ID: 20260809_0001
Revises: None
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260809_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
INGESTION_STATUS = sa.Enum(
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name="ingestionstatus",
    native_enum=False,
    length=16,
)
QUALITY_STATUS = sa.Enum(
    "passed", "failed", "warning", name="qualitystatus", native_enum=False, length=16
)


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("name", name=op.f("uq_sources_name")),
    )
    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=250), nullable=False),
        sa.Column("normalized_name", sa.String(length=250), nullable=False),
        sa.Column("slug", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topics")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_topics_normalized_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_topics_slug")),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", INGESTION_STATUS, server_default="running", nullable=False),
        sa.Column("records_requested", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("checkpoint_before", JSON_TYPE, nullable=True),
        sa.Column("checkpoint_after", JSON_TYPE, nullable=True),
        sa.Column("collector_version", sa.String(length=100), nullable=False),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.CheckConstraint(
            "error_count >= 0", name=op.f("ck_ingestion_runs_error_count_nonnegative")
        ),
        sa.CheckConstraint(
            "records_inserted >= 0", name=op.f("ck_ingestion_runs_records_inserted_nonnegative")
        ),
        sa.CheckConstraint(
            "records_received >= 0", name=op.f("ck_ingestion_runs_records_received_nonnegative")
        ),
        sa.CheckConstraint(
            "records_requested >= 0", name=op.f("ck_ingestion_runs_records_requested_nonnegative")
        ),
        sa.CheckConstraint(
            "records_skipped >= 0", name=op.f("ck_ingestion_runs_records_skipped_nonnegative")
        ),
        sa.CheckConstraint(
            "records_updated >= 0", name=op.f("ck_ingestion_runs_records_updated_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_ingestion_runs_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        "ix_ingestion_runs_source_started_at",
        "ingestion_runs",
        ["source_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "topic_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("alias", sa.String(length=250), nullable=False),
        sa.Column("normalized_alias", sa.String(length=250), nullable=False),
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
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_topic_aliases_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_topic_aliases_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_aliases")),
        sa.UniqueConstraint(
            "source_id", "normalized_alias", name="uq_topic_aliases_source_normalized_alias"
        ),
    )
    op.create_index(
        op.f("ix_topic_aliases_source_id"), "topic_aliases", ["source_id"], unique=False
    )
    op.create_index(op.f("ix_topic_aliases_topic_id"), "topic_aliases", ["topic_id"], unique=False)
    op.create_index(
        "uq_topic_aliases_global_normalized_alias",
        "topic_aliases",
        ["normalized_alias"],
        unique=True,
        postgresql_where=sa.text("source_id IS NULL"),
        sqlite_where=sa.text("source_id IS NULL"),
    )
    op.create_table(
        "ingestion_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=150), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("record_identifier", sa.String(length=500), nullable=True),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_ingestion_errors_run_id_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_errors")),
    )
    op.create_index(
        "ix_ingestion_errors_run_occurred_at",
        "ingestion_errors",
        ["run_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "data_quality_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", QUALITY_STATUS, nullable=False),
        sa.Column("observed", JSON_TYPE, nullable=False),
        sa.Column("expected", JSON_TYPE, nullable=False),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_data_quality_checks_run_id_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_checks")),
    )
    op.create_index(
        "ix_data_quality_checks_run_name", "data_quality_checks", ["run_id", "name"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_data_quality_checks_run_name", table_name="data_quality_checks")
    op.drop_table("data_quality_checks")
    op.drop_index("ix_ingestion_errors_run_occurred_at", table_name="ingestion_errors")
    op.drop_table("ingestion_errors")
    op.drop_index("uq_topic_aliases_global_normalized_alias", table_name="topic_aliases")
    op.drop_index(op.f("ix_topic_aliases_topic_id"), table_name="topic_aliases")
    op.drop_index(op.f("ix_topic_aliases_source_id"), table_name="topic_aliases")
    op.drop_table("topic_aliases")
    op.drop_index("ix_ingestion_runs_source_started_at", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("topics")
    op.drop_table("sources")
