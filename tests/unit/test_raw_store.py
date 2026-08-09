from __future__ import annotations

import gzip
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from collector_core import DataIntegrityError, LocalRawStore


def test_raw_store_write_read_and_deterministic_layout(tmp_path: Path) -> None:
    store = LocalRawStore(tmp_path)
    timestamp = datetime(2026, 8, 9, 3, 4, 5, 123456, tzinfo=UTC)
    payload = b'{"signal":"example"}'

    record = store.write(
        source="example-api",
        payload=payload,
        request_timestamp=timestamp,
        collector_version="1.0.0",
        schema_version="1",
        source_metadata={"endpoint": "/signals"},
    )

    assert record.directory.parent == tmp_path / "example-api" / "2026" / "08" / "09"
    assert record.directory.name.startswith("20260809T030405.123456Z_")
    assert store.read(record) == payload
    assert record.metadata_path.is_file()
    assert record.payload_path.is_file()


def test_duplicate_write_is_idempotent(tmp_path: Path) -> None:
    store = LocalRawStore(tmp_path)
    first = store.write(
        source="example-api",
        payload=b"same immutable bytes",
        request_timestamp=datetime(2026, 8, 9, tzinfo=UTC),
        collector_version="1.0.0",
        schema_version="1",
    )
    first_metadata = first.metadata_path.read_bytes()
    second = store.write(
        source="example-api",
        payload=b"same immutable bytes",
        request_timestamp=datetime(2026, 8, 9, tzinfo=UTC),
        collector_version="1.0.0",
        schema_version="1",
    )

    assert second.directory == first.directory
    assert second.metadata_path.read_bytes() == first_metadata
    assert list(store.iter_records("example-api")) == [first]


def test_checksum_detects_modified_payload(tmp_path: Path) -> None:
    store = LocalRawStore(tmp_path)
    record = store.write(
        source="example-api",
        payload=b"original",
        request_timestamp=datetime(2026, 8, 9, tzinfo=UTC),
        collector_version="1.0.0",
        schema_version="1",
    )
    record.payload_path.write_bytes(gzip.compress(b"modified", mtime=0))

    with pytest.raises(DataIntegrityError, match="checksum mismatch"):
        store.read(record)


def test_failed_publish_leaves_no_partial_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalRawStore(tmp_path)

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr(os, "rename", fail_rename)
    with pytest.raises(OSError, match="simulated"):
        store.write(
            source="example-api",
            payload=b"payload",
            request_timestamp=datetime(2026, 8, 9, tzinfo=UTC),
            collector_version="1.0.0",
            schema_version="1",
        )

    day = tmp_path / "example-api" / "2026" / "08" / "09"
    assert list(day.iterdir()) == []


def test_source_name_cannot_escape_store_root(tmp_path: Path) -> None:
    store = LocalRawStore(tmp_path)
    with pytest.raises(ValueError, match="source must match"):
        store.write(
            source="../outside",
            payload=b"payload",
            request_timestamp=datetime.now(UTC),
            collector_version="1.0.0",
            schema_version="1",
        )
