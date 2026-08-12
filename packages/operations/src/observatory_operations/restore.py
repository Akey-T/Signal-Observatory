"""Safe empty-target restore and isolated disaster-recovery drill."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import Engine, inspect, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from observatory_db.arxiv_models import (
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.github_models import (
    GithubRawResponse,
    GithubRepositorySnapshot,
    GithubTopicRepositoryMatch,
)
from observatory_db.models import IngestionRun, TopicSourceMapping
from observatory_db.session import create_database_engine
from observatory_operations.backup import BackupCatalog, BackupService, BackupVerifier
from observatory_operations.backup_models import BackupManifest, RestoreReport
from observatory_operations.integrity import RawIntegrityVerifier
from observatory_operations.postgres_backup import (
    PostgresBackupTool,
    PostgresTool,
    PostgresToolError,
)
from signal_observatory_config import Settings
from topic_registry.queries import TopicQueryService


class RestoreError(RuntimeError):
    """Raised when an empty-target restore cannot preserve the recovery unit."""


class RestoreService:
    def __init__(
        self,
        settings: Settings,
        *,
        repository_root: Path,
        postgres_tool: PostgresTool | None = None,
    ) -> None:
        self.settings = settings
        self.repository_root = repository_root.resolve()
        self.postgres_tool = postgres_tool or PostgresBackupTool.discover(self.repository_root)

    def restore(
        self,
        backup_directory: Path,
        *,
        database_url: str,
        raw_dir: Path,
    ) -> RestoreReport:
        started = datetime.now(UTC)
        timer = monotonic()
        manifest = self._preflight(backup_directory, database_url, raw_dir)
        stage = raw_dir.parent / f".{raw_dir.name}.restore-{uuid4().hex[:8]}"
        raw_restored = False
        database_restored = False
        phase = "Raw staging copy"
        try:
            shutil.copytree(backup_directory / "raw", stage, symlinks=False)
            phase = "Raw staging verification"
            self._verify_restored_raw_tree(backup_directory, stage)
            if raw_dir.exists():
                raw_dir.rmdir()
            os.rename(stage, raw_dir)
            raw_restored = True
            phase = "PostgreSQL restore"
            self.postgres_tool.restore(database_url, backup_directory / "postgres.dump")
            database_restored = True
            phase = "post-restore verification"
            report = self._verify_restored(
                manifest,
                database_url=database_url,
                raw_dir=raw_dir,
                started=started,
                duration_ms=int((monotonic() - timer) * 1000),
            )
        except Exception as error:
            if stage.exists():
                shutil.rmtree(stage)
            report = RestoreReport(
                restore_started_at=started,
                restore_completed_at=datetime.now(UTC),
                backup_id=manifest.backup_id,
                database_restore="pass" if database_restored else "fail",
                raw_restore="pass" if raw_restored else "fail",
                counts={"expected": manifest.database.counts, "restored": {}},
                raw_integrity={"state": "not_checked", "failures": 0},
                lineage_samples={"arxiv": [], "github": []},
                migration={
                    "expected": manifest.database.migration_head,
                    "restored": "unknown",
                },
                registry={"valid": False},
                api_smoke={},
                duration_ms=int((monotonic() - timer) * 1000),
                result="fail",
            )
            self._write_report(raw_dir, report)
            safe_message = (
                str(error)
                if isinstance(error, (RestoreError, PostgresToolError))
                else f"{phase} failed ({type(error).__name__})"
            )
            raise RestoreError(safe_message) from error
        self._write_report(raw_dir, report)
        if report.result != "pass":
            raise RestoreError("restored data failed verification")
        return report

    def _preflight(
        self, backup_directory: Path, database_url: str, raw_dir: Path
    ) -> BackupManifest:
        verification = BackupVerifier(self.postgres_tool).verify(
            backup_directory, write_report=False
        )
        if verification.result == "fail":
            raise RestoreError("backup verification failed")
        manifest = BackupCatalog(backup_directory.parent).show(backup_directory.name)
        if manifest is None:
            raise RestoreError("backup manifest is unavailable")
        source_url = make_url(self.settings.database_url)
        target_url = make_url(database_url)
        if not target_url.drivername.startswith("postgresql"):
            raise RestoreError("restore requires an explicit PostgreSQL target URL")
        if source_url.database == target_url.database:
            raise RestoreError(
                "restore target database name must differ from the active Observatory database"
            )
        target_raw = raw_dir.resolve()
        source_raw = self.settings.raw_data_path.resolve()
        if target_raw == source_raw or target_raw.is_relative_to(source_raw):
            raise RestoreError("restore target must not be the active Raw directory")
        backup_root = backup_directory.resolve()
        if target_raw == backup_root or target_raw.is_relative_to(backup_root):
            raise RestoreError("restore Raw target must not be inside the source backup")
        if backup_root.is_relative_to(target_raw):
            raise RestoreError("restore Raw target must not contain the source backup")
        if raw_dir.is_symlink():
            raise RestoreError("restore Raw target must not be a symlink")
        if raw_dir.exists() and any(raw_dir.iterdir()):
            raise RestoreError("restore Raw target must be empty")
        if not raw_dir.parent.exists():
            raise RestoreError("restore Raw target parent must already exist")
        engine = create_database_engine(database_url)
        try:
            with engine.connect() as connection:
                if inspect(connection).get_table_names():
                    raise RestoreError("restore database target must be empty")
        finally:
            engine.dispose()
        return manifest

    @staticmethod
    def _verify_restored_raw_tree(backup_directory: Path, stage: Path) -> None:
        source = backup_directory / "raw"
        source_files = sorted(path for path in source.rglob("*") if path.is_file())
        target_files = sorted(path for path in stage.rglob("*") if path.is_file())
        source_keys = [path.relative_to(source).as_posix() for path in source_files]
        target_keys = [path.relative_to(stage).as_posix() for path in target_files]
        if source_keys != target_keys:
            raise RestoreError("restored Raw file tree differs from backup")
        for source_path, target_path in zip(source_files, target_files, strict=True):
            if source_path.read_bytes() != target_path.read_bytes():
                raise RestoreError(
                    f"restored Raw bytes differ: {source_path.relative_to(source).as_posix()}"
                )

    def _verify_restored(
        self,
        manifest: BackupManifest,
        *,
        database_url: str,
        raw_dir: Path,
        started: datetime,
        duration_ms: int,
    ) -> RestoreReport:
        engine = create_database_engine(database_url)
        try:
            with Session(engine) as session:
                counts = BackupService.database_counts(session)
                migration = str(
                    session.connection()
                    .exec_driver_sql("SELECT version_num FROM alembic_version")
                    .scalar_one()
                )
                registry = TopicQueryService(session).registry_status()
                raw = RawIntegrityVerifier(session, raw_dir).verify(full=True)
                lineage = self._lineage_samples(session, raw_dir)
                api_smoke = asyncio.run(self._api_smoke(engine, database_url, raw_dir))
        finally:
            engine.dispose()
        registry_valid = bool(
            registry
            and registry["version"] == manifest.registry.version
            and registry["checksum"] == manifest.registry.checksum
            and int(str(registry["topic_count"])) == manifest.registry.topic_count
        )
        arxiv_lineage_valid = bool(lineage["arxiv"]) or (manifest.sources["arxiv"].match_count == 0)
        github_lineage_valid = bool(lineage["github"]) or (
            manifest.sources["github"].match_count == 0
        )
        raw_valid = raw["state"] == "pass" or (
            manifest.raw.file_count == 0 and raw["state"] == "not_initialized"
        )
        valid = (
            counts == manifest.database.counts
            and migration == manifest.database.migration_head
            and registry_valid
            and raw_valid
            and arxiv_lineage_valid
            and github_lineage_valid
            and all(status == 200 for status in api_smoke.values())
        )
        return RestoreReport(
            restore_started_at=started,
            restore_completed_at=datetime.now(UTC),
            backup_id=manifest.backup_id,
            database_restore="pass",
            raw_restore="pass",
            counts={"expected": manifest.database.counts, "restored": counts},
            raw_integrity={
                "state": str(raw["state"]),
                "checked": int(raw["records_checked"]),
                "failures": int(raw["failures"]),
            },
            lineage_samples=lineage,
            migration={"expected": manifest.database.migration_head, "restored": migration},
            registry={
                "valid": registry_valid,
                "version": registry["version"] if registry else None,
                "checksum": registry["checksum"] if registry else None,
                "topic_count": int(str(registry["topic_count"])) if registry else 0,
            },
            api_smoke=api_smoke,
            duration_ms=duration_ms,
            result="pass" if valid else "fail",
        )

    @staticmethod
    def _lineage_samples(session: Session, raw_dir: Path) -> dict[str, list[dict[str, str]]]:
        verifier = RawIntegrityVerifier(session, raw_dir)
        arxiv: list[dict[str, str]] = []
        arxiv_rows = session.execute(
            select(
                ArxivTopicMatch,
                ArxivPaperObservation,
                ArxivRawResponse,
                TopicSourceMapping,
                IngestionRun,
            )
            .join(
                ArxivPaperObservation,
                ArxivPaperObservation.paper_id == ArxivTopicMatch.paper_id,
            )
            .join(ArxivRawResponse, ArxivRawResponse.id == ArxivPaperObservation.raw_response_id)
            .join(
                TopicSourceMapping,
                TopicSourceMapping.id == ArxivTopicMatch.source_mapping_id,
            )
            .join(IngestionRun, IngestionRun.run_id == ArxivPaperObservation.ingestion_run_id)
            .order_by(ArxivTopicMatch.id)
            .limit(10)
        ).all()
        for match, observation, raw, mapping, run in arxiv_rows:
            path = verifier.resolve_path(raw.raw_path, "arxiv")
            RawIntegrityVerifier.verify_raw_directory(path, expected_checksum=raw.payload_checksum)
            arxiv.append(
                {
                    "match_id": str(match.id),
                    "observation_id": str(observation.id),
                    "mapping_id": str(mapping.id),
                    "run_id": str(run.run_id),
                    "raw_id": str(raw.id),
                    "raw_key": raw.raw_path,
                }
            )
        github: list[dict[str, str]] = []
        github_rows = session.execute(
            select(
                GithubRepositorySnapshot,
                GithubTopicRepositoryMatch,
                GithubRawResponse,
                TopicSourceMapping,
                IngestionRun,
            )
            .join(
                GithubTopicRepositoryMatch,
                GithubTopicRepositoryMatch.repository_id == GithubRepositorySnapshot.repository_id,
            )
            .join(
                GithubRawResponse,
                GithubRawResponse.id == GithubRepositorySnapshot.raw_response_id,
            )
            .join(
                TopicSourceMapping,
                TopicSourceMapping.id == GithubTopicRepositoryMatch.source_mapping_id,
            )
            .join(IngestionRun, IngestionRun.run_id == GithubRepositorySnapshot.ingestion_run_id)
            .order_by(GithubRepositorySnapshot.id)
            .limit(10)
        ).all()
        for snapshot, match, raw, mapping, run in github_rows:
            path = verifier.resolve_path(raw.raw_path, "github")
            RawIntegrityVerifier.verify_raw_directory(path, expected_checksum=raw.payload_checksum)
            github.append(
                {
                    "snapshot_id": str(snapshot.id),
                    "match_id": str(match.id),
                    "mapping_id": str(mapping.id),
                    "run_id": str(run.run_id),
                    "raw_id": str(raw.id),
                    "raw_key": raw.raw_path,
                }
            )
        return {"arxiv": arxiv, "github": github}

    @staticmethod
    async def _api_smoke(engine: Engine, database_url: str, raw_dir: Path) -> dict[str, int]:
        from signal_observatory_api.main import create_app

        settings = Settings(
            _env_file=None,
            database_url=database_url,
            raw_data_path=raw_dir,
            github_token=None,
        )
        application = create_app(settings)
        application.state.engine = engine
        paths = [
            "/api/topic-registry/status",
            "/api/operations",
            "/api/topics/model-context-protocol/research",
            "/api/topics/model-context-protocol/development",
            "/api/topics/model-context-protocol/coverage",
        ]
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://restore") as client:
            return {path: (await client.get(path)).status_code for path in paths}

    @staticmethod
    def _write_report(raw_dir: Path, report: RestoreReport) -> None:
        path = raw_dir.parent / f"{raw_dir.name}.restore-report.json"
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


class DisasterRecoveryDrill:
    def __init__(
        self,
        settings: Settings,
        *,
        repository_root: Path,
        postgres_tool: PostgresTool | None = None,
    ) -> None:
        self.settings = settings
        self.repository_root = repository_root.resolve()
        self.postgres_tool = postgres_tool or PostgresBackupTool.discover(self.repository_root)

    def run(self, backup_directory: Path, *, keep_on_failure: bool = False) -> dict[str, Any]:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        database_name = f"signal_observatory_restore_drill_{timestamp}_{suffix}"
        if (
            re.fullmatch(
                r"signal_observatory_restore_drill_[0-9]{14}_[0-9a-f]{6}",
                database_name,
            )
            is None
        ):
            raise RestoreError("invalid drill database name")
        target_url = make_url(self.settings.database_url).set(database=database_name)
        database_url = target_url.render_as_string(hide_password=False)
        drill_root = Path(tempfile.gettempdir()).resolve() / "so-drill" / f"{timestamp}-{suffix}"
        raw_dir = drill_root / "raw"
        drill_root.mkdir(parents=True, exist_ok=False)
        database_created = False
        succeeded = False
        result_payload: dict[str, Any] | None = None
        try:
            self._create_database(target_url, database_name)
            database_created = True
            report = RestoreService(
                self.settings,
                repository_root=self.repository_root,
                postgres_tool=self.postgres_tool,
            ).restore(backup_directory, database_url=database_url, raw_dir=raw_dir)
            succeeded = report.result == "pass"
            report_root = self.settings.backup_path.resolve() / "drill-reports"
            report_root.mkdir(parents=True, exist_ok=True)
            report_path = report_root / f"{database_name}.json"
            report_path.write_text(
                report.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            result_payload = {
                "drill_id": database_name,
                "target_database": database_name,
                "target_raw": str(raw_dir),
                "result": report.result,
                "report": report.model_dump(mode="json"),
                "cleanup": "retained" if keep_on_failure and not succeeded else "completed",
            }
        except Exception:
            failed_report = raw_dir.parent / f"{raw_dir.name}.restore-report.json"
            if failed_report.is_file():
                report_root = self.settings.backup_path.resolve() / "drill-reports"
                report_root.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(failed_report, report_root / f"{database_name}.json")
            raise
        finally:
            if succeeded or not keep_on_failure:
                if database_created:
                    self._drop_database(target_url, database_name)
                if drill_root.exists():
                    shutil.rmtree(drill_root)
        if result_payload is None:
            raise RestoreError("drill did not produce a report")
        return result_payload

    def _create_database(self, target_url: URL, database_name: str) -> None:
        admin_url = target_url.set(database="postgres")
        engine = create_database_engine(admin_url.render_as_string(hide_password=False))
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                existing = connection.exec_driver_sql(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
                ).scalar()
                if existing:
                    raise RestoreError("drill database already exists")
                connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        finally:
            engine.dispose()

    def _drop_database(self, target_url: URL, database_name: str) -> None:
        if not database_name.startswith("signal_observatory_restore_drill_"):
            raise RestoreError("refusing to drop a non-drill database")
        admin_url = target_url.set(database="postgres")
        engine = create_database_engine(admin_url.render_as_string(hide_password=False))
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.exec_driver_sql(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database_name,),
                )
                connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
        finally:
            engine.dispose()
