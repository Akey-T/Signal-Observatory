"""Small read model shared by CLI and the read-only Topic API."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from observatory_db.models import (
    Topic,
    TopicAlias,
    TopicCategory,
    TopicRegistryVersion,
    TopicSourceMapping,
    TopicStatus,
)


class TopicQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_topics(
        self,
        *,
        category: str | None = None,
        status: TopicStatus | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Topic], int]:
        statement = select(Topic)
        if category is not None:
            statement = statement.join(Topic.category).where(TopicCategory.slug == category)
        if status is not None:
            statement = statement.where(Topic.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.outerjoin(Topic.aliases).where(
                or_(
                    Topic.canonical_name.ilike(pattern),
                    Topic.slug.ilike(pattern),
                    TopicAlias.alias.ilike(pattern),
                )
            )
        statement = statement.distinct()
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        topics = list(
            self.session.scalars(
                statement.options(
                    selectinload(Topic.category),
                    selectinload(Topic.aliases),
                    selectinload(Topic.source_mappings).selectinload(TopicSourceMapping.source),
                )
                .order_by(Topic.monitoring_priority.desc(), Topic.canonical_name)
                .limit(limit)
                .offset(offset)
            ).unique()
        )
        return topics, int(total or 0)

    def get_topic(self, slug: str) -> Topic | None:
        return self.session.scalar(
            select(Topic)
            .where(Topic.slug == slug)
            .options(
                selectinload(Topic.category),
                selectinload(Topic.aliases),
                selectinload(Topic.source_mappings).selectinload(TopicSourceMapping.source),
            )
        )

    def list_categories(self) -> list[TopicCategory]:
        return list(
            self.session.scalars(
                select(TopicCategory)
                .options(selectinload(TopicCategory.parent))
                .order_by(TopicCategory.sort_order, TopicCategory.name)
            )
        )

    def registry_status(self) -> dict[str, object] | None:
        latest = self.session.scalar(
            select(TopicRegistryVersion).order_by(TopicRegistryVersion.version.desc()).limit(1)
        )
        if latest is None:
            return None
        active_count = self.session.scalar(
            select(func.count()).select_from(Topic).where(Topic.status == TopicStatus.ACTIVE)
        )
        mapping_count = self.session.scalar(select(func.count()).select_from(TopicSourceMapping))
        alias_count = self.session.scalar(select(func.count()).select_from(TopicAlias))
        topic_count = self.session.scalar(select(func.count()).select_from(Topic))
        return {
            "version": latest.version,
            "checksum": latest.checksum,
            "last_synced_at": latest.created_at,
            "topic_count": int(topic_count or 0),
            "active_topics": int(active_count or 0),
            "alias_count": int(alias_count or 0),
            "source_mapping_count": int(mapping_count or 0),
            "warnings": int(latest.metadata_.get("warning_count", 0)),
        }


def topic_to_dict(topic: Topic) -> dict[str, object]:
    return {
        "topic_id": str(topic.id),
        "canonical_name": topic.canonical_name,
        "slug": topic.slug,
        "description": topic.description,
        "category": topic.category.slug if topic.category else None,
        "status": topic.status.value,
        "monitoring_priority": topic.monitoring_priority,
        "deprecated_at": topic.deprecated_at,
        "registry_version": topic.registry_version,
        "metadata": topic.metadata_,
        "aliases": [
            {
                "value": alias.alias,
                "normalized_alias": alias.normalized_alias,
                "type": alias.alias_type.value,
                "match_mode": alias.match_mode.value,
                "case_sensitive": alias.case_sensitive,
                "status": alias.status.value,
                "confidence": alias.confidence,
                "metadata": alias.metadata_,
            }
            for alias in sorted(topic.aliases, key=lambda item: item.normalized_alias)
            if alias.source_id is None
        ],
        "sources": [
            {
                "source": mapping.source.name,
                "enabled": mapping.enabled,
                "mapping_type": mapping.mapping_type,
                "external_identifier": mapping.external_identifier,
                "query": mapping.query,
                "configuration": mapping.configuration,
            }
            for mapping in sorted(topic.source_mappings, key=lambda item: item.source.name)
        ],
    }
