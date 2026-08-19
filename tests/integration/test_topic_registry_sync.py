from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from observatory_db.models import (
    DataQualityCheck,
    QualityStatus,
    Topic,
    TopicAlias,
    TopicRegistryAuditLog,
    TopicRegistryVersion,
    TopicSourceMapping,
    TopicStatus,
)
from topic_registry.loader import TopicRegistryLoader
from topic_registry.models import (
    AliasType,
    IssueSeverity,
    LoadedRegistry,
    MatchMode,
    RegistryIssue,
    SourcesDefinition,
)
from topic_registry.models import TopicStatus as DefinitionStatus
from topic_registry.queries import TopicQueryService
from topic_registry.sync import TopicRegistrySyncService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "topic_registry"


def count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_empty_database_sync_then_second_sync_is_noop(migrated_engine: Engine) -> None:
    registry = TopicRegistryLoader(FIXTURES / "valid").load()
    with Session(migrated_engine) as session:
        first = TopicRegistrySyncService(session).sync(registry, applied_by="pytest")
        assert first.changed is True
        assert first.version == 1
        assert count(session, Topic) == 1
        assert count(session, TopicAlias) == 1
        assert count(session, TopicSourceMapping) == 2
        assert count(session, TopicRegistryVersion) == 1
        assert count(session, TopicRegistryAuditLog) >= 4
        assert count(session, DataQualityCheck) == 8

        second = TopicRegistrySyncService(session).sync(registry, applied_by="pytest")
        assert second.changed is False
        assert second.version is None
        assert count(session, TopicRegistryVersion) == 1
        assert count(session, TopicRegistryAuditLog) >= 4


def test_validation_warning_change_is_versioned_without_registry_content_change(
    migrated_engine: Engine,
) -> None:
    registry = TopicRegistryLoader(FIXTURES / "valid").load()
    assert registry.warnings == ()
    with Session(migrated_engine) as session:
        first = TopicRegistrySyncService(session).sync(registry, applied_by="pytest")
        assert first.version == 1

        warning = RegistryIssue(
            code="NEW_VALIDATION_RULE",
            message="A newly deployed validation rule requires operator review.",
            severity=IssueSeverity.WARNING,
            entity="fixture",
        )
        warned = registry.model_copy(update={"issues": (warning,)})
        second = TopicRegistrySyncService(session).sync(warned, applied_by="pytest")

        assert second.changed is True
        assert second.version == 2
        assert second.checksum == first.checksum
        status = TopicQueryService(session).registry_status()
        assert status is not None
        assert status["warnings"] == 1
        latest = session.scalar(
            select(TopicRegistryVersion).order_by(TopicRegistryVersion.version.desc()).limit(1)
        )
        assert latest is not None
        assert latest.metadata_["warnings"][0]["code"] == "NEW_VALIDATION_RULE"

        third = TopicRegistrySyncService(session).sync(warned, applied_by="pytest")
        assert third.changed is False
        assert third.version is None
        assert count(session, TopicRegistryVersion) == 2


def test_update_deprecation_alias_and_mapping_are_versioned(migrated_engine: Engine) -> None:
    registry = TopicRegistryLoader(FIXTURES / "version_change").load()
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(registry, applied_by="pytest")
        old = registry.topics[0]
        changed_alias = old.aliases[0].model_copy(update={"confidence": 0.7})
        new_alias = old.aliases[0].model_copy(
            update={
                "value": "MCP Server",
                "alias_type": AliasType.SEARCH_TERM,
                "match_mode": MatchMode.PHRASE,
            }
        )
        assert old.sources.github is not None
        changed_sources = old.sources.model_copy(
            update={
                "github": old.sources.github.model_copy(
                    update={"search_queries": ("modelcontextprotocol stars:>100",)}
                )
            }
        )
        changed_topic = old.model_copy(
            update={
                "status": DefinitionStatus.PAUSED,
                "monitoring_priority": 60,
                "aliases": (changed_alias, new_alias),
                "sources": changed_sources,
            }
        )
        changed = registry.model_copy(update={"topics": (changed_topic,), "checksum": "b" * 64})
        report = TopicRegistrySyncService(session).sync(changed, applied_by="pytest")
        assert report.version == 2
        topic = session.scalar(select(Topic).where(Topic.slug == old.slug))
        assert topic is not None
        assert topic.status is TopicStatus.PAUSED
        assert topic.deprecated_at is None
        assert topic.monitoring_priority == 60
        aliases = list(session.scalars(select(TopicAlias).order_by(TopicAlias.alias)))
        mapping = session.scalar(select(TopicSourceMapping))
        assert len(aliases) == 2
        assert aliases[0].alias == "MCP"
        assert aliases[0].confidence == 0.7
        assert mapping is not None
        assert mapping.query == "modelcontextprotocol stars:>100"
        assert count(session, TopicRegistryVersion) == 2

        deprecated_topic = changed_topic.model_copy(update={"status": DefinitionStatus.DEPRECATED})
        deprecated = changed.model_copy(
            update={"topics": (deprecated_topic,), "checksum": "d" * 64}
        )
        TopicRegistrySyncService(session).sync(deprecated, applied_by="pytest")
        deprecated_record = session.scalar(select(Topic).where(Topic.slug == old.slug))
        assert deprecated_record is not None
        assert deprecated_record.status is TopicStatus.DEPRECATED
        assert deprecated_record.deprecated_at is not None
        assert count(session, TopicRegistryVersion) == 3


