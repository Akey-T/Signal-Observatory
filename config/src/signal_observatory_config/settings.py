"""Validated settings shared by the API and worker."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
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
    arxiv_large_query_threshold: int = Field(default=1000, ge=10, le=30000)
    arxiv_max_runtime_minutes: int = Field(default=30, ge=1, le=1440)
    arxiv_retry_attempts: int = Field(default=3, ge=1, le=5)
    arxiv_user_agent: str = Field(
        default="Signal-Observatory/0.1.0 (+https://github.com/Akey-T/Signal-Observatory)",
        min_length=10,
        max_length=500,
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        supported = ("postgresql+psycopg://", "sqlite:///", "sqlite+pysqlite:///")
        if not value.startswith(supported):
            raise ValueError("database URL must use psycopg PostgreSQL or SQLite")
        return value

    def public_summary(self) -> dict[str, str]:
        """Return startup-safe values without credentials or other secrets."""

        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "database_driver": self.database_url.split(":", maxsplit=1)[0],
            "raw_data_path": str(self.raw_data_path),
            "arxiv_api_host": self.arxiv_api_base_url.split("/", maxsplit=3)[2],
            "arxiv_min_request_interval_seconds": str(self.arxiv_min_request_interval_seconds),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
