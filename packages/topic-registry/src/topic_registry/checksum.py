"""Deterministic canonical serialization for registry version identity."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from topic_registry.models import (
    AllowedAliasCollision,
    CategoryDefinition,
    TopicDefinition,
)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_canonicalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
        )
    return value


def registry_payload(
    categories: tuple[CategoryDefinition, ...],
    topics: tuple[TopicDefinition, ...],
    collisions: tuple[AllowedAliasCollision, ...],
) -> dict[str, Any]:
    raw = {
        "schema_version": 1,
        "categories": [
            category.model_dump(mode="json", by_alias=True, exclude_none=True)
            for category in sorted(categories, key=lambda item: item.slug)
        ],
        "topics": [
            topic.model_dump(mode="json", by_alias=True, exclude_none=True)
            for topic in sorted(topics, key=lambda item: item.slug)
        ],
        "allowed_alias_collisions": [
            collision.model_dump(mode="json", by_alias=True, exclude_none=True)
            for collision in sorted(
                collisions,
                key=lambda item: (item.alias.casefold(), tuple(sorted(item.topics))),
            )
        ],
    }
    return cast(dict[str, Any], _canonicalize(raw))


def registry_checksum(
    categories: tuple[CategoryDefinition, ...],
    topics: tuple[TopicDefinition, ...],
    collisions: tuple[AllowedAliasCollision, ...],
) -> str:
    serialized = json.dumps(
        registry_payload(categories, topics, collisions),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()
