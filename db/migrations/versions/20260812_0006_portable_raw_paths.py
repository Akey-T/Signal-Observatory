"""Normalize Raw provenance pointers to portable logical keys."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260812_0006"
down_revision = "20260811_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for table, source in (
        ("arxiv_raw_responses", "arxiv"),
        ("github_raw_responses", "github"),
    ):
        rows = connection.exec_driver_sql(f"SELECT id, raw_path FROM {table}").fetchall()
        for row_id, raw_path in rows:
            logical = _logical_key(str(raw_path), source)
            if logical != raw_path:
                connection.execute(
                    text(f"UPDATE {table} SET raw_path = :raw_path WHERE id = :id"),
                    {"raw_path": logical, "id": row_id},
                )


def downgrade() -> None:
    # Logical keys are valid for the backward-compatible resolver and must not be made machine-local.
    return


def _logical_key(raw_path: str, source: str) -> str:
    normalized = raw_path.replace("\\", "/")
    marker = f"/{source}/"
    if marker in normalized:
        return f"{source}/{normalized.split(marker, 1)[1]}"
    if normalized.startswith(f"{source}/"):
        return normalized
    return raw_path
