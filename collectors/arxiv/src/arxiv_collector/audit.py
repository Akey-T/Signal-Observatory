"""Read-only arXiv cursor coverage and durable-lineage verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from collector_core import DataIntegrityError, LocalRawStore
from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivRawResponse,
)
from observatory_db.models import (
    IngestionError,
    IngestionRun,
    IngestionStatus,
    Source,
    Topic,
    TopicSourceMapping,
    TopicStatus,
)
from signal_observatory_config import Settings


class ArxivCursorAuditor:
    """Explain cursor coverage and reject advancement without durable evidence."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.raw_store = LocalRawStore(Path(settings.raw_data_path))

    def audit(self) -> dict[str, Any]:
        mappings = list(
            self.session.scalars(
                select(TopicSourceMapping)
                .join(TopicSourceMapping.source)
                .where(Source.name == "arxiv", TopicSourceMapping.enabled.is_(True))
            ).all()
        )
        cursors = list(
            self.session.scalars(
                select(ArxivCollectionCursor).order_by(
                    ArxivCollectionCursor.source_mapping_id,
                    ArxivCollectionCursor.cursor_key,
                )
            ).all()
        )
        parents = [cursor for cursor in cursors if cursor.cursor_key == "incremental"]
        partition_prefixes: dict[UUID, tuple[str, ...]] = {}
        for parent in parents:
            partition = parent.checkpoint.get("partition")
            if not self._valid_partition(partition):
                continue
            assert isinstance(partition, dict)
            prefix = f"incremental-part:{partition['root_from']}:{partition['root_until']}:"
            partition_prefixes[parent.source_mapping_id] = (
                *partition_prefixes.get(parent.source_mapping_id, ()),
                prefix,
            )
        parent_mapping_ids = {cursor.source_mapping_id for cursor in parents}
        mapping_ids = {mapping.id for mapping in mappings}
        mapped_topic_ids = {mapping.topic_id for mapping in mappings}
        active_topic_ids = set(
            self.session.scalars(select(Topic.id).where(Topic.status == TopicStatus.ACTIVE)).all()
        )

        anomalies: dict[str, list[dict[str, str]]] = {
            "cursor_without_durable_run": [],
            "cursor_without_raw_evidence": [],
            "cursor_advanced_past_failure": [],
            "unexplained_cursor_state": [],
        }
        for cursor in cursors:
            self._inspect_cursor(cursor, mapping_ids, partition_prefixes, anomalies)

        reason_counts: dict[str, int] = {}
        for cursor in parents:
            reason = str(cursor.checkpoint.get("reason") or cursor.last_error or "none")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        integrity_failures = sum(len(items) for items in anomalies.values())
        status = "passed" if integrity_failures == 0 else "failed"
        return {
            "status": status,
            "exit_code": 0 if status == "passed" else 2,
            "enabled_arxiv_mappings": len(mappings),
            "incremental_parent_cursors": len(parents),
            "incremental_partition_cursors": sum(
                cursor.mode == "incremental_part" for cursor in cursors
            ),
            "succeeded": sum(cursor.status is ArxivCursorStatus.SUCCEEDED for cursor in parents),
            "partial": sum(cursor.status is ArxivCursorStatus.PARTIAL for cursor in parents),
            "failed": sum(cursor.status is ArxivCursorStatus.FAILED for cursor in parents),
            "pending_or_running": sum(
                cursor.status in {ArxivCursorStatus.PENDING, ArxivCursorStatus.RUNNING}
                for cursor in parents
            ),
            "large_query_partial": sum(
                cursor.status is ArxivCursorStatus.PARTIAL
                and (
                    self._valid_partition(cursor.checkpoint.get("partition"))
                    or self._is_large_query_reason(
                        str(cursor.checkpoint.get("reason") or cursor.last_error or "")
                    )
                )
                for cursor in parents
            ),
            "mapping_without_incremental_cursor": len(mapping_ids - parent_mapping_ids),
            "active_topics_without_arxiv_mapping": len(active_topic_ids - mapped_topic_ids),
            "reason_counts": reason_counts,
            **{name: len(items) for name, items in anomalies.items()},
            "anomalies": anomalies,
            "message": (
                "Cursor advancement has durable run and Raw evidence."
                if status == "passed"
                else "One or more cursor integrity invariants failed."
            ),
            "modified_records": 0,
        }

    def _inspect_cursor(
        self,
        cursor: ArxivCollectionCursor,
        mapping_ids: set[UUID],
        partition_prefixes: dict[UUID, tuple[str, ...]],
        anomalies: dict[str, list[dict[str, str]]],
    ) -> None:
        identity = {
            "cursor_id": str(cursor.id),
            "mapping_id": str(cursor.source_mapping_id),
            "cursor_key": cursor.cursor_key,
        }
        if cursor.source_mapping_id not in mapping_ids:
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "mapping is disabled or absent",
            )
        reason = cursor.checkpoint.get("reason") or cursor.last_error
        if cursor.status in {ArxivCursorStatus.PARTIAL, ArxivCursorStatus.FAILED} and not reason:
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "terminal state has no reason",
            )
        if cursor.status is ArxivCursorStatus.RUNNING and not self._has_active_arxiv_run():
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "cursor is running without an active arXiv ingestion run",
            )
        explicit_root = bool(
            cursor.checkpoint.get("partition_root_from")
            and cursor.checkpoint.get("partition_root_until")
        )
        parent_root = any(
            cursor.cursor_key.startswith(prefix)
            for prefix in partition_prefixes.get(cursor.source_mapping_id, ())
        )
        if cursor.mode == "incremental_part" and not (explicit_root or parent_root):
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "incremental child has no partition root",
            )
        partition = cursor.checkpoint.get("partition")
        if partition is not None and not self._valid_partition(partition):
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "parent partition checkpoint is malformed",
            )
        if cursor.status is not ArxivCursorStatus.SUCCEEDED:
            return
        if (
            cursor.last_successful_run_at is None
            or cursor.last_query_from is None
            or cursor.last_query_until is None
        ):
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "succeeded cursor lacks successful time or query bounds",
            )
            return

        run = self._durable_run(cursor)
        if run is None:
            self._add(
                anomalies,
                "cursor_without_durable_run",
                identity,
                "no terminal ingestion run supports the cursor",
            )
        raws = self._raw_evidence(cursor, run)
        if not raws or not any(self._raw_is_intact(raw) for raw in raws):
            self._add(
                anomalies,
                "cursor_without_raw_evidence",
                identity,
                "no intact immutable Raw response supports the cursor",
            )
        later_error = None
        if cursor.cursor_key == "incremental":
            later_error = self.session.scalar(
                select(IngestionError.id)
                .where(
                    IngestionError.record_identifier == str(cursor.source_mapping_id),
                    IngestionError.occurred_at > cursor.last_successful_run_at,
                )
                .limit(1)
            )
        if later_error is not None:
            self._add(
                anomalies,
                "cursor_advanced_past_failure",
                identity,
                "cursor is succeeded despite a later mapping failure",
            )

    def _durable_run(self, cursor: ArxivCollectionCursor) -> IngestionRun | None:
        run_id_value = cursor.checkpoint.get("last_successful_run_id")
        if run_id_value:
            try:
                run = self.session.get(IngestionRun, UUID(str(run_id_value)))
            except ValueError:
                return None
            if run is not None and run.status in {
                IngestionStatus.SUCCEEDED,
                IngestionStatus.PARTIAL,
                IngestionStatus.FAILED,
            }:
                return run
            return None
        for raw in self._candidate_raws(cursor):
            run = self.session.get(IngestionRun, raw.ingestion_run_id)
            if run is not None and run.status in {
                IngestionStatus.SUCCEEDED,
                IngestionStatus.PARTIAL,
                IngestionStatus.FAILED,
            }:
                return run
        return None

    def _raw_evidence(
        self,
        cursor: ArxivCollectionCursor,
        run: IngestionRun | None,
    ) -> list[ArxivRawResponse]:
        if run is None:
            return []
        return list(
            self.session.scalars(
                select(ArxivRawResponse).where(
                    ArxivRawResponse.source_mapping_id == cursor.source_mapping_id,
                    ArxivRawResponse.ingestion_run_id == run.run_id,
                )
            ).all()
        )

    def _candidate_raws(self, cursor: ArxivCollectionCursor) -> list[ArxivRawResponse]:
        rows = list(
            self.session.scalars(
                select(ArxivRawResponse)
                .where(ArxivRawResponse.source_mapping_id == cursor.source_mapping_id)
                .order_by(ArxivRawResponse.observed_at.desc())
            ).all()
        )
        expected_from = cursor.last_query_from.isoformat() if cursor.last_query_from else None
        expected_until = cursor.last_query_until.isoformat() if cursor.last_query_until else None
        return [
            row
            for row in rows
            if row.request_metadata.get("window_from") == expected_from
            and row.request_metadata.get("window_until") == expected_until
        ]

    def _raw_is_intact(self, raw: ArxivRawResponse) -> bool:
        try:
            path = self.raw_store.resolve_key(raw.raw_path, source="arxiv")
            record = self.raw_store.load(path)
            self.raw_store.read(record)
            return record.sha256 == raw.payload_checksum
        except (OSError, KeyError, TypeError, ValueError, DataIntegrityError):
            return False

    def _has_active_arxiv_run(self) -> bool:
        return (
            self.session.scalar(
                select(IngestionRun.run_id)
                .join(Source, Source.id == IngestionRun.source_id)
                .where(
                    Source.name == "arxiv",
                    IngestionRun.status == IngestionStatus.RUNNING,
                )
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def _valid_partition(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        return bool(
            value.get("root_from")
            and value.get("root_until")
            and isinstance(value.get("pending"), list)
            and isinstance(value.get("completed"), list)
        )

    @staticmethod
    def _is_large_query_reason(reason: str) -> bool:
        normalized = reason.casefold()
        return "large" in normalized and "query" in normalized

    @staticmethod
    def _add(
        anomalies: dict[str, list[dict[str, str]]],
        name: str,
        identity: dict[str, str],
        reason: str,
    ) -> None:
        anomalies[name].append({**identity, "reason": reason})
