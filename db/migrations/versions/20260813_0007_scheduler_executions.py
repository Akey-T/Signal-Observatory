"""Persist expected scheduler windows and their terminal outcomes.

Revision ID: 20260813_0007
Revises: 20260812_0006
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0007"
down_revision: str | None = "20260812_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
SCHEDULER_STATUS = sa.Enum(
    "scheduled",
    "running",
    "succeeded",
    "failed",
    "missed",
    "interrupted",
    name="schedulerexecutionstatus",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "scheduler_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", SCHEDULER_STATUS, nullable=False),
        sa.Column("error_type", sa.String(length=200), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduler_executions")),
        sa.UniqueConstraint(
            "job_name",
            "scheduled_at",
            name="uq_scheduler_execution_window",
        ),
    )
    op.create_index(
        "ix_scheduler_executions_job_scheduled",
        "scheduler_executions",
        ["job_name", "scheduled_at"],
    )
    op.create_index(
        "ix_scheduler_executions_status_scheduled",
        "scheduler_executions",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduler_executions_status_scheduled",
        table_name="scheduler_executions",
    )
    op.drop_index(
        "ix_scheduler_executions_job_scheduled",
        table_name="scheduler_executions",
    )
    op.drop_table("scheduler_executions")
