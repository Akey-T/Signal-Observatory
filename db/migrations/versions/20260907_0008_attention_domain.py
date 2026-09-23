"""Add source-neutral Attention Domain document, observation, and evidence tables.

Revision ID: 20260907_0008
Revises: 20260813_0007
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0008"
down_revision: str | None = "20260813_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
CHANNEL = sa.Enum(
    "media",
    "search",
    "community",
    "reference",
    name="attentionchannel",
    native_enum=False,
    length=16,
)
DOCUMENT_TYPE = sa.Enum(
    "article",
    "post",
    "story",
    "reference_page",
    "other",
    name="attentiondocumenttype",
    native_enum=False,
    length=24,
)
OBSERVATION_STATE = sa.Enum(
    "valid",
    "partial",
    name="attentionobservationstate",
    native_enum=False,
    length=16,
)
EVIDENCE_ROLE = sa.Enum(
    "sample",
    "match",
    "example",
    "source_record",
    name="attentionevidencerole",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    op.create_table(
        "attention_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_key", sa.String(length=1000), nullable=False),
        sa.Column("canonical_url", sa.String(length=2000), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_type", DOCUMENT_TYPE, nullable=False),
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
            "last_observed_at >= first_observed_at",
            name=op.f("ck_attention_documents_document_observation_order"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_attention_documents_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attention_documents")),
        sa.UniqueConstraint(
            "source_id",
            "source_document_key",
            name="uq_attention_documents_source_key",
        ),
    )
    op.create_index(
        "ix_attention_documents_source_observed",
        "attention_documents",
        ["source_id", "last_observed_at"],
        unique=False,
    )

    op.create_table(
        "attention_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("channel", CHANNEL, nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("definition_version", sa.String(length=80), nullable=False),
        sa.Column("collection_state", OBSERVATION_STATE, nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
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
            "window_end > window_start",
            name=op.f("ck_attention_observations_observation_window_order"),
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_attention_observations_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_attention_observations_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_attention_observations_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_attention_observations_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attention_observations")),
        sa.UniqueConstraint(
            "topic_id",
            "source_id",
            "source_mapping_id",
            "channel",
            "metric_name",
            "window_start",
            "window_end",
            name="uq_attention_observations_identity",
        ),
    )
    op.create_index(
        "ix_attention_observations_topic_window",
        "attention_observations",
        ["topic_id", "window_start", "window_end"],
        unique=False,
    )
    op.create_index(
        "ix_attention_observations_source_channel",
        "attention_observations",
        ["source_id", "channel", "window_start"],
        unique=False,
    )

    op.create_table(
        "attention_observation_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_role", EVIDENCE_ROLE, nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rank IS NULL OR rank >= 0",
            name=op.f("ck_attention_observation_evidence_evidence_rank_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["attention_documents.id"],
            name=op.f("fk_attention_observation_evidence_document_id_attention_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["attention_observations.id"],
            name=op.f("fk_attention_observation_evidence_observation_id_attention_observations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attention_observation_evidence")),
        sa.UniqueConstraint(
            "observation_id",
            "document_id",
            "evidence_role",
            name="uq_attention_observation_evidence_relation",
        ),
    )
    op.create_index(
        "ix_attention_observation_evidence_document",
        "attention_observation_evidence",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attention_observation_evidence_document",
        table_name="attention_observation_evidence",
    )
    op.drop_table("attention_observation_evidence")
    op.drop_index(
        "ix_attention_observations_source_channel",
        table_name="attention_observations",
    )
    op.drop_index(
        "ix_attention_observations_topic_window",
        table_name="attention_observations",
    )
    op.drop_table("attention_observations")
    op.drop_index("ix_attention_documents_source_observed", table_name="attention_documents")
    op.drop_table("attention_documents")
