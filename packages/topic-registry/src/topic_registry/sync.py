"""Transactional, idempotent Registry-to-database synchronization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from observatory_db.base import utc_now
from observatory_db.models import (
    AliasStatus as DatabaseAliasStatus,
)
from observatory_db.models import (
    AliasType as DatabaseAliasType,
)
from observatory_db.models import (
    DataQualityCheck,
    QualityStatus,
    Source,
    Topic,
    TopicAlias,
    TopicCategory,
    TopicRegistryAuditLog,
    TopicRegistryVersion,
    TopicSourceMapping,
)
from observatory_db.models import (
    MatchMode as DatabaseMatchMode,
)
from observatory_db.models import (
    TopicStatus as DatabaseTopicStatus,
)
from topic_registry.diff import (
    RegistryChange,
    RegistryDiff,
    TopicRegistryDiffService,
    warning_payloads,
)
from topic_registry.models import LoadedRegistry, StrictModel, TopicStatus
from topic_registry.normalization import normalize_canonical_name
from topic_registry.source_catalog import SOURCE_CATALOG


class SyncReport(StrictModel):
    dry_run: bool
    changed: bool
    version: int | None = None
    checksum: str
    diff: RegistryDiff
    topic_count: int
    alias_count: int
    category_count: int
    mapping_count: int


class TopicRegistrySyncService:
    def __init__(
        self,
        session: Session,
        *,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.diff_service = TopicRegistryDiffService()
        self.before_commit = before_commit

    def diff(self, registry: LoadedRegistry) -> RegistryDiff:
        return self.diff_service.compare(self.session, registry)

    def sync(
        self,
        registry: LoadedRegistry,
        *,
        dry_run: bool = False,
        applied_by: str = "signal-observatory-cli",
    ) -> SyncReport:
        registry_diff = self.diff(registry)
        if dry_run or not registry_diff.has_changes:
            self.session.rollback()
            return self._report(registry, registry_diff, dry_run=dry_run, version=None)
        try:
            next_version = (registry_diff.latest_version or 0) + 1
            version = TopicRegistryVersion(
                version=next_version,
                checksum=registry.checksum,
                source_file_count=len(registry.source_files),
                topic_count=len(registry.topics),
                alias_count=registry.alias_count,
                mapping_count=registry.mapping_count,
                applied_by=applied_by,
                metadata_={
                    "warning_count": len(registry_diff.warnings),
                    "warnings": warning_payloads(registry_diff.warnings),
                },
            )
            self.session.add(version)
            self.session.flush()
            sources = self._ensure_sources(registry)
            categories = self._sync_categories(registry)
            self._sync_topics(registry, categories, sources, next_version)
            self._write_audit(version, registry_diff.changes, registry)
            self._write_quality_checks(registry, registry_diff, next_version)
            if self.before_commit is not None:
                self.before_commit()
            self.session.commit()
            return self._report(
                registry,
                registry_diff,
                dry_run=False,
                version=next_version,
            )
        except Exception:
            self.session.rollback()
            raise

    def _ensure_sources(self, registry: LoadedRegistry) -> dict[str, Source]:
        required = {
            source_name for topic in registry.topics for source_name, _ in topic.sources.items()
        }
        existing = {
            source.name: source
            for source in self.session.scalars(
                select(Source).where(Source.name.in_(required))
            ).all()
        }
        for source_name in sorted(required - set(existing)):
            spec = SOURCE_CATALOG[source_name]
            source = Source(
                name=spec.name,
                kind=spec.kind,
                base_url=spec.base_url,
                metadata_={"managed_by": "topic_registry_source_catalog"},
            )
            self.session.add(source)
            existing[source_name] = source
        self.session.flush()
        return existing

    def _sync_categories(self, registry: LoadedRegistry) -> dict[str, TopicCategory]:
        existing = {
            category.slug: category
            for category in self.session.scalars(select(TopicCategory)).all()
        }
        for desired in registry.categories:
            category = existing.get(desired.slug)
            if category is None:
                category = TopicCategory(slug=desired.slug, name=desired.name)
                self.session.add(category)
                existing[desired.slug] = category
            category.name = desired.name
            category.description = desired.description
            category.sort_order = desired.sort_order
        self.session.flush()
        for desired in registry.categories:
            existing[desired.slug].parent = existing.get(desired.parent) if desired.parent else None
        self.session.flush()
        return existing

    def _sync_topics(
        self,
        registry: LoadedRegistry,
        categories: dict[str, TopicCategory],
        sources: dict[str, Source],
        registry_version: int,
    ) -> None:
        existing = {topic.slug: topic for topic in self.session.scalars(select(Topic)).all()}
        for desired in registry.topics:
            topic = existing.get(desired.slug)
            if topic is None:
                topic = Topic(slug=desired.slug, canonical_name=desired.canonical_name)
                self.session.add(topic)
                existing[desired.slug] = topic
            previous_status = topic.status
            topic.canonical_name = desired.canonical_name
            topic.normalized_name = normalize_canonical_name(desired.canonical_name)
            topic.description = desired.description
            topic.category = categories[desired.category]
            topic.status = DatabaseTopicStatus(desired.status.value)
            topic.monitoring_priority = desired.monitoring_priority
            topic.registry_version = registry_version
            topic.metadata_ = dict(desired.metadata)
            if desired.status is TopicStatus.DEPRECATED:
                topic.deprecated_at = topic.deprecated_at or utc_now()
            elif previous_status is DatabaseTopicStatus.DEPRECATED:
                topic.deprecated_at = None
            self.session.flush()
            self._sync_aliases(topic, desired.aliases)
            self._sync_mappings(topic, desired.sources.items(), sources)

    def _sync_aliases(self, topic: Topic, desired_aliases: Any) -> None:
        existing = {
            alias.normalized_alias: alias
            for alias in self.session.scalars(
                select(TopicAlias).where(
                    TopicAlias.topic_id == topic.id,
                    TopicAlias.source_id.is_(None),
                )
            ).all()
        }
        for desired in desired_aliases:
            alias = existing.get(desired.normalized)
            if alias is None:
                alias = TopicAlias(
                    topic=topic,
                    alias=desired.value,
                    normalized_alias=desired.normalized,
                )
                self.session.add(alias)
            alias.alias = desired.value
            alias.alias_type = DatabaseAliasType(desired.alias_type.value)
            alias.match_mode = DatabaseMatchMode(desired.match_mode.value)
            alias.case_sensitive = desired.case_sensitive
            alias.status = DatabaseAliasStatus(desired.status.value)
            alias.confidence = desired.confidence
            alias.metadata_ = dict(desired.metadata)
        self.session.flush()

    def _sync_mappings(
        self,
        topic: Topic,
        desired_mappings: Any,
        sources: dict[str, Source],
    ) -> None:
        existing = {
            mapping.source_id: mapping
            for mapping in self.session.scalars(
                select(TopicSourceMapping).where(
                    TopicSourceMapping.topic_id == topic.id,
                    TopicSourceMapping.mapping_type == "registry",
                )
            ).all()
        }
        for source_name, desired in desired_mappings:
            source = sources[source_name]
            mapping = existing.get(source.id)
            if mapping is None:
                mapping = TopicSourceMapping(topic=topic, source=source, mapping_type="registry")
                self.session.add(mapping)
            values = desired.configured_values()
            mapping.enabled = desired.enabled
            mapping.external_identifier = (
                values[0] if source_name == "wikipedia" and len(values) == 1 else None
            )
            mapping.query = values[0] if source_name != "wikipedia" and len(values) == 1 else None
            mapping.configuration = desired.model_dump(mode="json", exclude={"enabled"})
        self.session.flush()

    def _write_audit(
        self,
        version: TopicRegistryVersion,
        changes: tuple[RegistryChange, ...],
        registry: LoadedRegistry,
    ) -> None:
        for change in changes:
            self.session.add(
                TopicRegistryAuditLog(
                    version=version,
                    action=change.action.value,
                    entity_type=change.entity_type,
                    entity_id=change.entity_key,
                    before=change.before,
                    after=change.after,
                )
            )
        for warning in registry.warnings:
            if warning.code == "ALLOWED_ALIAS_COLLISION":
                self.session.add(
                    TopicRegistryAuditLog(
                        version=version,
                        action="review",
                        entity_type="alias_collision",
                        entity_id=warning.entity or "unknown",
                        before=None,
                        after=warning.model_dump(mode="json"),
                    )
                )

    def _write_quality_checks(
        self,
        registry: LoadedRegistry,
        registry_diff: RegistryDiff,
        registry_version: int,
    ) -> None:
        orphaned = sum(
            1 for warning in registry_diff.warnings if warning.code == "ORPHANED_DATABASE_TOPIC"
        )
        active = sum(topic.status is TopicStatus.ACTIVE for topic in registry.topics)
        unmapped = sum(not topic.sources.items() for topic in registry.topics)
        without_aliases = sum(not topic.aliases for topic in registry.topics)
        allowed_collisions = sum(
            warning.code == "ALLOWED_ALIAS_COLLISION" for warning in registry.warnings
        )
        checks = {
            "topic_count": (len(registry.topics), QualityStatus.PASSED),
            "active_topic_count": (active, QualityStatus.PASSED),
            "alias_count": (registry.alias_count, QualityStatus.PASSED),
            "unmapped_topics": (
                unmapped,
                QualityStatus.WARNING if unmapped else QualityStatus.PASSED,
            ),
            "duplicate_aliases": (
                allowed_collisions,
                QualityStatus.WARNING if allowed_collisions else QualityStatus.PASSED,
            ),
            "orphaned_database_topics": (
                orphaned,
                QualityStatus.WARNING if orphaned else QualityStatus.PASSED,
            ),
            "topics_without_aliases": (
                without_aliases,
                QualityStatus.WARNING if without_aliases else QualityStatus.PASSED,
            ),
            "topics_without_any_source_mapping": (
                unmapped,
                QualityStatus.WARNING if unmapped else QualityStatus.PASSED,
            ),
        }
        for name, (count, status) in checks.items():
            self.session.add(
                DataQualityCheck(
                    name=name,
                    status=status,
                    observed={"count": count},
                    expected={"count": 0}
                    if name
                    in {
                        "unmapped_topics",
                        "duplicate_aliases",
                        "orphaned_database_topics",
                        "topics_without_aliases",
                        "topics_without_any_source_mapping",
                    }
                    else {"minimum": 0},
                    details={"registry_version": registry_version},
                )
            )

    @staticmethod
    def _report(
        registry: LoadedRegistry,
        registry_diff: RegistryDiff,
        *,
        dry_run: bool,
        version: int | None,
    ) -> SyncReport:
        return SyncReport(
            dry_run=dry_run,
            changed=registry_diff.has_changes,
            version=version,
            checksum=registry.checksum,
            diff=registry_diff,
            topic_count=len(registry.topics),
            alias_count=registry.alias_count,
            category_count=len(registry.categories),
            mapping_count=registry.mapping_count,
        )
