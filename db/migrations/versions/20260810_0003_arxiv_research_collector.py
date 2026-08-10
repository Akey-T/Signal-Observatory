"""Add arXiv Research Collector Silver schema and lineage.

Revision ID: 20260810_0003
Revises: 20260809_0002
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0003"
down_revision: str | None = "20260809_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
MATCH_METHOD = sa.Enum(
    "ARXIV_API_QUERY", name="arxivmatchmethod", native_enum=False, length=32
)
CURSOR_STATUS = sa.Enum(
    "pending",
    "running",
    "succeeded",
    "partial",
    "failed",
    name="arxivcursorstatus",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "arxiv_papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("arxiv_id", sa.String(length=100), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("primary_category", sa.String(length=100), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("journal_ref", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=500), nullable=True),
        sa.Column("license_url", sa.String(length=1000), nullable=True),
        sa.Column("abs_url", sa.String(length=1000), nullable=False),
        sa.Column("pdf_url", sa.String(length=1000), nullable=True),
        sa.Column("is_withdrawn", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_papers")),
        sa.UniqueConstraint("arxiv_id", name=op.f("uq_arxiv_papers_arxiv_id")),
    )
    op.create_index("ix_arxiv_papers_published_at", "arxiv_papers", ["published_at"])
    op.create_index("ix_arxiv_papers_updated_at", "arxiv_papers", ["updated_at"])

    op.create_table(
        "arxiv_authors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_name", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_authors")),
    )
    op.create_index("ix_arxiv_authors_normalized_name", "arxiv_authors", ["normalized_name"])

    op.create_table(
        "arxiv_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_categories")),
        sa.UniqueConstraint("code", name=op.f("uq_arxiv_categories_code")),
    )

    op.create_table(
        "arxiv_paper_authors",
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_arxiv_paper_authors_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["arxiv_authors.id"],
            name=op.f("fk_arxiv_paper_authors_author_id_arxiv_authors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["arxiv_papers.id"],
            name=op.f("fk_arxiv_paper_authors_paper_id_arxiv_papers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("paper_id", "position", name=op.f("pk_arxiv_paper_authors")),
        sa.UniqueConstraint(
            "paper_id", "author_id", name="uq_arxiv_paper_authors_identity"
        ),
    )
    op.create_index(op.f("ix_arxiv_paper_authors_author_id"), "arxiv_paper_authors", ["author_id"])

    op.create_table(
        "arxiv_paper_categories",
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["arxiv_categories.id"],
            name=op.f("fk_arxiv_paper_categories_category_id_arxiv_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["arxiv_papers.id"],
            name=op.f("fk_arxiv_paper_categories_paper_id_arxiv_papers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "paper_id", "category_id", name=op.f("pk_arxiv_paper_categories")
        ),
    )

    op.create_table(
        "arxiv_raw_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("raw_path", sa.Text(), nullable=False),
        sa.Column("payload_checksum", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("start_index", sa.Integer(), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("sort_by", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.String(length=20), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("response_headers", JSON_TYPE, nullable=False),
        sa.Column("request_metadata", JSON_TYPE, nullable=False),
        sa.Column("parsed_entry_count", sa.Integer(), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_results >= 0", name=op.f("ck_arxiv_raw_responses_max_results_nonnegative")
        ),
        sa.CheckConstraint(
            "start_index >= 0", name=op.f("ck_arxiv_raw_responses_start_index_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_arxiv_raw_responses_ingestion_run_id_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_arxiv_raw_responses_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_arxiv_raw_responses_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_raw_responses")),
        sa.UniqueConstraint("raw_path", name=op.f("uq_arxiv_raw_responses_raw_path")),
    )
    op.create_index(
        "ix_arxiv_raw_responses_run_observed",
        "arxiv_raw_responses",
        ["ingestion_run_id", "observed_at"],
    )
    op.create_index(
        op.f("ix_arxiv_raw_responses_payload_checksum"),
        "arxiv_raw_responses",
        ["payload_checksum"],
    )
    op.create_index(
        op.f("ix_arxiv_raw_responses_source_mapping_id"),
        "arxiv_raw_responses",
        ["source_mapping_id"],
    )
    op.create_index(op.f("ix_arxiv_raw_responses_topic_id"), "arxiv_raw_responses", ["topic_id"])

    op.create_table(
        "arxiv_topic_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("matched_query", sa.Text(), nullable=False),
        sa.Column("match_method", MATCH_METHOD, nullable=False),
        sa.Column("first_matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("last_ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.ForeignKeyConstraint(
            ["first_ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_arxiv_topic_matches_first_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_arxiv_topic_matches_last_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["arxiv_papers.id"],
            name=op.f("fk_arxiv_topic_matches_paper_id_arxiv_papers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_arxiv_topic_matches_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_arxiv_topic_matches_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_topic_matches")),
        sa.UniqueConstraint(
            "paper_id",
            "topic_id",
            "source_mapping_id",
            "matched_query",
            name="uq_arxiv_topic_matches_explainable_identity",
        ),
    )
    op.create_index("ix_arxiv_topic_matches_mapping", "arxiv_topic_matches", ["source_mapping_id"])
    op.create_index(
        "ix_arxiv_topic_matches_topic_paper", "arxiv_topic_matches", ["topic_id", "paper_id"]
    )

    op.create_table(
        "arxiv_paper_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("raw_response_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arxiv_version", sa.Integer(), nullable=True),
        sa.Column("normalized_metadata", JSON_TYPE, nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.run_id"],
            name=op.f("fk_arxiv_paper_observations_ingestion_run_id_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["arxiv_papers.id"],
            name=op.f("fk_arxiv_paper_observations_paper_id_arxiv_papers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_response_id"],
            ["arxiv_raw_responses.id"],
            name=op.f("fk_arxiv_paper_observations_raw_response_id_arxiv_raw_responses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_paper_observations")),
        sa.UniqueConstraint(
            "paper_id", "raw_response_id", name="uq_arxiv_paper_observations_lineage"
        ),
    )
    op.create_index(
        "ix_arxiv_paper_observations_run", "arxiv_paper_observations", ["ingestion_run_id"]
    )

    op.create_table(
        "arxiv_collection_cursors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_mapping_id", sa.Uuid(), nullable=False),
        sa.Column("cursor_key", sa.String(length=250), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_query_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_query_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_start", sa.Integer(), server_default="0", nullable=False),
        sa.Column("checkpoint", JSON_TYPE, nullable=False),
        sa.Column("status", CURSOR_STATUS, server_default="pending", nullable=False),
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
        sa.CheckConstraint(
            "next_start >= 0", name=op.f("ck_arxiv_collection_cursors_next_start_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["source_mapping_id"],
            ["topic_source_mappings.id"],
            name=op.f("fk_arxiv_collection_cursors_source_mapping_id_topic_source_mappings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_arxiv_collection_cursors_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_collection_cursors")),
        sa.UniqueConstraint(
            "source_mapping_id",
            "cursor_key",
            name="uq_arxiv_collection_cursors_mapping_key",
        ),
    )
    op.create_index(
        "ix_arxiv_collection_cursors_topic", "arxiv_collection_cursors", ["topic_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_arxiv_collection_cursors_topic", table_name="arxiv_collection_cursors")
    op.drop_table("arxiv_collection_cursors")
    op.drop_index("ix_arxiv_paper_observations_run", table_name="arxiv_paper_observations")
    op.drop_table("arxiv_paper_observations")
    op.drop_index("ix_arxiv_topic_matches_topic_paper", table_name="arxiv_topic_matches")
    op.drop_index("ix_arxiv_topic_matches_mapping", table_name="arxiv_topic_matches")
    op.drop_table("arxiv_topic_matches")
    op.drop_index(op.f("ix_arxiv_raw_responses_topic_id"), table_name="arxiv_raw_responses")
    op.drop_index(
        op.f("ix_arxiv_raw_responses_source_mapping_id"), table_name="arxiv_raw_responses"
    )
    op.drop_index(
        op.f("ix_arxiv_raw_responses_payload_checksum"), table_name="arxiv_raw_responses"
    )
    op.drop_index("ix_arxiv_raw_responses_run_observed", table_name="arxiv_raw_responses")
    op.drop_table("arxiv_raw_responses")
    op.drop_table("arxiv_paper_categories")
    op.drop_index(op.f("ix_arxiv_paper_authors_author_id"), table_name="arxiv_paper_authors")
    op.drop_table("arxiv_paper_authors")
    op.drop_table("arxiv_categories")
    op.drop_index("ix_arxiv_authors_normalized_name", table_name="arxiv_authors")
    op.drop_table("arxiv_authors")
    op.drop_index("ix_arxiv_papers_updated_at", table_name="arxiv_papers")
    op.drop_index("ix_arxiv_papers_published_at", table_name="arxiv_papers")
    op.drop_table("arxiv_papers")
