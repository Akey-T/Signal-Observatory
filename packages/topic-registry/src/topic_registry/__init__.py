"""Curated Topic Registry schema, validation, diff, and synchronization."""

from topic_registry.loader import TopicRegistryLoader, TopicRegistryValidationError
from topic_registry.models import (
    AliasDefinition,
    AliasStatus,
    AliasType,
    CategoryDefinition,
    LoadedRegistry,
    MatchMode,
    TopicDefinition,
    TopicStatus,
)
from topic_registry.normalization import normalize_alias

__all__ = [
    "AliasDefinition",
    "AliasStatus",
    "AliasType",
    "CategoryDefinition",
    "LoadedRegistry",
    "MatchMode",
    "TopicDefinition",
    "TopicRegistryLoader",
    "TopicRegistryValidationError",
    "TopicStatus",
    "normalize_alias",
]
