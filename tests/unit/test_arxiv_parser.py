from __future__ import annotations

from pathlib import Path

import pytest

from arxiv_collector import (
    ArxivAPIError,
    ArxivAtomParser,
    ArxivParseError,
    ParsedArxivFeed,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv"


def parse(name: str) -> ParsedArxivFeed:
    return ArxivAtomParser().parse((FIXTURES / name).read_bytes())


def test_parser_reads_complete_article_and_normalizes_identity() -> None:
    feed = parse("single_result.xml")
    article = feed.articles[0]

    assert (feed.total_results, feed.start_index, feed.items_per_page) == (1, 0, 1)
    assert article.arxiv_id == "2608.01234"
    assert article.latest_version == 2
    assert article.title == "A Durable Signal Observatory"
    assert article.abstract == "First line. Second line."
    assert article.authors == ("Alice Example", "Bob Researcher")
    assert article.categories == ("cs.AI", "cs.LG")
    assert article.primary_category == "cs.AI"
    assert article.doi == "10.1000/example"
    assert article.journal_ref == "Journal 42 (2026)"
    assert article.comment == "12 pages, 3 figures"
    assert article.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert article.pdf_url == "https://arxiv.org/pdf/2608.01234v2"


def test_parser_handles_multiple_legacy_ids_and_zero_results() -> None:
    multiple = parse("multiple_results.xml")
    assert [article.arxiv_id for article in multiple.articles] == [
        "2608.00001",
        "hep-ex/0307015",
    ]
    assert multiple.articles[1].latest_version == 3

    empty = parse("empty_result.xml")
    assert empty.total_results == 0
    assert empty.articles == ()


def test_parser_accepts_missing_optional_fields() -> None:
    article = parse("missing_optional_fields.xml").articles[0]
    assert article.latest_version is None
    assert article.comment is None
    assert article.journal_ref is None
    assert article.doi is None
    assert article.license_url is None
    assert article.pdf_url is None


def test_parser_reads_pagination_and_updated_article() -> None:
    first = parse("pagination_page_1.xml")
    second = parse("pagination_page_2.xml")
    updated = parse("updated_article.xml").articles[0]
    assert (first.start_index, first.total_results) == (0, 2)
    assert (second.start_index, second.total_results) == (1, 2)
    assert updated.arxiv_id == "2608.01234"
    assert updated.latest_version == 3
    assert updated.title.endswith("revised")


@pytest.mark.parametrize("fixture", ["malformed.xml", "api_error.xml"])
def test_parser_rejects_malformed_and_api_error_feeds(fixture: str) -> None:
    expected = ArxivAPIError if fixture == "api_error.xml" else ArxivParseError
    with pytest.raises(expected):
        parse(fixture)


def test_parser_rejects_entity_declarations() -> None:
    payload = b'<!DOCTYPE feed [<!ENTITY x "unsafe">]><feed>&x;</feed>'
    with pytest.raises(ArxivParseError, match="entity"):
        ArxivAtomParser().parse(payload)
