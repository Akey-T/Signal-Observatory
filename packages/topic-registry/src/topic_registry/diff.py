"""Read-only comparison between validated registry content and database state."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from observatory_db.models import (
    Topic,
    TopicAlias,
    TopicCategory,
    TopicRegistryVersion,
    TopicSourceMapping,
)
from topic_registry.models import IssueSeverity, LoadedRegistry, RegistryIssue, StrictModel
from topic_registry.normalization import normalize_canonical_name


def warning_payloads(
    warnings: list[RegistryIssue] | tuple[RegistryIssue, ...],
) -> list[dict[str, Any]]:
    """Return a deterministic persisted representation of validation warnings."""

    ordered = sorted(
        warnings,
        key=lambda warning: (
            warning.code,
            warning.entity or "",
            warning.source_file or "",
            warning.message,
        ),
    )
    return [warning.model_dump(mode="json") for warning in ordered]


class ChangeAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    ADD = "add"
    REGISTRY_UPDATE = "registry_update"


class RegistryChange(StrictModel):
    action: ChangeAction
    entity_type: str
    entity_key: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class RegistryDiff(StrictModel):
    checksum: str
    changes: tuple[RegistryChange, ...] = ()
    warnings: tuple[RegistryIssue, ...] = ()
    latest_version: int | None = None
    latest_checksum: str | None = None

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    def count(self, entity_type: str, action: ChangeAction | None = None) -> int:
        return sum(
            1
            for change in self.changes
            if change.entity_type == entity_type and (action is None or change.action is action)
        )

    def summary(self) -> dict[str, Any]:
        return {
            "topics": {
                "create": self.count("topic", ChangeAction.CREATE),
                "update": self.count("topic", ChangeAction.UPDATE),
                "orphaned": sum(
                    1 for warning in self.warnings if warning.code == "ORPHANED_DATABASE_TOPIC"
                ),
            },
            "categories": {
                "create": self.count("category", ChangeAction.CREATE),
                "update": self.count("category", ChangeAction.UPDATE),
            },
            "aliases": {
                "add": self.count("alias", ChangeAction.ADD),
                "update": self.count("alias", ChangeAction.UPDATE),
            },
            "mappings": {
                "add": self.count("mapping", ChangeAction.ADD),
                "update": self.count("mapping", ChangeAction.UPDATE),
            },
            "warnings": len(self.warnings),
            "errors": 0,
        }


class TopicRegistryDiffService:
    def compare(self, session: Session, registry: LoadedRegistry) -> RegistryDiff:
        changes: list[RegistryChange] = []
        warnings = list(registry.warnings)
        latest = session.scalar(
            select(TopicRegistryVersion).order_by(TopicRegistryVersion.version.desc()).limit(1)
        )

        categories = {
            category.slug: category
            for category in session.scalars(
                select(TopicCategory).options(selectinload(TopicCategory.parent))
            ).all()
        }
        registry_category_slugs = {category.slug for category in registry.categories}
        for category_definition in registry.categories:
            current_category = categories.get(category_definition.slug)
            after = self._category_definition(category_definition)
            if current_category is None:
                changes.append(
                    RegistryChange(
                        action=ChangeAction.CREATE,
                        entity_type="category",
                        entity_key=category_definition.slug,
                        after=after,
                    )
                )
            else:
                before = self._category_record(current_category)
                if before != after:
                    changes.append(
                        RegistryChange(
                            action=ChangeAction.UPDATE,
                            entity_type="category",
                            entity_key=category_definition.slug,
                            before=before,
                            after=after,
                        )
                    )
        for slug in sorted(set(categories) - registry_category_slugs):
            warnings.append(
                self._warning(
                    "ORPHANED_DATABASE_CATEGORY",
                    f"database category {slug} is absent from registry YAML and was retained",
                    slug,
                )
            )

        topics = {
            topic.slug: topic
            for topic in session.scalars(
                select(Topic).options(
                    selectinload(Topic.category),
                    selectinload(Topic.aliases),
                    selectinload(Topic.source_mappings).selectinload(TopicSourceMapping.source),
                )
            ).all()
        }
        registry_topic_slugs = {topic.slug for topic in registry.topics}
        for topic_definition in registry.topics:
            current_topic = topics.get(topic_definition.slug)
            after = self._topic_definition(topic_definition)
            if current_topic is None:
                changes.append(
                    RegistryChange(
                        action=ChangeAction.CREATE,
                        entity_type="topic",
                        entity_key=topic_definition.slug,
                        after=after,
                    )
                )
                for alias in topic_definition.aliases:
                    changes.append(
                        RegistryChange(
                            action=ChangeAction.ADD,
                            entity_type="alias",
                            entity_key=f"{topic_definition.slug}:{alias.normalized}",
                            after=self._alias_definition(alias),
                        )
                    )
                for source_name, source_config in topic_definition.sources.items():
                    changes.append(
                        RegistryChange(
                            action=ChangeAction.ADD,
                            entity_type="mapping",
                            entity_key=f"{topic_definition.slug}:{source_name}",
                            after=self._mapping_definition(source_name, source_config),
                        )
                    )
                continue
            before = self._topic_record(current_topic)
            if before != after:
                changes.append(
                    RegistryChange(
                        action=ChangeAction.UPDATE,
                        entity_type="topic",
                        entity_key=topic_definition.slug,
                        before=before,
                        after=after,
                    )
                )
            current_aliases = {
                alias.normalized_alias: alias
                for alias in current_topic.aliases
                if alias.source_id is None
            }
            desired_aliases = {alias.normalized: alias for alias in topic_definition.aliases}
            for normalized, alias_definition in desired_aliases.items():
                current_alias = current_aliases.get(normalized)
                alias_after = self._alias_definition(alias_definition)
                if current_alias is None:
                    changes.append(
                        RegistryChange(
                            action=ChangeAction.ADD,
                            entity_type="alias",
                            entity_key=f"{topic_definition.slug}:{normalized}",
                            after=alias_after,
                        )
                    )
                else:
                    alias_before = self._alias_record(current_alias)
                    if alias_before != alias_after:
                        changes.append(
                            RegistryChange(
                                action=ChangeAction.UPDATE,
                                entity_type="alias",
                                entity_key=f"{topic_definition.slug}:{normalized}",
                                before=alias_before,
                                after=alias_after,
                            )
                        )
            for normalized in sorted(set(current_aliases) - set(desired_aliases)):
                warnings.append(
                    self._warning(
                        "ORPHANED_DATABASE_ALIAS",
                        f"database alias {topic_definition.slug}:{normalized} "
                        "is absent from YAML and was retained",
                        f"{topic_definition.slug}:{normalized}",
                    )
                )

            current_mappings = {
                mapping.source.name: mapping
                for mapping in current_topic.source_mappings
                if mapping.mapping_type == "registry"
            }
            desired_mappings = dict(topic_definition.sources.items())
            for source_name, source_config in desired_mappings.items():
                mapping_after = self._mapping_definition(source_name, source_config)
                current_mapping = current_mappings.get(source_name)
                if current_mapping is None:
                    changes.append(
                        RegistryChange(
                            action=ChangeAction.ADD,
                            entity_type="mapping",
                            entity_key=f"{topic_definition.slug}:{source_name}",
                            after=mapping_after,
                        )
                    )
                else:
                    mapping_before = self._mapping_record(current_mapping)
                    if mapping_before != mapping_after:
                        changes.append(
                            RegistryChange(
                                action=ChangeAction.UPDATE,
                                entity_type="mapping",
                                entity_key=f"{topic_definition.slug}:{source_name}",
                                before=mapping_before,
                                after=mapping_after,
                            )
                        )
            for source_name in sorted(set(current_mappings) - set(desired_mappings)):
                warnings.append(
                    self._warning(
                        "ORPHANED_DATABASE_MAPPING",
                        f"mapping {topic_definition.slug}:{source_name} "
                        "is absent from YAML and was retained",
                        f"{topic_definition.slug}:{source_name}",
                    )
                )

        for slug in sorted(set(topics) - registry_topic_slugs):
            warnings.append(
                self._warning(
                    "ORPHANED_DATABASE_TOPIC",
                    f"database topic {slug} is absent from registry YAML and was retained",
                    slug,
                )
            )

        warning_metadata = warning_payloads(warnings)
        latest_warning_metadata = latest.metadata_.get("warnings", []) if latest else []
        registry_metadata_changed = bool(
            latest is not None
            and (
                latest.checksum != registry.checksum or latest_warning_metadata != warning_metadata
            )
        )
        if latest is not None and registry_metadata_changed and not changes:
            changes.append(
                RegistryChange(
                    action=ChangeAction.REGISTRY_UPDATE,
                    entity_type="registry",
                    entity_key="topic-registry",
                    before={
                        "checksum": latest.checksum,
                        "warnings": latest_warning_metadata,
                    },
                    after={"checksum": registry.checksum, "warnings": warning_metadata},
                )
            )
        return RegistryDiff(
            checksum=registry.checksum,
            changes=tuple(changes),
            warnings=tuple(warnings),
            latest_version=latest.version if latest else None,
            latest_checksum=latest.checksum if latest else None,
        )

    @staticmethod
    def _category_definition(category: Any) -> dict[str, Any]:
        return {
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "parent": category.parent,
            "sort_order": category.sort_order,
        }

    @staticmethod
    def _category_record(category: TopicCategory) -> dict[str, Any]:
        return {
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "parent": category.parent.slug if category.parent else None,
            "sort_order": category.sort_order,
        }

    @staticmethod
    def _topic_definition(topic: Any) -> dict[str, Any]:
        return {
            "canonical_name": topic.canonical_name,
            "normalized_name": normalize_canonical_name(topic.canonical_name),
            "slug": topic.slug,
            "description": topic.description,
            "category": topic.category,
            "status": topic.status.value,
            "monitoring_priority": topic.monitoring_priority,
            "metadata": topic.metadata,
        }

    @staticmethod
    def _topic_record(topic: Topic) -> dict[str, Any]:
        return {
            "canonical_name": topic.canonical_name,
            "normalized_name": topic.normalized_name,
            "slug": topic.slug,
            "description": topic.description,
            "category": topic.category.slug if topic.category else None,
            "status": topic.status.value,
            "monitoring_priority": topic.monitoring_priority,
            "metadata": topic.metadata_,
        }

    @staticmethod
    def _alias_definition(alias: Any) -> dict[str, Any]:
        return {
            "alias": alias.value,
            "normalized_alias": alias.normalized,
            "alias_type": alias.alias_type.value,
            "match_mode": alias.match_mode.value,
            "case_sensitive": alias.case_sensitive,
            "status": alias.status.value,
            "confidence": alias.confidence,
            "metadata": alias.metadata,
        }

    @staticmethod
    def _alias_record(alias: TopicAlias) -> dict[str, Any]:
        return {
            "alias": alias.alias,
            "normalized_alias": alias.normalized_alias,
            "alias_type": alias.alias_type.value,
            "match_mode": alias.match_mode.value,
            "case_sensitive": alias.case_sensitive,
            "status": alias.status.value,
            "confidence": alias.confidence,
            "metadata": alias.metadata_,
        }

    @staticmethod
    def _mapping_definition(source_name: str, source_config: Any) -> dict[str, Any]:
        configuration = source_config.model_dump(mode="json", exclude={"enabled"})
        values = source_config.configured_values()
        return {
            "source": source_name,
            "enabled": source_config.enabled,
            "mapping_type": "registry",
            "external_identifier": values[0]
            if source_name == "wikipedia" and len(values) == 1
            else None,
            "query": values[0] if source_name != "wikipedia" and len(values) == 1 else None,
            "configuration": configuration,
        }

    @staticmethod
    def _mapping_record(mapping: TopicSourceMapping) -> dict[str, Any]:
        return {
            "source": mapping.source.name,
            "enabled": mapping.enabled,
            "mapping_type": mapping.mapping_type,
            "external_identifier": mapping.external_identifier,
            "query": mapping.query,
            "configuration": mapping.configuration,
        }

    @staticmethod
    def _warning(code: str, message: str, entity: str) -> RegistryIssue:
        return RegistryIssue(
            code=code,
            message=message,
            severity=IssueSeverity.WARNING,
            entity=entity,
        )
