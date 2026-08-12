"""Idempotent Silver persistence with explicit Raw and Registry lineage."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from arxiv_collector.models import (
    ArxivHTTPResponse,
    ParsedArxivArticle,
    ParsedArxivFeed,
    PersistenceCounts,
)
from collector_core import LocalRawStore, RawRecord
from observatory_db.arxiv_models import (
    ArxivAuthor,
    ArxivCategory,
    ArxivMatchMethod,
    ArxivPaper,
    ArxivPaperAuthor,
    ArxivPaperCategory,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.models import IngestionRun, Topic, TopicSourceMapping


def normalize_author_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())


class ArxivPersistence:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_raw_response(
        self,
        *,
        run: IngestionRun,
        topic: Topic,
        mapping: TopicSourceMapping,
        raw: RawRecord,
        response: ArxivHTTPResponse,
        request_metadata: Mapping[str, Any],
    ) -> ArxivRawResponse:
        raw_path = LocalRawStore(raw.directory.parents[4]).logical_key(
            raw.directory, source=raw.source
        )
        existing = self.session.scalar(
            select(ArxivRawResponse).where(ArxivRawResponse.raw_path == raw_path)
        )
        if existing is not None:
            return existing
        record = ArxivRawResponse(
            ingestion_run_id=run.run_id,
            topic_id=topic.id,
            source_mapping_id=mapping.id,
            raw_path=raw_path,
            payload_checksum=raw.sha256,
            observed_at=response.requested_at,
            query=response.request.search_query,
            start_index=response.request.start,
            max_results=response.request.max_results,
            sort_by=response.request.sort_by,
            sort_order=response.request.sort_order,
            http_status=response.status_code,
            response_headers=dict(response.headers),
            request_metadata=dict(request_metadata),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def record_parse_error(self, raw_response: ArxivRawResponse, error: BaseException) -> None:
        raw_response.parse_error = f"{type(error).__name__}: {error}"
        raw_response.parsed_entry_count = 0
        self.session.flush()

    def persist_feed(
        self,
        *,
        feed: ParsedArxivFeed,
        raw_response: ArxivRawResponse,
        run: IngestionRun,
        topic: Topic,
        mapping: TopicSourceMapping,
        matched_query: str,
    ) -> PersistenceCounts:
        raw_response.parsed_entry_count = len(feed.articles)
        raw_response.parse_error = None
        counts = PersistenceCounts()
        seen: set[str] = set()
        for article in feed.articles:
            if article.arxiv_id in seen:
                counts = counts.add(PersistenceCounts(duplicate_papers=1))
                continue
            seen.add(article.arxiv_id)
            paper, state = self._upsert_paper(article, raw_response.observed_at)
            if state == "inserted":
                counts = counts.add(PersistenceCounts(papers_inserted=1))
            elif state == "updated":
                counts = counts.add(PersistenceCounts(papers_updated=1))
            else:
                counts = counts.add(PersistenceCounts(papers_existing=1))
            if state != "existing":
                self._reconcile_authors(paper, article.authors)
                self._reconcile_categories(paper, article.categories, article.primary_category)
            self._record_observation(paper, article, raw_response, run)
            if self._upsert_match(
                paper=paper,
                topic=topic,
                mapping=mapping,
                matched_query=matched_query,
                run=run,
                raw_response=raw_response,
            ):
                counts = counts.add(PersistenceCounts(topic_matches_added=1))
        self.session.flush()
        return counts

    def _upsert_paper(
        self, article: ParsedArxivArticle, observed_at: datetime
    ) -> tuple[ArxivPaper, str]:
        paper = self.session.scalar(
            select(ArxivPaper)
            .where(ArxivPaper.arxiv_id == article.arxiv_id)
            .options(
                selectinload(ArxivPaper.authors).selectinload(ArxivPaperAuthor.author),
                selectinload(ArxivPaper.categories).selectinload(ArxivPaperCategory.category),
            )
        )
        values = self._paper_values(article)
        if paper is None:
            paper = ArxivPaper(**values, last_observed_at=observed_at)
            self.session.add(paper)
            self.session.flush()
            return paper, "inserted"

        paper.last_observed_at = max(paper.last_observed_at, observed_at)
        if article.updated_at < paper.updated_at:
            return paper, "existing"
        changed = any(getattr(paper, field) != value for field, value in values.items())
        if not changed:
            return paper, "existing"
        for field, value in values.items():
            setattr(paper, field, value)
        self.session.flush()
        return paper, "updated"

    @staticmethod
    def _paper_values(article: ParsedArxivArticle) -> dict[str, Any]:
        return {
            "arxiv_id": article.arxiv_id,
            "latest_version": article.latest_version,
            "title": article.title,
            "abstract": article.abstract,
            "published_at": article.published_at,
            "updated_at": article.updated_at,
            "primary_category": article.primary_category,
            "comment": article.comment,
            "journal_ref": article.journal_ref,
            "doi": article.doi,
            "license_url": article.license_url,
            "abs_url": article.abs_url,
            "pdf_url": article.pdf_url,
            "is_withdrawn": article.is_withdrawn,
            "metadata_": dict(article.metadata),
        }

    def _reconcile_authors(self, paper: ArxivPaper, authors: tuple[str, ...]) -> None:
        existing_by_position = {relation.position: relation for relation in paper.authors}
        desired: list[ArxivPaperAuthor] = []
        for position, display_name in enumerate(authors):
            normalized = normalize_author_name(display_name)
            relation = existing_by_position.get(position)
            if (
                relation is not None
                and relation.author.display_name == display_name
                and relation.author.normalized_name == normalized
            ):
                desired.append(relation)
                continue
            author = ArxivAuthor(display_name=display_name, normalized_name=normalized)
            self.session.add(author)
            desired.append(ArxivPaperAuthor(position=position, author=author))
        paper.authors = desired
        self.session.flush()

    def _reconcile_categories(
        self,
        paper: ArxivPaper,
        categories: tuple[str, ...],
        primary_category: str,
    ) -> None:
        existing = {
            category.code: category
            for category in self.session.scalars(
                select(ArxivCategory).where(ArxivCategory.code.in_(categories))
            ).all()
        }
        existing_relations = {relation.category.code: relation for relation in paper.categories}
        desired_codes = set(categories)
        for code in categories:
            category = existing.get(code)
            if category is None:
                category = ArxivCategory(code=code)
                self.session.add(category)
                existing[code] = category
            relation = existing_relations.get(code)
            if relation is None:
                relation = ArxivPaperCategory(
                    paper=paper,
                    category=category,
                    is_primary=code == primary_category,
                )
                self.session.add(relation)
            else:
                relation.is_primary = code == primary_category
        for code, relation in existing_relations.items():
            if code not in desired_codes:
                paper.categories.remove(relation)
        self.session.flush()

    def _record_observation(
        self,
        paper: ArxivPaper,
        article: ParsedArxivArticle,
        raw_response: ArxivRawResponse,
        run: IngestionRun,
    ) -> None:
        existing = self.session.scalar(
            select(ArxivPaperObservation).where(
                ArxivPaperObservation.paper_id == paper.id,
                ArxivPaperObservation.raw_response_id == raw_response.id,
            )
        )
        if existing is not None:
            return
        self.session.add(
            ArxivPaperObservation(
                paper_id=paper.id,
                raw_response_id=raw_response.id,
                ingestion_run_id=run.run_id,
                observed_at=raw_response.observed_at,
                arxiv_version=article.latest_version,
                normalized_metadata=article.model_dump(mode="json"),
            )
        )

    def _upsert_match(
        self,
        *,
        paper: ArxivPaper,
        topic: Topic,
        mapping: TopicSourceMapping,
        matched_query: str,
        run: IngestionRun,
        raw_response: ArxivRawResponse,
    ) -> bool:
        match = self.session.scalar(
            select(ArxivTopicMatch).where(
                ArxivTopicMatch.paper_id == paper.id,
                ArxivTopicMatch.topic_id == topic.id,
                ArxivTopicMatch.source_mapping_id == mapping.id,
                ArxivTopicMatch.matched_query == matched_query,
            )
        )
        if match is None:
            self.session.add(
                ArxivTopicMatch(
                    paper_id=paper.id,
                    topic_id=topic.id,
                    source_mapping_id=mapping.id,
                    matched_query=matched_query,
                    match_method=ArxivMatchMethod.ARXIV_API_QUERY,
                    first_matched_at=raw_response.observed_at,
                    last_matched_at=raw_response.observed_at,
                    first_ingestion_run_id=run.run_id,
                    last_ingestion_run_id=run.run_id,
                    metadata_={
                        "latest_raw_response_id": str(raw_response.id),
                        "latest_raw_path": raw_response.raw_path,
                    },
                )
            )
            return True
        match.last_matched_at = max(match.last_matched_at, raw_response.observed_at)
        match.last_ingestion_run_id = run.run_id
        match.metadata_ = {
            **match.metadata_,
            "latest_raw_response_id": str(raw_response.id),
            "latest_raw_path": raw_response.raw_path,
        }
        return False
