"""Validated settings shared by the API and worker."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIGNAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "postgresql+psycopg://signal:signal@localhost:5432/signal_observatory"
    database_connect_attempts: int = Field(default=10, ge=1, le=100)
    database_connect_delay_seconds: float = Field(default=2.0, ge=0, le=60)
    raw_data_path: Path = Path("data/raw")
    backup_path: Path = Path("data/backups")
    worker_ready_file: Path = Path(".signal-worker-ready")
    arxiv_api_base_url: str = Field(
        default="https://export.arxiv.org/api/query",
        validation_alias=AliasChoices("ARXIV_API_BASE_URL", "SIGNAL_ARXIV_API_BASE_URL"),
    )
    arxiv_min_request_interval_seconds: float = Field(
        default=3.0,
        ge=3.0,
        le=300,
        validation_alias=AliasChoices(
            "ARXIV_MIN_REQUEST_INTERVAL_SECONDS",
            "SIGNAL_ARXIV_MIN_REQUEST_INTERVAL_SECONDS",
        ),
    )
    arxiv_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
        validation_alias=AliasChoices(
            "ARXIV_REQUEST_TIMEOUT_SECONDS", "SIGNAL_ARXIV_REQUEST_TIMEOUT_SECONDS"
        ),
    )
    arxiv_page_size: int = Field(
        default=100,
        ge=1,
        le=2000,
        validation_alias=AliasChoices("ARXIV_PAGE_SIZE", "SIGNAL_ARXIV_PAGE_SIZE"),
    )
    arxiv_max_requests_per_run: int = Field(
        default=250,
        ge=1,
        le=10000,
        validation_alias=AliasChoices(
            "ARXIV_MAX_REQUESTS_PER_RUN", "SIGNAL_ARXIV_MAX_REQUESTS_PER_RUN"
        ),
    )
    arxiv_max_results_per_topic: int = Field(
        default=1000,
        ge=1,
        le=30000,
        validation_alias=AliasChoices(
            "ARXIV_MAX_RESULTS_PER_TOPIC", "SIGNAL_ARXIV_MAX_RESULTS_PER_TOPIC"
        ),
    )
    arxiv_incremental_overlap_hours: int = Field(
        default=48,
        ge=1,
        le=168,
        validation_alias=AliasChoices(
            "ARXIV_INCREMENTAL_OVERLAP_HOURS", "SIGNAL_ARXIV_INCREMENTAL_OVERLAP_HOURS"
        ),
    )
    arxiv_schedule: str = Field(
        default="0 2 * * *",
        validation_alias=AliasChoices("ARXIV_SCHEDULE", "SIGNAL_ARXIV_SCHEDULE"),
    )
    arxiv_backfill_window_days: int = Field(default=90, ge=1, le=366)
    arxiv_large_query_threshold: int = Field(
        default=1000,
        ge=10,
        le=30000,
        validation_alias=AliasChoices(
            "ARXIV_LARGE_QUERY_THRESHOLD",
            "SIGNAL_ARXIV_LARGE_QUERY_THRESHOLD",
        ),
    )
    arxiv_min_query_partition_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        validation_alias=AliasChoices(
            "ARXIV_MIN_QUERY_PARTITION_MINUTES",
            "SIGNAL_ARXIV_MIN_QUERY_PARTITION_MINUTES",
        ),
    )
    arxiv_max_runtime_minutes: int = Field(default=30, ge=1, le=1440)
    arxiv_retry_attempts: int = Field(default=3, ge=1, le=5)
    arxiv_user_agent: str = Field(
        default="Signal-Observatory/0.1.0 (+https://github.com/Akey-T/Signal-Observatory)",
        min_length=10,
        max_length=500,
    )
    arxiv_freshness_fresh_hours: int = Field(default=36, ge=1, le=720)
    arxiv_freshness_very_stale_hours: int = Field(default=72, ge=2, le=1440)
    github_token: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("GITHUB_TOKEN", "SIGNAL_GITHUB_TOKEN"),
    )
    github_api_base_url: str = Field(
        default="https://api.github.com",
        validation_alias=AliasChoices("GITHUB_API_BASE_URL", "SIGNAL_GITHUB_API_BASE_URL"),
    )
    github_api_version: str = Field(
        default="2022-11-28",
        validation_alias=AliasChoices("GITHUB_API_VERSION", "SIGNAL_GITHUB_API_VERSION"),
    )
    github_require_auth: bool = Field(
        default=True,
        validation_alias=AliasChoices("GITHUB_REQUIRE_AUTH", "SIGNAL_GITHUB_REQUIRE_AUTH"),
    )
    github_allow_anonymous_smoke: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "GITHUB_ALLOW_ANONYMOUS_SMOKE", "SIGNAL_GITHUB_ALLOW_ANONYMOUS_SMOKE"
        ),
    )
    github_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
        validation_alias=AliasChoices(
            "GITHUB_REQUEST_TIMEOUT_SECONDS", "SIGNAL_GITHUB_REQUEST_TIMEOUT_SECONDS"
        ),
    )
    github_request_concurrency: int = Field(
        default=1,
        ge=1,
        le=4,
        validation_alias=AliasChoices(
            "GITHUB_REQUEST_CONCURRENCY", "SIGNAL_GITHUB_REQUEST_CONCURRENCY"
        ),
    )
    github_discovery_page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        validation_alias=AliasChoices(
            "GITHUB_DISCOVERY_PAGE_SIZE", "SIGNAL_GITHUB_DISCOVERY_PAGE_SIZE"
        ),
    )
    github_discovery_max_results_per_mapping: int = Field(
        default=20,
        ge=1,
        le=1000,
        validation_alias=AliasChoices(
            "GITHUB_DISCOVERY_MAX_RESULTS_PER_MAPPING",
            "SIGNAL_GITHUB_DISCOVERY_MAX_RESULTS_PER_MAPPING",
        ),
    )
    github_max_requests_per_run: int = Field(
        default=100,
        ge=1,
        le=5000,
        validation_alias=AliasChoices(
            "GITHUB_MAX_REQUESTS_PER_RUN", "SIGNAL_GITHUB_MAX_REQUESTS_PER_RUN"
        ),
    )
    github_min_core_remaining: int = Field(
        default=100,
        ge=0,
        validation_alias=AliasChoices(
            "GITHUB_MIN_CORE_REMAINING", "SIGNAL_GITHUB_MIN_CORE_REMAINING"
        ),
    )
    github_min_search_remaining: int = Field(
        default=2,
        ge=0,
        validation_alias=AliasChoices(
            "GITHUB_MIN_SEARCH_REMAINING", "SIGNAL_GITHUB_MIN_SEARCH_REMAINING"
        ),
    )
    github_snapshot_schedule: str = Field(
        default="30 2 * * *",
        validation_alias=AliasChoices(
            "GITHUB_SNAPSHOT_SCHEDULE", "SIGNAL_GITHUB_SNAPSHOT_SCHEDULE"
        ),
    )
    github_discovery_schedule: str = Field(
        default="0 3 * * 0",
        validation_alias=AliasChoices(
            "GITHUB_DISCOVERY_SCHEDULE", "SIGNAL_GITHUB_DISCOVERY_SCHEDULE"
        ),
    )
    github_conditional_requests_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "GITHUB_CONDITIONAL_REQUESTS_ENABLED",
            "SIGNAL_GITHUB_CONDITIONAL_REQUESTS_ENABLED",
        ),
    )
    github_retry_attempts: int = Field(default=3, ge=1, le=5)
    github_max_runtime_minutes: int = Field(default=30, ge=1, le=1440)
    github_track_forks: bool = Field(default=False)
    github_snapshot_due_hours: int = Field(default=20, ge=1, le=168)
    github_discovery_due_days: int = Field(default=7, ge=1, le=90)
    github_user_agent: str = Field(
        default="Signal-Observatory/0.1.0 (+https://github.com/Akey-T/Signal-Observatory)",
        min_length=10,
        max_length=500,
    )
    github_freshness_fresh_hours: int = Field(default=36, ge=1, le=720)
    github_freshness_very_stale_hours: int = Field(default=72, ge=2, le=1440)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        supported = ("postgresql+psycopg://", "sqlite:///", "sqlite+pysqlite:///")
        if not value.startswith(supported):
            raise ValueError("database URL must use psycopg PostgreSQL or SQLite")
        return value

    @field_validator("github_token", mode="before")
    @classmethod
    def normalize_blank_github_token(cls, value: object) -> object:
        """Treat an unset Compose interpolation as missing authentication."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_freshness_thresholds(self) -> Settings:
        if self.arxiv_freshness_very_stale_hours <= self.arxiv_freshness_fresh_hours:
            raise ValueError("arXiv very-stale threshold must exceed the fresh threshold")
        if self.github_freshness_very_stale_hours <= self.github_freshness_fresh_hours:
            raise ValueError("GitHub very-stale threshold must exceed the fresh threshold")
        return self

    def public_summary(self) -> dict[str, str]:
        """Return startup-safe values without credentials or other secrets."""

        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "database_driver": self.database_url.split(":", maxsplit=1)[0],
            "raw_data_path": str(self.raw_data_path),
            "arxiv_api_host": self.arxiv_api_base_url.split("/", maxsplit=3)[2],
            "arxiv_min_request_interval_seconds": str(self.arxiv_min_request_interval_seconds),
            "github_api_host": self.github_api_base_url.split("/", maxsplit=3)[2],
            "github_auth_configured": str(self.github_token is not None).lower(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
