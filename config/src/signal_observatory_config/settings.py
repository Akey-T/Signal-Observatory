"""Validated settings shared by the API and worker."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIGNAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "postgresql+psycopg://signal:signal@localhost:5432/signal_observatory"
    database_connect_attempts: int = Field(default=10, ge=1, le=100)
    database_connect_delay_seconds: float = Field(default=2.0, ge=0, le=60)
    raw_data_path: Path = Path("data/raw")
    worker_ready_file: Path = Path(".signal-worker-ready")

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
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
