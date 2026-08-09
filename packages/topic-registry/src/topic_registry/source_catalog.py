"""Finite E02 source catalog; no network access or collector behavior lives here."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceSpec:
    name: str
    kind: str
    base_url: str


SOURCE_CATALOG: dict[str, SourceSpec] = {
    "arxiv": SourceSpec("arxiv", "api", "https://export.arxiv.org/api"),
    "github": SourceSpec("github", "api", "https://api.github.com"),
    "hacker_news": SourceSpec("hacker_news", "api", "https://hacker-news.firebaseio.com"),
    "wikipedia": SourceSpec("wikipedia", "api", "https://en.wikipedia.org/w/api.php"),
}
