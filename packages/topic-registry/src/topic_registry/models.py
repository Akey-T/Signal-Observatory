"""Strict human-maintained YAML schema and normalized registry values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from topic_registry.normalization import normalize_alias

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class TopicStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"


class AliasStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class AliasType(StrEnum):
    NAME = "name"
    ABBREVIATION = "abbreviation"
    SPELLING = "spelling"
    PRODUCT_NAME = "product_name"
    RELATED_TERM = "related_term"
    SEARCH_TERM = "search_term"


class MatchMode(StrEnum):
    EXACT = "exact"
    PHRASE = "phrase"


class CategoryDefinition(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    parent: str | None = Field(default=None, pattern=SLUG_PATTERN, max_length=150)
    sort_order: int = Field(default=0, ge=0, le=10000)


class AliasDefinition(StrictModel):
    value: str = Field(min_length=1, max_length=250)
    alias_type: AliasType = Field(default=AliasType.NAME, alias="type")
    match_mode: MatchMode = MatchMode.EXACT
    case_sensitive: bool = False
    status: AliasStatus = AliasStatus.ACTIVE
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def normalized(self) -> str:
        return normalize_alias(self.value, case_sensitive=self.case_sensitive)


class QuerySourceConfig(StrictModel, ABC):
    enabled: bool = True

    @abstractmethod
    def configured_values(self) -> tuple[str, ...]:
        """Return the source query values without interpreting or executing them."""

    @model_validator(mode="after")
    def enabled_source_has_values(self) -> QuerySourceConfig:
        if self.enabled and not self.configured_values():
            raise ValueError("an enabled source mapping requires at least one value")
        return self


class ArxivSourceConfig(QuerySourceConfig):
    search_terms: tuple[str, ...] = ()

    def configured_values(self) -> tuple[str, ...]:
        return self.search_terms


class GitHubSourceConfig(QuerySourceConfig):
    search_queries: tuple[str, ...] = ()

    def configured_values(self) -> tuple[str, ...]:
        return self.search_queries


class HackerNewsSourceConfig(QuerySourceConfig):
    terms: tuple[str, ...] = ()

    def configured_values(self) -> tuple[str, ...]:
        return self.terms


class WikipediaSourceConfig(QuerySourceConfig):
    page_titles: tuple[str, ...] = ()

    def configured_values(self) -> tuple[str, ...]:
        return self.page_titles


class SourcesDefinition(StrictModel):
    arxiv: ArxivSourceConfig | None = None
    github: GitHubSourceConfig | None = None
    hacker_news: HackerNewsSourceConfig | None = None
    wikipedia: WikipediaSourceConfig | None = None

    def items(self) -> tuple[tuple[str, QuerySourceConfig], ...]:
        configured: list[tuple[str, QuerySourceConfig]] = []
        for name in ("arxiv", "github", "hacker_news", "wikipedia"):
            value = getattr(self, name)
            if value is not None:
                configured.append((name, value))
        return tuple(configured)


class TopicDefinition(StrictModel):
    canonical_name: str = Field(min_length=1, max_length=250)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=250)
    description: str = Field(min_length=10, max_length=4000)
    category: str = Field(pattern=SLUG_PATTERN, max_length=150)
    status: TopicStatus = TopicStatus.ACTIVE
    monitoring_priority: int = Field(default=50, ge=0, le=100)
    aliases: tuple[AliasDefinition, ...] = ()
    sources: SourcesDefinition = Field(default_factory=SourcesDefinition)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AllowedAliasCollision(StrictModel):
    alias: str = Field(min_length=1, max_length=250)
    topics: tuple[str, ...] = Field(min_length=2)
    reason: str = Field(min_length=8, max_length=1000)

    @model_validator(mode="after")
    def topics_are_unique(self) -> AllowedAliasCollision:
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("allowlisted collision topics must be unique")
        return self


class RegistryFileDefinition(StrictModel):
    schema_version: Literal[1]
    categories: tuple[CategoryDefinition, ...] = ()
    topics: tuple[TopicDefinition, ...] = ()
    allowed_alias_collisions: tuple[AllowedAliasCollision, ...] = ()


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class RegistryIssue(StrictModel):
    code: str
    message: str
    severity: IssueSeverity
    source_file: str | None = None
    entity: str | None = None


class LoadedRegistry(StrictModel):
    schema_version: Literal[1] = 1
    categories: tuple[CategoryDefinition, ...]
    topics: tuple[TopicDefinition, ...]
    allowed_alias_collisions: tuple[AllowedAliasCollision, ...]
    source_files: tuple[Path, ...]
    checksum: str
    issues: tuple[RegistryIssue, ...] = ()

    @property
    def alias_count(self) -> int:
        return sum(len(topic.aliases) for topic in self.topics)

    @property
    def mapping_count(self) -> int:
        return sum(len(topic.sources.items()) for topic in self.topics)

    @property
    def warnings(self) -> tuple[RegistryIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.WARNING)
