"""Full PostgreSQL + immutable Raw + Registry backup workflow."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from collector_core import DataIntegrityError, LocalRawStore
from observatory_db.base import Base
from observatory_db.models import IngestionRun, Source
from observatory_db.session import create_database_engine
from observatory_operations.backup_models import (
    BackupManifest,
    CoverageManifest,
    DatabaseManifest,
    DataProtectionStatus,
    RawManifestEntry,
    RawManifestSummary,
    RegistryManifest,
    SourceManifest,
    VerificationReport,
)
from observatory_operations.integrity import RawIntegrityVerifier
from observatory_operations.postgres_backup import (
    PostgresBackupTool,
    PostgresTool,
    PostgresToolError,
    assert_version_compatible,
)
from observatory_operations.source_recovery import (
    SOURCE_RECOVERY_ADAPTERS,
    recovery_source_names,
)
from signal_observatory_config import Settings
from topic_registry.loader import TopicRegistryLoader, TopicRegistryValidationError
from topic_registry.queries import TopicQueryService


class BackupError(RuntimeError):
    """Raised when a backup cannot be safely created, verified, or published."""


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def generate_backup_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"


def tree_checksum(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        total += len(content)
    return digest.hexdigest(), total


class RawBackupCopier:
    def __init__(self, source_root: Path, *, sources: Iterable[str] | None = None) -> None:
        self.source_root = source_root.resolve()
        self.store = LocalRawStore(self.source_root)
        self.sources = tuple(sorted(set(sources or recovery_source_names())))

    def copy(self, target_root: Path, manifest_path: Path) -> RawManifestSummary:
        target_root.mkdir(parents=True, exist_ok=False)
        entries = 0
        total_bytes = 0
        with manifest_path.open("wb") as raw_manifest:
            with gzip.GzipFile(fileobj=raw_manifest, mode="wb", mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream:
                    for entry in self._entries(target_root):
                        stream.write(entry.model_dump_json() + "\n")
                        entries += 1
                        total_bytes += entry.size_bytes + entry.sidecar_size_bytes
        return RawManifestSummary(
            file_count=entries,
            total_bytes=total_bytes,
            manifest_sha256=sha256_file(manifest_path),
        )

    def _entries(self, target_root: Path) -> Iterable[RawManifestEntry]:
        unregistered = sorted(self._persisted_source_directories() - set(self.sources))
        if unregistered:
            raise BackupError(
                "Raw source directory has no recovery adapter: " + ", ".join(unregistered)
            )
        for source in self.sources:
            for record in self.store.iter_records(source):
                logical = self.store.logical_key(record.directory, source=source)
                self._ensure_no_symlinks(record.directory, source)
                source_directory = record.directory.resolve()
                try:
                    source_directory.relative_to(self.source_root)
                except ValueError as error:
                    raise BackupError(
                        f"Raw record resolves outside the configured root: {record.directory}"
                    ) from error
                RawIntegrityVerifier.verify_raw_directory(
                    source_directory, expected_checksum=record.sha256
                )
                destination = (target_root / logical).resolve()
                try:
                    destination.relative_to(target_root.resolve())
                except ValueError as error:
                    raise BackupError(f"Raw logical key escapes backup root: {logical}") from error
                destination.mkdir(parents=True, exist_ok=False)
                shutil.copyfile(record.payload_path, destination / "payload.gz")
                shutil.copyfile(record.metadata_path, destination / "metadata.json")
                payload_size = record.payload_path.stat().st_size
                sidecar_size = record.metadata_path.stat().st_size
                yield RawManifestEntry(
                    path=logical,
                    size_bytes=payload_size,
                    sha256=sha256_file(record.payload_path),
                    sidecar=True,
                    sidecar_size_bytes=sidecar_size,
                    sidecar_sha256=sha256_file(record.metadata_path),
                    source_checksum=record.sha256,
                )

    def _persisted_source_directories(self) -> set[str]:
        if not self.source_root.is_dir():
            return set()
        return {
            path.name
            for path in self.source_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        }

    def _ensure_no_symlinks(self, directory: Path, source: str) -> None:
        source_root = self.source_root / source
        candidates = [directory / "payload.gz", directory / "metadata.json"]
        current = directory
        while True:
            candidates.append(current)
            if current == source_root:
                break
            if current == current.parent:
                raise BackupError(f"Raw record is outside source root: {directory}")
            current = current.parent
        if any(path.is_symlink() for path in candidates):
            raise BackupError(f"Raw symlink is not allowed: {directory}")


class BackupVerifier:
    def __init__(self, postgres_tool: PostgresTool) -> None:
        self.postgres_tool = postgres_tool

    def verify(
        self,
        backup_directory: Path,
        *,
        write_report: bool = True,
    ) -> VerificationReport:
        now = datetime.now(UTC)
        failures: list[str] = []
        warnings: list[str] = []
        manifest: BackupManifest | None = None
        try:
            manifest = BackupManifest.model_validate_json(
                (backup_directory / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as error:
            failures.append(f"manifest invalid: {error}")

        dump_valid = False
        dump_checksum_valid = False
        registry_valid = False
        expected = checked = missing = checksum_failures = sidecar_failures = extras = 0
        if manifest is not None:
            unsupported = sorted(set(manifest.sources) - set(recovery_source_names()))
            if unsupported:
                failures.append(
                    "backup contains source(s) without a recovery adapter: "
                    + ", ".join(unsupported)
                )
            dump_path = backup_directory / manifest.database.dump_filename
            if dump_path.is_file() and dump_path.stat().st_size > 0:
                dump_checksum_valid = sha256_file(dump_path) == manifest.database.sha256
                if not dump_checksum_valid:
                    failures.append("PostgreSQL dump checksum mismatch")
                try:
                    self.postgres_tool.validate_dump(dump_path)
                    dump_valid = True
                except PostgresToolError as error:
                    failures.append(str(error))
            else:
                failures.append("PostgreSQL dump is missing or empty")

            registry_valid = self._verify_registry(backup_directory, manifest, failures)
            (
                expected,
                checked,
                missing,
                checksum_failures,
                sidecar_failures,
                extras,
            ) = self._verify_raw(backup_directory, manifest, failures, warnings)

        result = "fail" if failures else "warning" if warnings else "pass"
        report = VerificationReport(
            verified_at=now,
            manifest_valid=manifest is not None,
            database_dump_valid=dump_valid,
            database_dump_checksum_valid=dump_checksum_valid,
            registry_valid=registry_valid,
            raw_files_expected=expected,
            raw_files_checked=checked,
            raw_files_missing=missing,
            raw_checksum_failures=checksum_failures,
            sidecar_failures=sidecar_failures,
            extra_raw_files=extras,
            result=result,
            failures=failures,
            warnings=warnings,
        )
        if write_report and backup_directory.is_dir():
            self._write_json(backup_directory / "verification.json", report.model_dump(mode="json"))
        return report

    @staticmethod
    def _verify_registry(
        backup_directory: Path, manifest: BackupManifest, failures: list[str]
    ) -> bool:
        registry_root = backup_directory / "registry" / "topics"
        try:
            loaded = TopicRegistryLoader(registry_root).load()
            checksum, byte_count = tree_checksum(registry_root)
            valid = (
                checksum == manifest.registry.config_checksum
                and byte_count == manifest.registry.config_bytes
                and loaded.checksum == manifest.registry.checksum
                and len(loaded.topics) == manifest.registry.topic_count
            )
            if not valid:
                failures.append("Registry snapshot checksum or projection checksum differs")
            return valid
        except (OSError, TopicRegistryValidationError) as error:
            failures.append(f"Registry snapshot invalid: {error}")
            return False

    @staticmethod
    def _verify_raw(
        backup_directory: Path,
        manifest: BackupManifest,
        failures: list[str],
        warnings: list[str],
    ) -> tuple[int, int, int, int, int, int]:
        raw_root = backup_directory / "raw"
        manifest_path = backup_directory / manifest.raw.manifest_filename
        if not manifest_path.is_file():
            failures.append("Raw manifest is missing")
            return 0, 0, 0, 0, 0, 0
        if sha256_file(manifest_path) != manifest.raw.manifest_sha256:
            failures.append("Raw manifest checksum mismatch")
        expected_paths: set[str] = set()
        source_entries: defaultdict[str, int] = defaultdict(int)
        checked = missing = checksum_failures = sidecar_failures = 0
        try:
            with gzip.open(manifest_path, "rt", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    entry = RawManifestEntry.model_validate_json(line)
                    if entry.path in expected_paths:
                        failures.append(f"Raw manifest repeats {entry.path}")
                        continue
                    expected_paths.add(entry.path)
                    source = entry.path.split("/", 1)[0]
                    if source not in manifest.sources:
                        failures.append(
                            f"Raw manifest source {source!r} is absent from the backup manifest"
                        )
                        continue
                    source_entries[source] += 1
                    path = (raw_root / entry.path).resolve()
                    try:
                        path.relative_to(raw_root.resolve())
                    except ValueError:
                        failures.append(f"Raw manifest path escapes root at line {line_number}")
                        continue
                    payload = path / "payload.gz"
                    sidecar = path / "metadata.json"
                    if not payload.is_file():
                        missing += 1
                        failures.append(f"Raw payload missing: {entry.path}")
                        continue
                    if not sidecar.is_file():
                        sidecar_failures += 1
                        failures.append(f"Raw sidecar missing: {entry.path}")
                        continue
                    checked += 1
                    if (
                        payload.stat().st_size != entry.size_bytes
                        or sha256_file(payload) != entry.sha256
                    ):
                        checksum_failures += 1
                        failures.append(f"Raw payload byte checksum mismatch: {entry.path}")
                    if (
                        sidecar.stat().st_size != entry.sidecar_size_bytes
                        or sha256_file(sidecar) != entry.sidecar_sha256
                    ):
                        sidecar_failures += 1
                        failures.append(f"Raw sidecar byte checksum mismatch: {entry.path}")
                    try:
                        RawIntegrityVerifier.verify_raw_directory(
                            path, expected_checksum=entry.source_checksum
                        )
                    except (OSError, ValueError, DataIntegrityError) as error:
                        checksum_failures += 1
                        failures.append(f"Raw integrity failed for {entry.path}: {error}")
        except (OSError, ValidationError, ValueError) as error:
            failures.append(f"Raw manifest invalid: {error}")
        actual_paths = {
            metadata.parent.relative_to(raw_root).as_posix()
            for metadata in raw_root.glob("*/*/*/*/*/metadata.json")
        }
        extras = len(actual_paths - expected_paths)
        if extras:
            warnings.append(f"{extras} unreferenced Raw record(s) exist in the backup")
        if len(expected_paths) != manifest.raw.file_count:
            failures.append("Raw manifest entry count differs from backup manifest")
        for source, source_manifest in manifest.sources.items():
            raw_count = source_entries[source]
            database_count = source_manifest.raw_response_count
            if raw_count < database_count:
                failures.append(
                    f"Raw manifest has fewer {source} records than the database snapshot"
                )
            elif raw_count > database_count:
                difference = raw_count - database_count
                extras += difference
                warnings.append(
                    f"{difference} {source} Raw record(s) are newer than or unreferenced by "
                    "the database snapshot"
                )
        return (
            len(expected_paths),
            checked,
            missing,
            checksum_failures,
            sidecar_failures,
            extras,
        )

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)


class BackupService:
    def __init__(
        self,
        settings: Settings,
        *,
        repository_root: Path,
        postgres_tool: PostgresTool | None = None,
        now: datetime | None = None,
    ) -> None:
        self.settings = settings
        self.repository_root = repository_root.resolve()
        self.postgres_tool = postgres_tool or PostgresBackupTool.discover(self.repository_root)
        self.now = (now or datetime.now(UTC)).astimezone(UTC)

    def create(self, *, output: Path | None = None, label: str | None = None) -> dict[str, Any]:
        started = self.now
        backup_id = generate_backup_id(started)
        root = (output or self.settings.backup_path).resolve()
        raw_root = self.settings.raw_data_path.resolve()
        self._validate_backup_root(root, raw_root)
        root.mkdir(parents=True, exist_ok=True)
        self._disk_preflight(root, raw_root)
        stage_parent = root / ".tmp"
        stage_parent.mkdir(exist_ok=True)
        stage = stage_parent / backup_id
        final = root / backup_id
        stage.mkdir(exist_ok=False)
        try:
            client_version = self.postgres_tool.client_version()
            database, sources, coverage, registry = self._database_snapshot(
                stage / "postgres.dump", client_version
            )
            registry_root = stage / "registry" / "topics"
            shutil.copytree(self.repository_root / "config" / "topics", registry_root)
            registry_checksum, registry_bytes = tree_checksum(registry_root)
            registry = registry.model_copy(
                update={
                    "config_checksum": registry_checksum,
                    "config_bytes": registry_bytes,
                }
            )
            raw = RawBackupCopier(raw_root).copy(stage / "raw", stage / "raw-manifest.jsonl.gz")
            completed = datetime.now(UTC)
            total_bytes = database.size_bytes + raw.total_bytes + registry.config_bytes
            manifest = BackupManifest(
                backup_id=backup_id,
                label=label,
                backup_started_at=started,
                backup_completed_at=completed,
                application_version=self._application_version(),
                git_commit_if_available=self._git_commit(),
                database=database,
                registry=registry,
                raw=raw,
                sources=sources,
                coverage=coverage,
                verification_state="unverified",
                total_backup_bytes=total_bytes,
            )
            self._write_manifest(stage, manifest)
            verifier = BackupVerifier(self.postgres_tool)
            report = verifier.verify(stage)
            if report.result == "fail":
                raise BackupError("backup verification failed: " + "; ".join(report.failures[:3]))
            manifest = manifest.model_copy(update={"verification_state": report.result})
            self._write_manifest(stage, manifest)
            report = verifier.verify(stage)
            if report.result == "fail":
                raise BackupError("final backup verification failed")
            if final.exists():
                raise BackupError(f"final backup already exists: {final}")
            os.rename(stage, final)
            return {
                "backup_id": backup_id,
                "backup_path": str(final),
                "manifest": manifest.model_dump(mode="json"),
                "verification": report.model_dump(mode="json"),
            }
        except Exception as error:
            failure = stage / "FAILED.json"
            if stage.is_dir():
                failure.write_text(
                    json.dumps(
                        {
                            "backup_id": backup_id,
                            "state": "failed",
                            "error_type": type(error).__name__,
                            "message": str(error),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            raise

    def _database_snapshot(
        self, dump_path: Path, client_version: str
    ) -> tuple[
        DatabaseManifest,
        dict[str, SourceManifest],
        CoverageManifest,
        RegistryManifest,
    ]:
        engine = create_database_engine(self.settings.database_url)
        try:
            with engine.connect() as connection:
                snapshot: str | None = None
                if connection.dialect.name == "postgresql":
                    transaction = connection.begin()
                    connection.exec_driver_sql(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                    snapshot = str(
                        connection.exec_driver_sql("SELECT pg_export_snapshot()").scalar_one()
                    )
                    server_version_num = int(
                        connection.exec_driver_sql("SHOW server_version_num").scalar_one()
                    )
                    assert_version_compatible(client_version, server_version_num)
                    server_version = str(
                        connection.exec_driver_sql("SHOW server_version").scalar_one()
                    )
                else:
                    transaction = connection.begin()
                    server_version = "test-sqlite"
                session = Session(bind=connection)
                try:
                    counts = self.database_counts(session)
                    sources = self._source_manifests(session, counts)
                    registry = self._registry_manifest(session)
                    coverage = CoverageManifest(projection_count=counts["topic_source_coverage"])
                    migration = str(
                        connection.exec_driver_sql(
                            "SELECT version_num FROM alembic_version"
                        ).scalar_one()
                    )
                    table_count = len(inspect(connection).get_table_names())
                    self.postgres_tool.dump(
                        self.settings.database_url, dump_path, snapshot=snapshot
                    )
                finally:
                    session.close()
                    transaction.commit()
        finally:
            engine.dispose()
        return (
            DatabaseManifest(
                server_version=server_version,
                migration_head=migration,
                table_count=table_count,
                size_bytes=dump_path.stat().st_size,
                sha256=sha256_file(dump_path),
                counts=counts,
            ),
            sources,
            coverage,
            registry,
        )

    @staticmethod
    def database_counts(session: Session) -> dict[str, int]:
        return {
            table.name: int(session.scalar(select(func.count()).select_from(table)) or 0)
            for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name)
        }

    @staticmethod
    def _source_manifests(session: Session, counts: dict[str, int]) -> dict[str, SourceManifest]:
        manifests: dict[str, SourceManifest] = {}
        for name, adapter in SOURCE_RECOVERY_ADAPTERS.items():
            required_tables = {adapter.entity_table, adapter.match_table, adapter.raw_table}
            if adapter.snapshot_table is not None:
                required_tables.add(adapter.snapshot_table)
            missing = sorted(required_tables - counts.keys())
            if missing:
                raise BackupError(
                    f"recovery adapter {name!r} references missing table(s): {', '.join(missing)}"
                )
            observation_dates = None
            if adapter.observation_date_column is not None:
                observation_dates = int(
                    session.scalar(
                        select(func.count(func.distinct(adapter.observation_date_column)))
                    )
                    or 0
                )
            latest_run = session.scalar(
                select(func.max(IngestionRun.started_at))
                .join(Source, Source.id == IngestionRun.source_id)
                .where(Source.name == name)
            )
            manifests[name] = SourceManifest(
                entity_count=counts[adapter.entity_table],
                match_count=counts[adapter.match_table],
                raw_response_count=counts[adapter.raw_table],
                snapshot_count=(
                    counts[adapter.snapshot_table] if adapter.snapshot_table is not None else None
                ),
                observation_dates=observation_dates,
                latest_run_at=latest_run,
            )
        return manifests

    @staticmethod
    def _registry_manifest(session: Session) -> RegistryManifest:
        registry = TopicQueryService(session).registry_status()
        return RegistryManifest(
            version=int(str(registry["version"])) if registry is not None else None,
            checksum=str(registry["checksum"]) if registry is not None else None,
            topic_count=int(str(registry["topic_count"])) if registry is not None else 0,
            config_checksum="0" * 64,
            config_bytes=0,
        )

    def _git_commit(self) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        commit = result.stdout.strip()
        return commit if result.returncode == 0 and len(commit) == 40 else None

    @staticmethod
    def _application_version() -> str:
        try:
            return version("signal-observatory")
        except PackageNotFoundError:
            return "0.1.0"

    @staticmethod
    def _write_manifest(stage: Path, manifest: BackupManifest) -> None:
        (stage / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    @staticmethod
    def _validate_backup_root(root: Path, raw_root: Path) -> None:
        if root == raw_root or root.is_relative_to(raw_root):
            raise BackupError("backup output must not be inside the Raw source tree")
        if raw_root.is_relative_to(root):
            raise BackupError("backup output must not contain the Raw source tree")

    @staticmethod
    def _disk_preflight(root: Path, raw_root: Path) -> None:
        raw_bytes = sum(
            path.stat().st_size
            for path in raw_root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        available = shutil.disk_usage(root).free
        if available < raw_bytes + 16 * 1024 * 1024:
            raise BackupError("insufficient free disk space for Raw copy and database dump")


class BackupCatalog:
    def __init__(self, backup_root: Path) -> None:
        self.backup_root = backup_root

    def list(self) -> list[BackupManifest]:
        manifests: list[BackupManifest] = []
        if not self.backup_root.is_dir():
            return manifests
        for path in self.backup_root.iterdir():
            if not path.is_dir() or path.name.startswith("."):
                continue
            try:
                manifests.append(
                    BackupManifest.model_validate_json(
                        (path / "manifest.json").read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValidationError):
                continue
        return sorted(manifests, key=lambda item: item.backup_completed_at, reverse=True)

    def show(self, backup_id: str) -> BackupManifest | None:
        if not backup_id or "/" in backup_id or "\\" in backup_id:
            return None
        try:
            return BackupManifest.model_validate_json(
                (self.backup_root / backup_id / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError):
            return None

    def status(self, *, now: datetime | None = None) -> DataProtectionStatus:
        manifests = self.list()
        verified = [item for item in manifests if item.verification_state in {"pass", "warning"}]
        drills: list[dict[str, object]] = []
        drill_root = self.backup_root / "drill-reports"
        if drill_root.is_dir():
            for path in drill_root.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        drills.append(payload)
                except (OSError, ValueError):
                    continue
        drills.sort(key=lambda item: str(item.get("restore_completed_at", "")), reverse=True)
        latest_verified = verified[0] if verified else None
        current = (now or datetime.now(UTC)).astimezone(UTC)
        age = (
            max(0, int((current - latest_verified.backup_completed_at).total_seconds()))
            if latest_verified
            else None
        )
        return DataProtectionStatus(
            latest_backup=self._summary(manifests[0]) if manifests else None,
            latest_verified_backup=(self._summary(latest_verified) if latest_verified else None),
            latest_verified_backup_age_seconds=age,
            latest_restore_drill=drills[0] if drills else None,
        )

    @staticmethod
    def _summary(manifest: BackupManifest) -> dict[str, object]:
        return {
            "backup_id": manifest.backup_id,
            "label": manifest.label,
            "completed_at": manifest.backup_completed_at,
            "verification_state": manifest.verification_state,
            "migration_head": manifest.database.migration_head,
            "database_size_bytes": manifest.database.size_bytes,
            "raw_objects": manifest.raw.file_count,
            "raw_size_bytes": manifest.raw.total_bytes,
            "total_backup_bytes": manifest.total_backup_bytes,
            "registry_version": manifest.registry.version,
        }
