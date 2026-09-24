"""Read-only arXiv cursor coverage and durable-lineage verification."""

from __future__ import annotations

from datetime import datetime, timedelta
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
            self._inspect_cursor(cursor, mapping_ids, anomalies)

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
        if cursor.mode == "incremental_part" and not self._has_partition_root_evidence(cursor):
            self._add(
                anomalies,
                "unexplained_cursor_state",
                identity,
                "incremental child has no uniquely evidenced partition root",
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
        rows = list(
            self.session.scalars(
                select(ArxivRawResponse).where(
                    ArxivRawResponse.source_mapping_id == cursor.source_mapping_id,
                    ArxivRawResponse.ingestion_run_id == run.run_id,
                )
            ).all()
        )
        if cursor.mode != "incremental_part":
            return rows
        expected_from = cursor.last_query_from.isoformat() if cursor.last_query_from else None
        expected_until = cursor.last_query_until.isoformat() if cursor.last_query_until else None
        return [
            row
            for row in rows
            if row.request_metadata.get("mode") == "incremental_part"
            and row.request_metadata.get("window_from") == expected_from
            and row.request_metadata.get("window_until") == expected_until
        ]

    def _has_partition_root_evidence(self, cursor: ArxivCollectionCursor) -> bool:
        """Accept old child checkpoints only when immutable root Raw proves their key."""
        child_from = cursor.window_from
        child_until = cursor.window_until
        if child_from is None or child_until is None or child_from >= child_until:
            return False
        checkpoint = cursor.checkpoint
        if checkpoint.get("mapping_id") not in (None, str(cursor.source_mapping_id)):
            return False
        if checkpoint.get("window_from") not in (None, child_from.isoformat()):
            return False
        if checkpoint.get("window_until") not in (None, child_until.isoformat()):
            return False
        explicit_from = checkpoint.get("partition_root_from")
        explicit_until = checkpoint.get("partition_root_until")
        if (explicit_from is None) != (explicit_until is None):
            return False
        if cursor.status is ArxivCursorStatus.SUCCEEDED and (
            cursor.last_query_from != child_from or cursor.last_query_until != child_until
        ):
            return False

        roots: set[tuple[str, str, str]] = set()
        rows = self.session.scalars(
            select(ArxivRawResponse).where(
                ArxivRawResponse.source_mapping_id == cursor.source_mapping_id,
                ArxivRawResponse.topic_id == cursor.topic_id,
                ArxivRawResponse.start_index == 0,
                ArxivRawResponse.http_status == 200,
            )
        )
        for raw in rows:
            metadata = raw.request_metadata
            root_from = metadata.get("window_from")
            root_until = metadata.get("window_until")
            if metadata.get("mode") != "incremental":
                continue
            if not isinstance(root_from, str) or not isinstance(root_until, str):
                continue
            key = (
                f"incremental-part:{root_from}:{root_until}:"
                f"{child_from.isoformat()}:{child_until.isoformat()}"
            )
            if key != cursor.cursor_key:
                continue
            try:
                start = datetime.fromisoformat(root_from)
                end = datetime.fromisoformat(root_until)
            except ValueError:
                continue
            if (
                start.utcoffset() != timedelta(0)
                or end.utcoffset() != timedelta(0)
                or not (start <= child_from < child_until <= end)
                or (explicit_from is not None and explicit_from != root_from)
                or (explicit_until is not None and explicit_until != root_until)
                or raw.observed_at > cursor.created_at
                or raw.parse_error is not None
            ):
                continue
            run = self.session.get(IngestionRun, raw.ingestion_run_id)
            if run is None or run.status not in {
                IngestionStatus.SUCCEEDED,
                IngestionStatus.PARTIAL,
                IngestionStatus.FAILED,
            }:
                continue
            source = self.session.get(Source, run.source_id)
            if source is None or source.name != "arxiv":
                continue
            if explicit_from is None and not self._root_run_has_child(raw, root_from, root_until):
                continue
            if self._raw_is_intact(raw):
                roots.add((root_from, root_until, raw.query))
        return len(roots) == 1

    def _root_run_has_child(
        self, root_raw: ArxivRawResponse, root_from: str, root_until: str
    ) -> bool:
        """A historical root probe must share its run with a persisted partition child."""
        rows = self.session.scalars(
            select(ArxivRawResponse).where(
                ArxivRawResponse.source_mapping_id == root_raw.source_mapping_id,
                ArxivRawResponse.ingestion_run_id == root_raw.ingestion_run_id,
            )
        )
        for child_raw in rows:
            metadata = child_raw.request_metadata
            child_from = metadata.get("window_from")
            child_until = metadata.get("window_until")
            if metadata.get("mode") != "incremental_part":
                continue
            if not isinstance(child_from, str) or not isinstance(child_until, str):
                continue
            key = f"incremental-part:{root_from}:{root_until}:{child_from}:{child_until}"
            child = self.session.scalar(
                select(ArxivCollectionCursor).where(
                    ArxivCollectionCursor.source_mapping_id == root_raw.source_mapping_id,
                    ArxivCollectionCursor.topic_id == root_raw.topic_id,
                    ArxivCollectionCursor.mode == "incremental_part",
                    ArxivCollectionCursor.cursor_key == key,
                )
            )
            if (
                child is not None
                and child.window_from is not None
                and child.window_until is not None
                and child.window_from.isoformat() == child_from
                and child.window_until.isoformat() == child_until
                and self._raw_is_intact(child_raw)
            ):
                return True
        return False

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
