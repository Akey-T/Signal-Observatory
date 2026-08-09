from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from observatory_db.session import create_database_engine

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    configuration = Config(REPOSITORY_ROOT / "alembic.ini")
    configuration.set_main_option("script_location", str(REPOSITORY_ROOT / "db" / "migrations"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    configuration.attributes["database_url_override"] = database_url
    return configuration


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'silver.db').as_posix()}"
    command.upgrade(alembic_config(database_url), "head")
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
