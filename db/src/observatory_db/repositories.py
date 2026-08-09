"""Small idempotent repositories for the first Silver entities."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from observatory_db.base import utc_now
from observatory_db.models import IngestionRun, IngestionStatus, Source, Topic


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())


class TopicRepository:
    """Read curated Topics without creating canonical identity from observed text."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_label(self, value: str) -> Topic | None:
        """Resolve a canonical label only among Registry-synchronized Topics."""

        normalized = normalize_label(value)
        if not normalized:
            return None
        return self._session.scalar(select(Topic).where(Topic.normalized_name == normalized))

    def get_by_slug(self, slug: str) -> Topic | None:
        return self._session.scalar(select(Topic).where(Topic.slug == slug))


class IngestionRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start(
        self,
        *,
        source: Source,
        collector_version: str,
        checkpoint_before: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> IngestionRun:
        run = IngestionRun(
            source=source,
            collector_version=collector_version,
            checkpoint_before=dict(checkpoint_before) if checkpoint_before else None,
            metadata_=dict(metadata or {}),
            status=IngestionStatus.RUNNING,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def complete(
        self,
        run: IngestionRun,
        *,
        records_requested: int,
        records_received: int,
        records_inserted: int,
        records_updated: int,
        records_skipped: int,
        error_count: int,
        checkpoint_after: Mapping[str, Any] | None = None,
    ) -> None:
        self._ensure_running(run)
        counts = (
            records_requested,
            records_received,
            records_inserted,
            records_updated,
            records_skipped,
            error_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("ingestion counts cannot be negative")
        run.records_requested = records_requested
        run.records_received = records_received
        run.records_inserted = records_inserted
        run.records_updated = records_updated
        run.records_skipped = records_skipped
        run.error_count = error_count
        run.checkpoint_after = dict(checkpoint_after) if checkpoint_after else None
        run.status = IngestionStatus.SUCCEEDED
        run.finished_at = utc_now()
        self._session.flush()

    def fail(self, run: IngestionRun, *, error_count: int) -> None:
        self._ensure_running(run)
        if error_count < 1:
            raise ValueError("a failed run must record at least one error")
        run.error_count = error_count
        run.status = IngestionStatus.FAILED
        run.finished_at = utc_now()
        self._session.flush()

    @staticmethod
    def _ensure_running(run: IngestionRun) -> None:
        if run.status is not IngestionStatus.RUNNING:
            raise ValueError(f"run {run.run_id} is already terminal")


def get_source(session: Session, source_id: UUID) -> Source | None:
    return session.get(Source, source_id)
