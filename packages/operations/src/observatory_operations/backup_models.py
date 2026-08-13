"""Strict, versioned schemas for backup and restore evidence."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BACKUP_SCHEMA_VERSION: Literal["1"] = "1"
BACKUP_TOOL_VERSION = "backup-v1"
BACKUP_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
SOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatabaseManifest(StrictModel):
    server_version: str
    migration_head: str
    dump_filename: str = "postgres.dump"
    table_count: int = Field(ge=0)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    counts: dict[str, int]


class RegistryManifest(StrictModel):
    version: int | None
    checksum: str | None
    topic_count: int = Field(ge=0)
    config_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_bytes: int = Field(ge=0)


class RawManifestSummary(StrictModel):
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    manifest_filename: str = "raw-manifest.jsonl.gz"
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceManifest(StrictModel):
    entity_count: int = Field(ge=0)
    match_count: int = Field(ge=0)
    raw_response_count: int = Field(ge=0)
    snapshot_count: int | None = Field(default=None, ge=0)
    observation_dates: int | None = Field(default=None, ge=0)
    latest_run_at: datetime | None = None


class CoverageManifest(StrictModel):
    projection_count: int = Field(ge=0)


class BackupManifest(StrictModel):
    schema_version: Literal["1"] = BACKUP_SCHEMA_VERSION
    backup_id: str
    label: str | None = Field(default=None, max_length=200)
    backup_started_at: datetime
    backup_completed_at: datetime
    application_version: str
    git_commit_if_available: str | None
    database: DatabaseManifest
    registry: RegistryManifest
    raw: RawManifestSummary
    sources: dict[str, SourceManifest]
    coverage: CoverageManifest
    backup_tool_version: str = BACKUP_TOOL_VERSION
    verification_state: Literal["unverified", "pass", "warning", "fail"]
    total_backup_bytes: int = Field(ge=0)

    @field_validator("backup_id")
    @classmethod
    def validate_backup_id(cls, value: str) -> str:
        if BACKUP_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("backup_id must be UTC timestamp plus six lowercase hex characters")
        return value

    @model_validator(mode="after")
    def validate_sources(self) -> BackupManifest:
        if not self.sources:
            raise ValueError("sources must contain at least one registered recovery source")
        invalid = sorted(
            name for name in self.sources if SOURCE_NAME_PATTERN.fullmatch(name) is None
        )
        if invalid:
            raise ValueError(f"invalid recovery source name(s): {', '.join(invalid)}")
        return self


class RawManifestEntry(StrictModel):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sidecar: bool
    sidecar_size_bytes: int = Field(ge=0)
    sidecar_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_logical_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("Raw manifest path must be a safe logical key")
        parts = normalized.split("/")
        if len(parts) < 2 or SOURCE_NAME_PATTERN.fullmatch(parts[0]) is None:
            raise ValueError("Raw manifest path must begin with a valid source name")
        return normalized


class VerificationReport(StrictModel):
    verified_at: datetime
    tool_version: str = BACKUP_TOOL_VERSION
    manifest_valid: bool
    database_dump_valid: bool
    database_dump_checksum_valid: bool
    registry_valid: bool
    raw_files_expected: int = Field(ge=0)
    raw_files_checked: int = Field(ge=0)
    raw_files_missing: int = Field(ge=0)
    raw_checksum_failures: int = Field(ge=0)
    sidecar_failures: int = Field(ge=0)
    extra_raw_files: int = Field(ge=0)
    result: Literal["pass", "warning", "fail"]
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RestoreReport(StrictModel):
    restore_started_at: datetime
    restore_completed_at: datetime
    backup_id: str
    database_restore: Literal["pass", "fail"]
    raw_restore: Literal["pass", "fail"]
    counts: dict[str, dict[str, int]]
    raw_integrity: dict[str, int | str]
    lineage_samples: dict[str, list[dict[str, str]]]
    migration: dict[str, str]
    registry: dict[str, str | int | bool | None]
    api_smoke: dict[str, int]
    duration_ms: int = Field(ge=0)
    result: Literal["pass", "fail"]


class DataProtectionStatus(StrictModel):
    latest_backup: dict[str, object] | None
    latest_verified_backup: dict[str, object] | None
    latest_verified_backup_age_seconds: int | None
    latest_restore_drill: dict[str, object] | None
