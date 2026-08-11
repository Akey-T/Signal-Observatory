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
        "arxiv_authors",
        "arxiv_categories",
        "arxiv_collection_cursors",
        "arxiv_paper_authors",
        "arxiv_paper_categories",
        "arxiv_paper_observations",
        "arxiv_papers",
        "arxiv_raw_responses",
        "arxiv_topic_matches",
        "data_quality_checks",
        "github_discovery_states",
        "github_raw_responses",
        "github_repositories",
        "github_repository_poll_states",
        "github_repository_snapshots",
        "github_topic_repository_matches",
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
