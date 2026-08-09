import pytest

from topic_registry.normalization import (
    normalize_alias,
    normalize_canonical_name,
    normalize_whitespace,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" C ", "c"),
        ("C++", "c++"),
        ("C#", "c#"),
        (".NET", ".net"),
        ("Node.js", "node.js"),
        ("ＡＩ", "ai"),
        ("Model\t Context\nProtocol", "model context protocol"),
    ],
)
def test_alias_normalization_preserves_meaningful_punctuation(raw: str, expected: str) -> None:
    assert normalize_alias(raw) == expected


def test_case_sensitive_alias_preserves_case_after_unicode_normalization() -> None:
    assert normalize_alias("  McP  ", case_sensitive=True) == "McP"


def test_canonical_and_whitespace_normalization_are_deterministic() -> None:
    assert normalize_whitespace("  Model   Context  ") == "Model Context"
    assert normalize_canonical_name("  MODEL   Context  ") == "model context"
