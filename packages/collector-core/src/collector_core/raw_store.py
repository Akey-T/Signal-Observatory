"""Immutable, deterministic, checksummed local Bronze storage."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class DataIntegrityError(RuntimeError):
    """Raised when persisted Bronze bytes no longer match their checksum."""


@dataclass(frozen=True, slots=True)
class RawRecord:
    directory: Path
    source: str
    request_timestamp: datetime
    collector_version: str
    schema_version: str
    sha256: str
    uncompressed_bytes: int
    source_metadata: dict[str, Any]

    @property
    def payload_path(self) -> Path:
        return self.directory / "payload.gz"

    @property
    def metadata_path(self) -> Path:
        return self.directory / "metadata.json"


class LocalRawStore:
    """Store each observation as one atomically published immutable directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write(
        self,
        *,
        source: str,
        payload: bytes,
        request_timestamp: datetime,
        collector_version: str,
        schema_version: str,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> RawRecord:
        self._validate_source(source)
        timestamp = self._require_utc(request_timestamp)
        checksum = hashlib.sha256(payload).hexdigest()
        day_directory = (
            self.root
            / source
            / f"{timestamp.year:04d}"
            / f"{timestamp.month:02d}"
            / f"{timestamp.day:02d}"
        )
        record_name = f"{timestamp.strftime('%Y%m%dT%H%M%S.%fZ')}_{checksum}"
        final_directory = day_directory / record_name
        day_directory.mkdir(parents=True, exist_ok=True)

        if final_directory.exists():
            record = self.load(final_directory)
            self.read(record)
            return record

        temporary_directory = Path(tempfile.mkdtemp(prefix=".tmp-", dir=day_directory))
        metadata = {
            "source": source,
            "request_timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "collector_version": collector_version,
            "schema_version": schema_version,
            "sha256": checksum,
            "uncompressed_bytes": len(payload),
            "source_metadata": dict(source_metadata or {}),
        }
        try:
            self._write_payload(temporary_directory / "payload.gz", payload)
            self._write_metadata(temporary_directory / "metadata.json", metadata)
            try:
                os.rename(temporary_directory, final_directory)
            except FileExistsError:
                shutil.rmtree(temporary_directory)
            self._sync_directory(day_directory)
        except BaseException:
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory)
            raise

        record = self.load(final_directory)
        self.read(record)
        return record

    def read(self, record: RawRecord) -> bytes:
        with gzip.open(record.payload_path, "rb") as compressed:
            payload = compressed.read()
        actual_checksum = hashlib.sha256(payload).hexdigest()
        if actual_checksum != record.sha256:
            raise DataIntegrityError(
                f"checksum mismatch for {record.directory}: "
                f"expected {record.sha256}, got {actual_checksum}"
            )
        if len(payload) != record.uncompressed_bytes:
            raise DataIntegrityError(f"length mismatch for {record.directory}")
        return payload

    def load(self, directory: str | Path) -> RawRecord:
        record_directory = Path(directory)
        with (record_directory / "metadata.json").open(encoding="utf-8") as metadata_file:
            metadata: dict[str, Any] = json.load(metadata_file)
        timestamp = datetime.fromisoformat(
            str(metadata["request_timestamp"]).replace("Z", "+00:00")
        )
        return RawRecord(
            directory=record_directory,
            source=str(metadata["source"]),
            request_timestamp=self._require_utc(timestamp),
            collector_version=str(metadata["collector_version"]),
            schema_version=str(metadata["schema_version"]),
            sha256=str(metadata["sha256"]),
            uncompressed_bytes=int(metadata["uncompressed_bytes"]),
            source_metadata=dict(metadata["source_metadata"]),
        )

    def iter_records(self, source: str) -> Iterator[RawRecord]:
        self._validate_source(source)
        source_root = self.root / source
        if not source_root.exists():
            return
        for metadata_path in sorted(source_root.glob("*/*/*/*/metadata.json")):
            yield self.load(metadata_path.parent)

    def logical_key(self, directory: str | Path, *, source: str) -> str:
        """Return a portable Raw identity relative to this store's root."""

        self._validate_source(source)
        candidate = Path(directory)
        try:
            relative = candidate.resolve().relative_to(self.root.resolve())
        except ValueError:
            parts = candidate.parts
            try:
                source_index = next(index for index, part in enumerate(parts) if part == source)
            except StopIteration as error:
                raise ValueError(f"Raw path is outside the configured root: {candidate}") from error
            relative = Path(*parts[source_index:])
        if relative.parts[0] != source or ".." in relative.parts:
            raise ValueError(f"invalid Raw logical key: {relative}")
        return relative.as_posix()

    def resolve_key(self, raw_path: str | Path, *, source: str) -> Path:
        """Resolve logical keys and legacy absolute pointers under the configured root."""

        self._validate_source(source)
        persisted = Path(raw_path)
        if persisted.is_absolute():
            try:
                persisted.resolve().relative_to(self.root.resolve())
            except ValueError:
                pass
            else:
                return persisted.resolve()
        parts = persisted.parts
        try:
            source_index = next(index for index, part in enumerate(parts) if part == source)
        except StopIteration as error:
            raise ValueError(f"Raw pointer has no {source!r} source segment") from error
        relative = Path(*parts[source_index:])
        resolved = (self.root / relative).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as error:
            raise ValueError("Raw pointer escapes the configured root") from error
        return resolved

    @staticmethod
    def _write_payload(path: Path, payload: bytes) -> None:
        with path.open("xb") as raw_file:
            with gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as compressed:
                compressed.write(payload)
            raw_file.flush()
            os.fsync(raw_file.fileno())

    @staticmethod
    def _write_metadata(path: Path, metadata: Mapping[str, Any]) -> None:
        with path.open("x", encoding="utf-8", newline="\n") as metadata_file:
            json.dump(metadata, metadata_file, sort_keys=True, separators=(",", ":"))
            metadata_file.write("\n")
            metadata_file.flush()
            os.fsync(metadata_file.fileno())

    @staticmethod
    def _validate_source(source: str) -> None:
        if SOURCE_PATTERN.fullmatch(source) is None:
            raise ValueError("source must match ^[a-z0-9][a-z0-9_-]*$")

    @staticmethod
    def _require_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("request_timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _sync_directory(path: Path) -> None:
        if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
            return
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
