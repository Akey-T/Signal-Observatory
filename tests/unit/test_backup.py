from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from collector_core import LocalRawStore
from observatory_operations.backup import (
    BackupError,
    BackupVerifier,
    RawBackupCopier,
    generate_backup_id,
    sha256_file,
)
from observatory_operations.backup_models import (
    BackupManifest,
    CoverageManifest,
    DatabaseManifest,
    RawManifestEntry,
    RawManifestSummary,
    RegistryManifest,
    SourceManifest,
)
from observatory_operations.postgres_backup import PostgresToolError


class FakePostgresTool:
    def client_version(self) -> str:
        return "18.0"

    def dump(self, database_url: str, target: Path, *, snapshot: str | None = None) -> None:
        del database_url, snapshot
        target.write_bytes(b"PGDMP-test-catalog")

    def validate_dump(self, dump_path: Path) -> None:
        if not dump_path.read_bytes().startswith(b"PGDMP"):
            raise PostgresToolError("invalid fake dump")

    def restore(self, database_url: str, dump_path: Path) -> None:
        del database_url
        self.validate_dump(dump_path)


def make_manifest(
    backup_id: str,
    *,
    dump_path: Path,
    raw: RawManifestSummary,
    registry_checksum: str,
    registry_bytes: int,
) -> BackupManifest:
    now = datetime(2026, 8, 12, 3, tzinfo=UTC)
    return BackupManifest(
        backup_id=backup_id,
        backup_started_at=now,
        backup_completed_at=now,
        application_version="0.1.0",
        git_commit_if_available=None,
        database=DatabaseManifest(
            server_version="18.0",
            migration_head="20260812_0006",
            table_count=27,
            size_bytes=dump_path.stat().st_size,
            sha256=sha256_file(dump_path),
            counts={},
        ),
        registry=RegistryManifest(
            version=None,
            checksum=None,
            topic_count=0,
            config_checksum=registry_checksum,
            config_bytes=registry_bytes,
        ),
        raw=raw,
        sources={
            "arxiv": SourceManifest(
                entity_count=0,
                match_count=0,
                raw_response_count=1,
            ),
            "github": SourceManifest(
                entity_count=0,
                match_count=0,
                raw_response_count=1,
            ),
        },
        coverage=CoverageManifest(projection_count=0),
        verification_state="pass",
        total_backup_bytes=dump_path.stat().st_size + raw.total_bytes + registry_bytes,
    )


def test_backup_id_is_unique_utc_and_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    now = datetime(2026, 8, 12, 3, tzinfo=UTC)
    first = generate_backup_id(now)
    second = generate_backup_id(now)
    assert first.startswith("20260812T030000Z-")
    assert first != second

    dump_path = tmp_path / "postgres.dump"
    dump_path.write_bytes(b"PGDMP")
    manifest = make_manifest(
        first,
        dump_path=dump_path,
        raw=RawManifestSummary(
            file_count=0,
            total_bytes=0,
            manifest_sha256="0" * 64,
        ),
        registry_checksum="0" * 64,
        registry_bytes=0,
    )
    payload = manifest.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="unexpected"):
        BackupManifest.model_validate(payload)

    extended = manifest.model_copy(
        update={
            "sources": {
                **manifest.sources,
                "hacker_news": SourceManifest(
                    entity_count=0,
                    match_count=0,
                    raw_response_count=0,
                ),
            }
        }
    )
    assert set(BackupManifest.model_validate(extended.model_dump()).sources) == {
        "arxiv",
        "github",
        "hacker_news",
    }
    entry = RawManifestEntry(
        path="hacker_news/2026/08/13/record",
        size_bytes=1,
        sha256="0" * 64,
        sidecar=True,
        sidecar_size_bytes=1,
        sidecar_sha256="1" * 64,
        source_checksum="2" * 64,
    )
    assert entry.path.startswith("hacker_news/")


def test_raw_copy_and_full_verification_detect_corruption(tmp_path: Path) -> None:
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    backup.mkdir()
    for index, name in enumerate(("arxiv", "github")):
        LocalRawStore(source).write(
            source=name,
            payload=f"payload-{name}".encode(),
            request_timestamp=datetime(2026, 8, 12, 3, index, tzinfo=UTC),
            collector_version="test",
            schema_version="1",
        )
    raw = RawBackupCopier(source).copy(
        backup / "raw",
        backup / "raw-manifest.jsonl.gz",
    )
    assert raw.file_count == 2
    with gzip.open(backup / "raw-manifest.jsonl.gz", "rt", encoding="utf-8") as stream:
        entries = [json.loads(line) for line in stream]
    assert [entry["path"].split("/", 1)[0] for entry in entries] == ["arxiv", "github"]

    dump = backup / "postgres.dump"
    dump.write_bytes(b"PGDMP-test-catalog")
    registry = backup / "registry" / "topics"
    registry.mkdir(parents=True)
    (registry / "registry.yaml").write_text(
        "schema_version: 1\ncategories: []\ntopics: []\nallowed_alias_collisions: []\n",
        encoding="utf-8",
    )
    from observatory_operations.backup import tree_checksum
    from topic_registry.loader import TopicRegistryLoader

    config_checksum, config_bytes = tree_checksum(registry)
    loaded = TopicRegistryLoader(registry).load()
    manifest = make_manifest(
        "20260812T030000Z-a1b2c3",
        dump_path=dump,
        raw=raw,
        registry_checksum=config_checksum,
        registry_bytes=config_bytes,
    ).model_copy(
        update={
            "registry": RegistryManifest(
                version=None,
                checksum=loaded.checksum,
                topic_count=0,
                config_checksum=config_checksum,
                config_bytes=config_bytes,
            )
        }
    )
    (backup / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    verifier = BackupVerifier(FakePostgresTool())
    assert verifier.verify(backup).result == "pass"

    payload = next((backup / "raw").glob("arxiv/*/*/*/*/payload.gz"))
    payload.write_bytes(b"corrupted")
    report = verifier.verify(backup)
    assert report.result == "fail"
    assert report.raw_checksum_failures > 0


def test_raw_copy_rejects_symlinked_record(tmp_path: Path) -> None:
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks unsupported")
    source = tmp_path / "source"
    external = tmp_path / "external"
    external.mkdir()
    record = LocalRawStore(source).write(
        source="arxiv",
        payload=b"payload",
        request_timestamp=datetime(2026, 8, 12, tzinfo=UTC),
        collector_version="test",
        schema_version="1",
    )
    original = record.payload_path
    link_target = external / "payload.gz"
    original.replace(link_target)
    try:
        original.symlink_to(link_target)
    except OSError:
        pytest.skip("creating symlinks requires platform permission")
    with pytest.raises(BackupError, match="symlink"):
        RawBackupCopier(source).copy(tmp_path / "copy", tmp_path / "manifest.gz")


def test_raw_copy_fails_closed_for_unregistered_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    LocalRawStore(source).write(
        source="hacker_news",
        payload=b"payload",
        request_timestamp=datetime(2026, 8, 13, tzinfo=UTC),
        collector_version="test",
        schema_version="1",
    )

    with pytest.raises(BackupError, match="no recovery adapter: hacker_news"):
        RawBackupCopier(source).copy(tmp_path / "copy", tmp_path / "manifest.gz")
