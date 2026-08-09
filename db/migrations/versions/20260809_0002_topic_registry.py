"""Add curated Topic Registry persistence.

Revision ID: 20260809_0002
Revises: 20260809_0001
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260809_0002"
down_revision: str | None = "20260809_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TOPIC_STATUS = sa.Enum(
    "active", "paused", "deprecated", name="topicstatus", native_enum=False, length=16
)
ALIAS_STATUS = sa.Enum("active", "deprecated", name="aliasstatus", native_enum=False, length=16)
ALIAS_TYPE = sa.Enum(
    "name",
    "abbreviation",
    "spelling",
    "product_name",
    "related_term",
    "search_term",
    name="aliastype",
    native_enum=False,
    length=24,
)
MATCH_MODE = sa.Enum("exact", "phrase", name="matchmode", native_enum=False, length=16)


def upgrade() -> None:
    op.create_table(
        "topic_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
            "sort_order >= 0", name=op.f("ck_topic_categories_sort_order_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["topic_categories.id"],
            name=op.f("fk_topic_categories_parent_id_topic_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_topic_categories_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_topic_categories_slug")),
    )
    op.create_index(
        op.f("ix_topic_categories_parent_id"), "topic_categories", ["parent_id"], unique=False
    )
    op.create_table(
        "topic_registry_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("source_file_count", sa.Integer(), nullable=False),
        sa.Column("topic_count", sa.Integer(), nullable=False),
        sa.Column("alias_count", sa.Integer(), nullable=False),
        sa.Column("mapping_count", sa.Integer(), nullable=False),
        sa.Column("applied_by", sa.String(length=200), nullable=False),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.CheckConstraint(
            "alias_count >= 0", name=op.f("ck_topic_registry_versions_alias_count_nonnegative")
        ),
        sa.CheckConstraint(
            "mapping_count >= 0", name=op.f("ck_topic_registry_versions_mapping_count_nonnegative")
        ),
        sa.CheckConstraint(
            "source_file_count >= 0",
            name=op.f("ck_topic_registry_versions_source_file_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "topic_count >= 0", name=op.f("ck_topic_registry_versions_topic_count_nonnegative")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_topic_registry_versions_version_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_registry_versions")),
        sa.UniqueConstraint("version", name=op.f("uq_topic_registry_versions_version")),
    )
    op.create_index(
        op.f("ix_topic_registry_versions_checksum"),
        "topic_registry_versions",
        ["checksum"],
        unique=False,
    )

    with op.batch_alter_table("topics") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("status", TOPIC_STATUS, server_default="active", nullable=False)
        )
        batch_op.add_column(
            sa.Column("monitoring_priority", sa.Integer(), server_default="50", nullable=False)
        )
        batch_op.add_column(sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("registry_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("metadata", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False)
        )
        batch_op.create_check_constraint(
            "monitoring_priority_range",
            "monitoring_priority >= 0 AND monitoring_priority <= 100",
        )
        batch_op.create_foreign_key(
            "fk_topics_category_id_topic_categories",
            "topic_categories",
            ["category_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(op.f("ix_topics_category_id"), ["category_id"], unique=False)
        batch_op.create_index(op.f("ix_topics_status"), ["status"], unique=False)

    op.drop_index("uq_topic_aliases_global_normalized_alias", table_name="topic_aliases")
    with op.batch_alter_table("topic_aliases") as batch_op:
        batch_op.add_column(
            sa.Column("alias_type", ALIAS_TYPE, server_default="name", nullable=False)
        )
        batch_op.add_column(
            sa.Column("match_mode", MATCH_MODE, server_default="exact", nullable=False)
        )
        batch_op.add_column(
            sa.Column("case_sensitive", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("status", ALIAS_STATUS, server_default="active", nullable=False)
        )
        batch_op.add_column(
            sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("metadata", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False)
        )
        batch_op.create_check_constraint("confidence_range", "confidence >= 0 AND confidence <= 1")
        batch_op.create_unique_constraint(
            "uq_topic_aliases_topic_normalized_alias", ["topic_id", "normalized_alias"]
        )

    op.create_table(
        "topic_source_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mapping_type", sa.String(length=100), nullable=False),
        sa.Column("external_identifier", sa.String(length=500), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("configuration", JSON_TYPE, nullable=False),
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
            name=op.f("fk_topic_source_mappings_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_topic_source_mappings_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_source_mappings")),
        sa.UniqueConstraint(
            "topic_id",
            "source_id",
            "mapping_type",
            name="uq_topic_source_mappings_identity",
        ),
    )
    op.create_index(
        op.f("ix_topic_source_mappings_source_id"),
        "topic_source_mappings",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_topic_source_mappings_topic_id"),
        "topic_source_mappings",
        ["topic_id"],
        unique=False,
    )
    op.create_table(
        "topic_registry_audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=500), nullable=False),
        sa.Column("before", JSON_TYPE, nullable=True),
        sa.Column("after", JSON_TYPE, nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["topic_registry_versions.id"],
            name=op.f("fk_topic_registry_audit_log_version_id_topic_registry_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_registry_audit_log")),
    )
    op.create_index(
        "ix_topic_registry_audit_version_timestamp",
        "topic_registry_audit_log",
        ["version_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_topic_registry_audit_version_timestamp", table_name="topic_registry_audit_log"
    )
    op.drop_table("topic_registry_audit_log")
    op.drop_index(op.f("ix_topic_source_mappings_topic_id"), table_name="topic_source_mappings")
    op.drop_index(op.f("ix_topic_source_mappings_source_id"), table_name="topic_source_mappings")
    op.drop_table("topic_source_mappings")

    with op.batch_alter_table("topic_aliases") as batch_op:
        batch_op.drop_constraint("uq_topic_aliases_topic_normalized_alias", type_="unique")
        batch_op.drop_constraint("confidence_range", type_="check")
        batch_op.drop_column("metadata")
        batch_op.drop_column("confidence")
        batch_op.drop_column("status")
        batch_op.drop_column("case_sensitive")
        batch_op.drop_column("match_mode")
        batch_op.drop_column("alias_type")
    op.create_index(
        "uq_topic_aliases_global_normalized_alias",
        "topic_aliases",
        ["normalized_alias"],
        unique=True,
        postgresql_where=sa.text("source_id IS NULL"),
        sqlite_where=sa.text("source_id IS NULL"),
    )

    with op.batch_alter_table("topics") as batch_op:
        batch_op.drop_index(op.f("ix_topics_status"))
        batch_op.drop_index(op.f("ix_topics_category_id"))
        batch_op.drop_constraint("fk_topics_category_id_topic_categories", type_="foreignkey")
        batch_op.drop_constraint("monitoring_priority_range", type_="check")
        batch_op.drop_column("metadata")
        batch_op.drop_column("registry_version")
        batch_op.drop_column("deprecated_at")
        batch_op.drop_column("monitoring_priority")
        batch_op.drop_column("status")
        batch_op.drop_column("category_id")

    op.drop_index(op.f("ix_topic_registry_versions_checksum"), table_name="topic_registry_versions")
    op.drop_table("topic_registry_versions")
    op.drop_index(op.f("ix_topic_categories_parent_id"), table_name="topic_categories")
    op.drop_table("topic_categories")
