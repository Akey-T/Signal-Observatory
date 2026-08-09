"""Conservative Topic and Alias normalization."""

from __future__ import annotations

import unicodedata


def normalize_whitespace(value: str) -> str:
    """Apply Unicode NFKC and collapse whitespace without changing punctuation."""

    normalized = unicodedata.normalize("NFKC", value).strip()
    return " ".join(normalized.split())


def normalize_alias(value: str, *, case_sensitive: bool = False) -> str:
    """Normalize an alias for matching while preserving meaningful punctuation."""

    normalized = normalize_whitespace(value)
    return normalized if case_sensitive else normalized.casefold()


def normalize_canonical_name(value: str) -> str:
    return normalize_whitespace(value).casefold()
