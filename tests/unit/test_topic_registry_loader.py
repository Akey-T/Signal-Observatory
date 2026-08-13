from pathlib import Path

import pytest
from pydantic import ValidationError

from topic_registry.checksum import registry_checksum
from topic_registry.loader import TopicRegistryLoader, TopicRegistryValidationError
from topic_registry.models import (
    AliasDefinition,
    CategoryDefinition,
    TopicDefinition,
    TopicStatus,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "topic_registry"


def issue_codes(path: Path) -> set[str]:
    with pytest.raises(TopicRegistryValidationError) as captured:
        TopicRegistryLoader(path).load()
    return {issue.code for issue in captured.value.issues}


def test_valid_registry_loads_with_counts_and_stable_checksum() -> None:
    first = TopicRegistryLoader(FIXTURES / "valid").load()
    second = TopicRegistryLoader(FIXTURES / "valid").load()
    assert first.checksum == second.checksum
    assert (len(first.categories), len(first.topics), first.alias_count, first.mapping_count) == (
        1,
        1,
        1,
        2,
    )


@pytest.mark.parametrize(
    ("fixture", "code"),
    [
        ("duplicate_slug", "DUPLICATE_TOPIC_SLUG"),
        ("alias_collision", "ALIAS_COLLISION"),
        ("invalid_source", "INVALID_SOURCE"),
        ("unknown_field", "UNKNOWN_FIELD"),
    ],
)
def test_invalid_fixtures_have_actionable_codes(fixture: str, code: str) -> None:
    assert code in issue_codes(FIXTURES / fixture)


def test_allowed_alias_collision_is_visible_as_warning(tmp_path: Path) -> None:
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
    assert [issue.code for issue in registry.warnings] == ["ALLOWED_ALIAS_COLLISION"]


def test_missing_category_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "registry.yaml").write_text(
        """schema_version: 1
categories: []
topics:
  - canonical_name: Orphan Topic
    slug: orphan-topic
    description: This topic references a category that is absent.
    category: absent
allowed_alias_collisions: []
""",
        encoding="utf-8",
    )
    assert "MISSING_CATEGORY" in issue_codes(tmp_path)


def test_shared_wikipedia_page_is_visible_as_warning(tmp_path: Path) -> None:
    (tmp_path / "registry.yaml").write_text(
        """schema_version: 1
categories: [{name: Infrastructure, slug: infrastructure}]
topics:
  - canonical_name: Edge AI
    slug: edge-ai
    description: Artificial intelligence deployed near data sources.
    category: infrastructure
    sources: {wikipedia: {page_titles: [Edge_computing]}}
  - canonical_name: Edge Computing
    slug: edge-computing
    description: Distributed computation deployed near data sources.
    category: infrastructure
    sources: {wikipedia: {page_titles: [Edge computing]}}
allowed_alias_collisions: []
""",
        encoding="utf-8",
    )

    registry = TopicRegistryLoader(tmp_path).load()

    assert [issue.code for issue in registry.warnings] == ["SHARED_WIKIPEDIA_PAGE"]
    assert registry.warnings[0].entity == "edge computing"


def test_checksum_is_independent_of_definition_order() -> None:
    categories = (
        CategoryDefinition(name="Second", slug="second"),
        CategoryDefinition(name="First", slug="first"),
    )
    topics = (
        TopicDefinition(
            canonical_name="Second Topic",
            slug="second-topic",
            description="A sufficient second topic description.",
            category="second",
            aliases=(AliasDefinition(value="S2"),),
        ),
        TopicDefinition(
            canonical_name="First Topic",
            slug="first-topic",
            description="A sufficient first topic description.",
            category="first",
        ),
    )
    assert registry_checksum(categories, topics, ()) == registry_checksum(
        tuple(reversed(categories)), tuple(reversed(topics)), ()
    )


def test_checksum_changes_when_semantic_content_changes() -> None:
    category = CategoryDefinition(name="AI", slug="ai")
    topic = TopicDefinition(
        canonical_name="Example Topic",
        slug="example-topic",
        description="A sufficient original topic description.",
        category="ai",
    )
    changed = topic.model_copy(update={"monitoring_priority": 99})
    assert registry_checksum((category,), (topic,), ()) != registry_checksum(
        (category,), (changed,), ()
    )


@pytest.mark.parametrize(
    "values",
    [
        {"canonical_name": "Bad Slug", "slug": "Bad_Slug"},
        {"canonical_name": "Low Priority", "slug": "low-priority", "monitoring_priority": -1},
        {
            "canonical_name": "High Priority",
            "slug": "high-priority",
            "monitoring_priority": 101,
        },
        {"canonical_name": "Bad Status", "slug": "bad-status", "status": "retired"},
    ],
)
def test_topic_schema_rejects_invalid_slug_priority_and_status(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TopicDefinition(
            description="A sufficient schema validation description.",
            category="ai",
            **values,
        )


def test_topic_priority_boundaries_and_status_enum_are_accepted() -> None:
    low = TopicDefinition(
        canonical_name="Disabled Topic",
        slug="disabled-topic",
        description="A sufficient disabled topic description.",
        category="ai",
        monitoring_priority=0,
        status=TopicStatus.PAUSED,
    )
    high = low.model_copy(
        update={"slug": "critical-topic", "monitoring_priority": 100, "status": TopicStatus.ACTIVE}
    )
    assert low.monitoring_priority == 0
    assert high.monitoring_priority == 100


def test_duplicate_canonical_name_and_same_topic_alias_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "registry.yaml").write_text(
        """schema_version: 1
categories: [{name: AI, slug: ai}]
topics:
  - canonical_name: Repeated Name
    slug: first-topic
    description: This first topic has duplicate aliases.
    category: ai
    aliases: [{value: Same}, {value: same}]
  - canonical_name: repeated name
    slug: second-topic
    description: This second topic repeats a canonical name.
    category: ai
allowed_alias_collisions: []
""",
        encoding="utf-8",
    )
    codes = issue_codes(tmp_path)
    assert "DUPLICATE_CANONICAL_NAME" in codes
    assert "DUPLICATE_TOPIC_ALIAS" in codes
