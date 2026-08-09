from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from observatory_db.models import IngestionStatus, Source, TopicAlias
from observatory_db.repositories import IngestionRunRepository, TopicRepository
from observatory_db.session import create_database_engine, database_is_ready
from topic_registry.loader import TopicRegistryLoader
from topic_registry.sync import TopicRegistrySyncService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "topic_registry"


def test_database_connection(migrated_engine: Engine) -> None:
    assert database_is_ready(migrated_engine)


def test_topic_repository_only_resolves_registry_managed_topics(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(TopicRegistryLoader(FIXTURES / "valid").load())
        repository = TopicRepository(session)
        topic = repository.get_by_label("  MODEL   Context Protocol ")
        assert topic is not None
        assert topic.slug == "model-context-protocol"
        assert repository.get_by_label("unreviewed observed keyword") is None


def test_topic_alias_unique_constraint(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(TopicRegistryLoader(FIXTURES / "valid").load())
        topic = TopicRepository(session).get_by_slug("model-context-protocol")
        assert topic is not None
        first = TopicAlias(topic=topic, alias="Protocol", normalized_alias="protocol")
        session.add(first)
        session.commit()
        second = TopicAlias(topic=topic, alias="protocol", normalized_alias="protocol")
        session.add(second)
        with pytest.raises(IntegrityError):
            session.commit()


def test_ingestion_run_lifecycle_and_utc(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        source = Source(name="example-api", kind="api", metadata_={})
        session.add(source)
        session.flush()
        repository = IngestionRunRepository(session)
        run = repository.start(
            source=source,
            collector_version="1.0.0",
            checkpoint_before={"cursor": "a"},
        )
        repository.complete(
            run,
            records_requested=10,
            records_received=10,
            records_inserted=8,
            records_updated=1,
            records_skipped=1,
            error_count=0,
            checkpoint_after={"cursor": "b"},
        )
        session.commit()

        assert run.status is IngestionStatus.SUCCEEDED
        assert run.finished_at is not None
        assert run.finished_at.tzinfo is UTC
        assert run.checkpoint_after == {"cursor": "b"}
        with pytest.raises(ValueError, match="already terminal"):
            repository.fail(run, error_count=1)


@pytest.mark.postgres
def test_postgresql_connection_when_configured() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_database_engine(database_url)
    try:
        assert database_is_ready(engine)
    finally:
        engine.dispose()
