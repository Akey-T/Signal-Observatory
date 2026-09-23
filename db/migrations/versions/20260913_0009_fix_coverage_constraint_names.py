"""Correct duplicated check-constraint prefixes on Topic Source Coverage.

Revision ID: 20260913_0009
Revises: 20260907_0008
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260913_0009"
down_revision: str | None = "20260907_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "topic_source_coverage"
# The third value is the deterministic PostgreSQL rendering of the legacy name.
# PostgreSQL's 63-byte identifier limit caused SQLAlchemy to truncate it and append
# a four-character digest; SQLite retained the full legacy name.
CONSTRAINTS = (
    (
        "observation_count_nonnegative",
        "observation_count >= 0",
        "ck_topic_source_coverage_ck_topic_source_coverage_obser_9d4c",
    ),
    (
        "expected_observation_count_nonnegative",
        "expected_observation_count IS NULL OR expected_observation_count >= 0",
        "ck_topic_source_coverage_ck_topic_source_coverage_expec_e75d",
    ),
    (
        "missing_observation_count_nonnegative",
        "missing_observation_count >= 0",
        "ck_topic_source_coverage_ck_topic_source_coverage_missi_a626",
    ),
)


def _canonical_name(suffix: str) -> str:
    return f"ck_{TABLE_NAME}_{suffix}"


def _legacy_name(suffix: str) -> str:
    canonical_name = _canonical_name(suffix)
    return f"ck_{TABLE_NAME}_{canonical_name}"


def _rename_postgresql_constraint(source_name: str, target_name: str) -> None:
    op.execute(
        sa.text(f'ALTER TABLE "{TABLE_NAME}" RENAME CONSTRAINT "{source_name}" TO "{target_name}"')
    )


def _replace_sqlite_constraints(*, use_legacy_names: bool) -> None:
    with op.batch_alter_table(TABLE_NAME, recreate="always") as batch_op:
        for suffix, condition, _postgresql_legacy_name in CONSTRAINTS:
            source_name = _canonical_name(suffix) if use_legacy_names else _legacy_name(suffix)
            target_name = _legacy_name(suffix) if use_legacy_names else _canonical_name(suffix)
            batch_op.drop_constraint(op.f(source_name), type_="check")
            batch_op.create_check_constraint(op.f(target_name), condition)


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _replace_sqlite_constraints(use_legacy_names=False)
        return

    for suffix, _condition, postgresql_legacy_name in CONSTRAINTS:
        _rename_postgresql_constraint(postgresql_legacy_name, _canonical_name(suffix))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _replace_sqlite_constraints(use_legacy_names=True)
        return

    for suffix, _condition, postgresql_legacy_name in CONSTRAINTS:
        _rename_postgresql_constraint(_canonical_name(suffix), postgresql_legacy_name)
