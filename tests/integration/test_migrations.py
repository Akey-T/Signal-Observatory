from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect
from tests.conftest import alembic_config


def test_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
    configuration = alembic_config(database_url)

    command.upgrade(configuration, "head")
    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "data_quality_checks",
        "ingestion_errors",
        "ingestion_runs",
        "sources",
        "topic_aliases",
        "topic_categories",
        "topic_registry_audit_log",
        "topic_registry_versions",
        "topic_source_mappings",
        "topics",
    }

    command.downgrade(configuration, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