def test_dry_run_and_exception_roll_back_all_writes(migrated_engine: Engine) -> None:
    registry = TopicRegistryLoader(FIXTURES / "valid").load()
    with Session(migrated_engine) as session:
        dry_run = TopicRegistrySyncService(session).sync(registry, dry_run=True)
        assert dry_run.changed is True
        assert count(session, Topic) == 0

        def fail_before_commit() -> None:
            raise RuntimeError("forced rollback")

        with pytest.raises(RuntimeError, match="forced rollback"):
            TopicRegistrySyncService(session, before_commit=fail_before_commit).sync(registry)
        assert count(session, Topic) == 0
        assert count(session, TopicRegistryVersion) == 0


def test_missing_yaml_entities_are_retained_and_reported(migrated_engine: Engine) -> None:
    registry = TopicRegistryLoader(FIXTURES / "valid").load()
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(registry)
        reduced_topic = registry.topics[0].model_copy(
            update={"aliases": (), "sources": SourcesDefinition()}
        )
        reduced: LoadedRegistry = registry.model_copy(
            update={"topics": (reduced_topic,), "checksum": "c" * 64}
        )
        registry_diff = TopicRegistrySyncService(session).diff(reduced)
        codes = {warning.code for warning in registry_diff.warnings}
        assert "ORPHANED_DATABASE_ALIAS" in codes
        assert "ORPHANED_DATABASE_MAPPING" in codes
        TopicRegistrySyncService(session).sync(reduced)
        assert count(session, TopicAlias) == 1
        assert count(session, TopicSourceMapping) == 2


def test_topic_removed_from_yaml_is_orphaned_and_retained(migrated_engine: Engine) -> None:
    registry = TopicRegistryLoader(FIXTURES / "valid").load()
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(registry)
        empty = registry.model_copy(update={"topics": (), "checksum": "e" * 64})
        registry_diff = TopicRegistrySyncService(session).diff(empty)
        assert "ORPHANED_DATABASE_TOPIC" in {warning.code for warning in registry_diff.warnings}
        TopicRegistrySyncService(session).sync(empty)
        assert count(session, Topic) == 1


def test_allowlisted_collision_creates_review_audit_and_quality_warning(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    source = (FIXTURES / "alias_collision" / "registry.yaml").read_text(encoding="utf-8")
    source = source.replace(
        "allowed_alias_collisions: []",
        "allowed_alias_collisions:\n"
        "  - alias: MCP\n"
        "    topics: [model-context-protocol, microsoft-certified-professional]\n"
        "    reason: Reviewed acronym shared by two established concepts.\n",
    )
    (tmp_path / "registry.yaml").write_text(source, encoding="utf-8")
    registry = TopicRegistryLoader(tmp_path).load()
    with Session(migrated_engine) as session:
        TopicRegistrySyncService(session).sync(registry)
        audit = session.scalar(
            select(TopicRegistryAuditLog).where(TopicRegistryAuditLog.action == "review")
        )
        quality = session.scalar(
            select(DataQualityCheck).where(DataQualityCheck.name == "duplicate_aliases")
        )
        assert audit is not None
        assert audit.entity_id == "mcp"
        assert quality is not None
        assert quality.status is QualityStatus.WARNING
