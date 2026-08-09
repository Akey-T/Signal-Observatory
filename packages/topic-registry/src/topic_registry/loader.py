"""Filesystem discovery, strict YAML parsing, and cross-file validation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml
from pydantic import ValidationError

from topic_registry.checksum import registry_checksum
from topic_registry.models import (
    AliasDefinition,
    AllowedAliasCollision,
    CategoryDefinition,
    IssueSeverity,
    LoadedRegistry,
    RegistryFileDefinition,
    RegistryIssue,
    TopicDefinition,
)
from topic_registry.normalization import normalize_alias, normalize_canonical_name


class TopicRegistryValidationError(ValueError):
    def __init__(self, issues: list[RegistryIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in issues[:5])
        super().__init__(summary)


class TopicRegistryLoader:
    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)

    def discover_files(self) -> tuple[Path, ...]:
        if not self.registry_path.is_dir():
            raise TopicRegistryValidationError(
                [self._error("REGISTRY_PATH_NOT_FOUND", f"{self.registry_path} is not a directory")]
            )
        files = sorted((*self.registry_path.rglob("*.yaml"), *self.registry_path.rglob("*.yml")))
        if not files:
            raise TopicRegistryValidationError(
                [self._error("REGISTRY_EMPTY", f"no YAML files found under {self.registry_path}")]
            )
        return tuple(files)

    def load(self) -> LoadedRegistry:
        files = self.discover_files()
        definitions: list[RegistryFileDefinition] = []
        issues: list[RegistryIssue] = []
        for path in files:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("registry file root must be a mapping")
                definitions.append(RegistryFileDefinition.model_validate(raw))
            except yaml.YAMLError as error:
                issues.append(self._error("YAML_PARSE_ERROR", str(error), path))
            except ValidationError as error:
                issues.extend(self._pydantic_issues(path, error))
            except (OSError, ValueError) as error:
                issues.append(self._error("SCHEMA_VALIDATION", str(error), path))
        if issues:
            raise TopicRegistryValidationError(issues)

        categories = tuple(
            category for definition in definitions for category in definition.categories
        )
        topics = tuple(topic for definition in definitions for topic in definition.topics)
        collisions = tuple(
            collision
            for definition in definitions
            for collision in definition.allowed_alias_collisions
        )
        issues.extend(self._cross_file_issues(categories, topics, collisions))
        errors = [issue for issue in issues if issue.severity is IssueSeverity.ERROR]
        if errors:
            raise TopicRegistryValidationError(issues)
        return LoadedRegistry(
            categories=tuple(sorted(categories, key=lambda item: item.slug)),
            topics=tuple(sorted(topics, key=lambda item: item.slug)),
            allowed_alias_collisions=tuple(
                sorted(collisions, key=lambda item: (item.alias.casefold(), item.topics))
            ),
            source_files=files,
            checksum=registry_checksum(categories, topics, collisions),
            issues=tuple(issues),
        )

    def _cross_file_issues(
        self,
        categories: tuple[CategoryDefinition, ...],
        topics: tuple[TopicDefinition, ...],
        collisions: tuple[AllowedAliasCollision, ...],
    ) -> list[RegistryIssue]:
        issues: list[RegistryIssue] = []
        category_by_slug: dict[str, CategoryDefinition] = {}
        category_names: dict[str, str] = {}
        for category in categories:
            if category.slug in category_by_slug:
                issues.append(
                    self._error("DUPLICATE_CATEGORY_SLUG", f"duplicate category: {category.slug}")
                )
            category_by_slug[category.slug] = category
            normalized_name = normalize_canonical_name(category.name)
            if normalized_name in category_names:
                issues.append(
                    self._error(
                        "DUPLICATE_CATEGORY_NAME", f"duplicate category name: {category.name}"
                    )
                )
            category_names[normalized_name] = category.slug
        for category in categories:
            if category.parent and category.parent not in category_by_slug:
                issues.append(
                    self._error(
                        "MISSING_PARENT_CATEGORY",
                        f"category {category.slug} references missing parent {category.parent}",
                    )
                )
        issues.extend(self._category_cycle_issues(category_by_slug))

        topic_by_slug: dict[str, TopicDefinition] = {}
        canonical_names: dict[str, str] = {}
        aliases_by_folded: dict[str, list[tuple[str, AliasDefinition]]] = defaultdict(list)
        for topic in topics:
            if topic.slug in topic_by_slug:
                issues.append(self._error("DUPLICATE_TOPIC_SLUG", f"duplicate topic: {topic.slug}"))
            topic_by_slug[topic.slug] = topic
            normalized_name = normalize_canonical_name(topic.canonical_name)
            if normalized_name in canonical_names:
                issues.append(
                    self._error(
                        "DUPLICATE_CANONICAL_NAME",
                        f"canonical name {topic.canonical_name!r} belongs to multiple topics",
                    )
                )
            canonical_names[normalized_name] = topic.slug
            if topic.category not in category_by_slug:
                issues.append(
                    self._error(
                        "MISSING_CATEGORY",
                        f"topic {topic.slug} references missing category {topic.category}",
                        entity=topic.slug,
                    )
                )
            seen_aliases: set[tuple[str, bool]] = set()
            for alias in topic.aliases:
                identity = (alias.normalized, alias.case_sensitive)
                if identity in seen_aliases:
                    issues.append(
                        self._error(
                            "DUPLICATE_TOPIC_ALIAS",
                            f"topic {topic.slug} repeats alias {alias.value!r}",
                            entity=topic.slug,
                        )
                    )
                seen_aliases.add(identity)
                aliases_by_folded[normalize_alias(alias.value)].append((topic.slug, alias))

        allowlist_by_alias: dict[str, AllowedAliasCollision] = {}
        for collision in collisions:
            folded = normalize_alias(collision.alias)
            if folded in allowlist_by_alias:
                issues.append(
                    self._error(
                        "DUPLICATE_COLLISION_ALLOWLIST",
                        f"alias {collision.alias!r} is repeated in collision allowlist",
                    )
                )
            allowlist_by_alias[folded] = collision
        used_allowlist: set[str] = set()
        for folded, entries in aliases_by_folded.items():
            topic_slugs = {topic_slug for topic_slug, _alias in entries}
            if len(topic_slugs) < 2 or not self._entries_collide(entries):
                continue
            allowed = allowlist_by_alias.get(folded)
            if allowed and set(allowed.topics) == topic_slugs:
                used_allowlist.add(folded)
                issues.append(
                    self._warning(
                        "ALLOWED_ALIAS_COLLISION",
                        f"reviewed alias {folded!r} is shared by {sorted(topic_slugs)}: "
                        f"{allowed.reason}",
                        entity=folded,
                    )
                )
            else:
                issues.append(
                    self._error(
                        "ALIAS_COLLISION",
                        f"alias {folded!r} is shared by {sorted(topic_slugs)}",
                        entity=folded,
                    )
                )
        for collision in collisions:
            folded = normalize_alias(collision.alias)
            unknown_topics = sorted(set(collision.topics) - set(topic_by_slug))
            if unknown_topics:
                issues.append(
                    self._error(
                        "ALLOWLIST_UNKNOWN_TOPIC",
                        f"allowlist for {collision.alias!r} references {unknown_topics}",
                    )
                )
            elif folded not in used_allowlist:
                issues.append(
                    self._warning(
                        "UNUSED_COLLISION_ALLOWLIST",
                        f"allowlist for {collision.alias!r} does not match a current collision",
                    )
                )
        return issues

    @staticmethod
    def _entries_collide(entries: list[tuple[str, AliasDefinition]]) -> bool:
        aliases = [alias for _topic, alias in entries]
        if any(not alias.case_sensitive for alias in aliases):
            return True
        normalized = {alias.normalized for alias in aliases}
        return len(normalized) < len(aliases)

    def _category_cycle_issues(
        self, categories: dict[str, CategoryDefinition]
    ) -> list[RegistryIssue]:
        issues: list[RegistryIssue] = []
        for start in categories:
            path: list[str] = []
            current: str | None = start
            while current is not None and current in categories:
                if current in path:
                    cycle = path[path.index(current) :] + [current]
                    issues.append(
                        self._error("CATEGORY_CYCLE", f"category cycle: {' -> '.join(cycle)}")
                    )
                    break
                path.append(current)
                current = categories[current].parent
        unique = {(issue.code, issue.message): issue for issue in issues}
        return list(unique.values())

    def _pydantic_issues(self, path: Path, error: ValidationError) -> list[RegistryIssue]:
        issues: list[RegistryIssue] = []
        for detail in error.errors(include_url=False):
            location = ".".join(str(part) for part in detail["loc"])
            code = "SCHEMA_VALIDATION"
            if detail["type"] == "extra_forbidden":
                code = "INVALID_SOURCE" if ".sources." in f".{location}." else "UNKNOWN_FIELD"
            issues.append(self._error(code, f"{location}: {detail['msg']}", path, entity=location))
        return issues

    @staticmethod
    def _error(
        code: str,
        message: str,
        source_file: Path | None = None,
        *,
        entity: str | None = None,
    ) -> RegistryIssue:
        return RegistryIssue(
            code=code,
            message=message,
            severity=IssueSeverity.ERROR,
            source_file=str(source_file) if source_file else None,
            entity=entity,
        )

    @staticmethod
    def _warning(code: str, message: str, *, entity: str | None = None) -> RegistryIssue:
        return RegistryIssue(
            code=code,
            message=message,
            severity=IssueSeverity.WARNING,
            entity=entity,
        )
