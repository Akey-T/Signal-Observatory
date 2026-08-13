"""Bounded read-only integrity checks for immutable Raw evidence."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from collector_core import DataIntegrityError, LocalRawStore
from observatory_operations.source_recovery import (
    SOURCE_RECOVERY_ADAPTERS,
    recovery_source_names,
)


@dataclass(frozen=True, slots=True)
class RawPointer:
    id: UUID
    source: str
    raw_path: str
    checksum: str
    observed_at: datetime


class RawIntegrityVerifier:
    def __init__(self, session: Session, raw_root: str | Path) -> None:
        self.session = session
        self.raw_root = Path(raw_root)
        self.raw_store = LocalRawStore(self.raw_root)

    def verify(
        self,
        *,
        sample: int = 100,
        source: str | None = None,
        full: bool = False,
    ) -> dict[str, Any]:
        if sample < 1 or sample > 10000:
            raise ValueError("Raw integrity sample must be between 1 and 10000")
        if source is not None and source not in SOURCE_RECOVERY_ADAPTERS:
            raise ValueError(
                "Raw integrity source must have a registered recovery adapter: "
                + ", ".join(recovery_source_names())
            )
        pointers, available = self._pointers(source=source, sample=sample, full=full)
        failures: list[dict[str, str]] = []
        for pointer in pointers:
            path = self.resolve_path(pointer.raw_path, pointer.source)
            try:
                self.verify_raw_directory(path, expected_checksum=pointer.checksum)
            except (OSError, KeyError, TypeError, ValueError, DataIntegrityError) as error:
                failures.append(
                    {
                        "source": pointer.source,
                        "raw_id": str(pointer.id),
                        "raw_path": pointer.raw_path,
                        "reason": str(error),
                    }
                )
        state = "not_initialized" if available == 0 else "pass" if not failures else "fail"
        return {
            "state": state,
            "mode": "full" if full else "sample",
            "source": source,
            "records_available": available,
            "records_checked": len(pointers),
            "failures": len(failures),
            "failure_details": failures[:100],
            "checks": [
                "db_pointer_exists",
                "filesystem_object_exists",
                "metadata_sidecar_exists",
                "checksum_matches",
            ],
            "modified_records": 0,
        }

    def resolve_path(self, raw_path: str, source: str) -> Path:
        return self.raw_store.resolve_key(raw_path, source=source)

    @staticmethod
    def verify_raw_directory(path: Path, *, expected_checksum: str | None = None) -> None:
        """Apply the shared immutable Raw integrity rules to one record directory."""

        if not path.is_dir():
            raise FileNotFoundError("Raw pointer directory does not exist")
        if not (path / "metadata.json").is_file():
            raise FileNotFoundError("metadata sidecar does not exist")
        if not (path / "payload.gz").is_file():
            raise FileNotFoundError("compressed payload does not exist")
        store = LocalRawStore(path.parent)
        record = store.load(path)
        if expected_checksum is not None and record.sha256 != expected_checksum:
            raise DataIntegrityError("expected checksum does not match the Raw metadata sidecar")
        store.read(record)

    def _pointers(
        self, *, source: str | None, sample: int, full: bool
    ) -> tuple[list[RawPointer], int]:
        sources = [source] if source else list(recovery_source_names())
        available = 0
        candidates: list[RawPointer] = []
        for source_name in sources:
            model = SOURCE_RECOVERY_ADAPTERS[source_name].raw_model
            source_count = int(self.session.scalar(select(func.count()).select_from(model)) or 0)
            available += source_count
            statement = select(
                model.id,
                model.raw_path,
                model.payload_checksum,
                model.observed_at,
            ).order_by(model.observed_at.desc())
            if not full:
                statement = statement.limit(sample)
            for raw_id, raw_path, checksum, observed_at in self.session.execute(statement):
                candidates.append(
                    RawPointer(
                        id=raw_id,
                        source=source_name,
                        raw_path=raw_path,
                        checksum=checksum,
                        observed_at=observed_at,
                    )
                )
        if full or len(candidates) <= sample:
            return sorted(candidates, key=lambda pointer: pointer.observed_at), available
        return random.Random(0).sample(candidates, sample), available
