"""Namespace-aware, defensive parser for official arXiv Atom metadata."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import urlparse

from arxiv_collector.models import ParsedArxivArticle, ParsedArxivFeed

ATOM = "http://www.w3.org/2005/Atom"
OPEN_SEARCH = "http://a9.com/-/spec/opensearch/1.1/"
ARXIV = "http://arxiv.org/schemas/atom"
NS = {"atom": ATOM, "opensearch": OPEN_SEARCH, "arxiv": ARXIV}
VERSION_SUFFIX = re.compile(r"v(?P<version>[1-9][0-9]*)$")


class ArxivParseError(ValueError):
    """Raised when an Atom response is unsafe, malformed, or structurally invalid."""


class ArxivAPIError(ArxivParseError):
    """Raised for a valid Atom error feed returned by the arXiv API."""


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split())


class ArxivAtomParser:
    def parse(self, payload: bytes) -> ParsedArxivFeed:
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise ArxivParseError("DTD and entity declarations are not accepted")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise ArxivParseError(f"malformed arXiv Atom XML: {error}") from error
        if root.tag != f"{{{ATOM}}}feed":
            raise ArxivParseError("arXiv response root must be an Atom feed")

        entries = root.findall("atom:entry", NS)
        if len(entries) == 1 and self._is_error_entry(entries[0]):
            title = normalize_text(entries[0].findtext("atom:title", namespaces=NS))
            summary = normalize_text(entries[0].findtext("atom:summary", namespaces=NS))
            raise ArxivAPIError(f"{title}: {summary}".strip(": "))

        total_results = self._required_int(root, "opensearch:totalResults")
        start_index = self._required_int(root, "opensearch:startIndex")
        items_per_page = self._required_int(root, "opensearch:itemsPerPage")
        articles = tuple(self._article(entry) for entry in entries)
        if items_per_page < len(articles):
            raise ArxivParseError("itemsPerPage cannot be smaller than returned entry count")
        feed_updated = self._optional_datetime(root.findtext("atom:updated", namespaces=NS))
        return ParsedArxivFeed(
            total_results=total_results,
            start_index=start_index,
            items_per_page=items_per_page,
            articles=articles,
            feed_id=self._optional_text(root.findtext("atom:id", namespaces=NS)),
            feed_updated_at=feed_updated,
        )

    def _article(self, entry: ET.Element) -> ParsedArxivArticle:
        entry_id = self._required_text(entry.findtext("atom:id", namespaces=NS), "entry id")
        canonical_id, version = self.canonical_identifier(entry_id)
        title = self._required_text(entry.findtext("atom:title", namespaces=NS), "title")
        abstract = self._required_text(entry.findtext("atom:summary", namespaces=NS), "summary")
        published = self._required_datetime(entry.findtext("atom:published", namespaces=NS))
        updated = self._required_datetime(entry.findtext("atom:updated", namespaces=NS))
        authors = tuple(
            self._required_text(author.findtext("atom:name", namespaces=NS), "author name")
            for author in entry.findall("atom:author", NS)
        )
        categories = tuple(
            term
            for category in entry.findall("atom:category", NS)
            if (term := normalize_text(category.attrib.get("term")))
        )
        primary_element = entry.find("arxiv:primary_category", NS)
        primary = (
            normalize_text(primary_element.attrib.get("term"))
            if primary_element is not None
            else ""
        )
        if not primary:
            raise ArxivParseError(f"paper {canonical_id} is missing primary category")
        if primary not in categories:
            categories = (primary, *categories)

        abs_url = entry_id
        pdf_url: str | None = None
        license_url: str | None = None
        for link in entry.findall("atom:link", NS):
            href = normalize_text(link.attrib.get("href"))
            if not href:
                continue
            rel = link.attrib.get("rel")
            media_type = link.attrib.get("type")
            title_attribute = link.attrib.get("title")
            if rel == "alternate" and media_type == "text/html":
                abs_url = href
            elif title_attribute == "pdf" or media_type == "application/pdf":
                pdf_url = href
            elif rel == "license":
                license_url = href
        arxiv_license = self._optional_text(entry.findtext("arxiv:license", namespaces=NS))
        license_url = license_url or arxiv_license
        withdrawal_text = f"{title} {abstract}".casefold()
        return ParsedArxivArticle(
            arxiv_id=canonical_id,
            latest_version=version,
            title=title,
            abstract=abstract,
            published_at=published,
            updated_at=updated,
            authors=authors,
            categories=tuple(dict.fromkeys(categories)),
            primary_category=primary,
            comment=self._optional_text(entry.findtext("arxiv:comment", namespaces=NS)),
            journal_ref=self._optional_text(entry.findtext("arxiv:journal_ref", namespaces=NS)),
            doi=self._optional_text(entry.findtext("arxiv:doi", namespaces=NS)),
            license_url=license_url,
            abs_url=abs_url,
            pdf_url=pdf_url,
            is_withdrawn="withdrawn" in withdrawal_text,
            metadata={"entry_id": entry_id},
        )

    @staticmethod
    def canonical_identifier(value: str) -> tuple[str, int | None]:
        parsed = urlparse(value)
        identifier = parsed.path.split("/abs/", maxsplit=1)[-1] if "/abs/" in parsed.path else value
        identifier = identifier.strip().strip("/")
        if not identifier:
            raise ArxivParseError("article identifier is empty")
        match = VERSION_SUFFIX.search(identifier)
        version = int(match.group("version")) if match else None
        canonical = identifier[: match.start()] if match else identifier
        return canonical, version

    @staticmethod
    def _is_error_entry(entry: ET.Element) -> bool:
        entry_id = normalize_text(entry.findtext("atom:id", namespaces=NS)).casefold()
        title = normalize_text(entry.findtext("atom:title", namespaces=NS)).casefold()
        return "/api/errors" in entry_id or title == "error"

    @staticmethod
    def _required_int(root: ET.Element, path: str) -> int:
        value = normalize_text(root.findtext(path, namespaces=NS))
        try:
            return int(value)
        except ValueError as error:
            raise ArxivParseError(f"missing or invalid {path}") from error

    @staticmethod
    def _required_text(value: str | None, field: str) -> str:
        normalized = normalize_text(value)
        if not normalized:
            raise ArxivParseError(f"arXiv entry is missing {field}")
        return normalized

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        normalized = normalize_text(value)
        return normalized or None

    @staticmethod
    def _required_datetime(value: str | None) -> datetime:
        parsed = ArxivAtomParser._optional_datetime(value)
        if parsed is None:
            raise ArxivParseError("arXiv entry has a missing timestamp")
        return parsed

    @staticmethod
    def _optional_datetime(value: str | None) -> datetime | None:
        normalized = normalize_text(value)
        if not normalized:
            return None
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as error:
            raise ArxivParseError(f"invalid arXiv timestamp: {normalized}") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ArxivParseError("arXiv timestamp must include a timezone")
        return parsed.astimezone(UTC)
