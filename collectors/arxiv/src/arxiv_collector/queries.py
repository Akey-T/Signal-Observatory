"""Read-only operator queries over persisted arXiv collection state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from observatory_db.arxiv_models import (
    ArxivAuthor,
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivPaper,
    ArxivPaperAuthor,
    ArxivPaperCategory,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.base import utc_now
from observatory_db.models import (
    IngestionRun,
    IngestionStatus,
    Source,
    Topic,
    TopicSourceMapping,
    TopicStatus,
)


class ArxivQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def status(self) -> dict[str, Any]:
        source = self.session.scalar(select(Source).where(Source.name == "arxiv"))
        mapping_filter = (
            Source.name == "arxiv",
            TopicSourceMapping.enabled.is_(True),
            Topic.status == TopicStatus.ACTIVE,
        )
        tracked_mappings = self.session.scalar(
            select(func.count())
            .select_from(TopicSourceMapping)
            .join(TopicSourceMapping.source)
            .join(TopicSourceMapping.topic)
            .where(*mapping_filter)
        )
        tracked_topics = self.session.scalar(
            select(func.count(func.distinct(TopicSourceMapping.topic_id)))
            .select_from(TopicSourceMapping)
            .join(TopicSourceMapping.source)
            .join(TopicSourceMapping.topic)
            .where(*mapping_filter)
        )
        latest = None
        latest_successful = None
        if source is not None:
            latest = self.session.scalar(
                select(IngestionRun)
                .where(IngestionRun.source_id == source.id)
                .order_by(IngestionRun.started_at.desc())
                .limit(1)
            )
            latest_successful = self.session.scalar(
                select(IngestionRun)
                .where(
                    IngestionRun.source_id == source.id,
                    IngestionRun.status == IngestionStatus.SUCCEEDED,
                )
                .order_by(IngestionRun.finished_at.desc())
                .limit(1)
            )
        if latest is None:
            collector_state = "not_initialized"
        elif latest.status is IngestionStatus.SUCCEEDED:
            collector_state = "healthy"
        else:
            collector_state = "degraded"
        paper_count = self.session.scalar(select(func.count()).select_from(ArxivPaper))
        new_since = utc_now() - timedelta(hours=24)
        new_count = self.session.scalar(
            select(func.count()).select_from(ArxivPaper).where(ArxivPaper.created_at >= new_since)
        )
        return {
            "source": "arxiv",
            "enabled": bool(source and source.is_active and int(tracked_mappings or 0) > 0),
            "collector_state": collector_state,
            "last_run_at": latest.started_at if latest else None,
            "last_successful_run_at": (
                latest_successful.finished_at if latest_successful else None
            ),
            "last_run_status": latest.status.value if latest else None,
            "tracked_topics": int(tracked_topics or 0),
            "tracked_mappings": int(tracked_mappings or 0),
            "papers_observed": int(paper_count or 0),
            "last_24h_new_papers": int(new_count or 0),
            "error_count_last_run": latest.error_count if latest else 0,
        }

    def sample(self, topic_slug: str, *, limit: int) -> list[dict[str, Any]]:
        if limit < 1 or limit > 100:
            raise ValueError("sample limit must be between 1 and 100")
        rows = self.session.execute(
            select(ArxivTopicMatch, ArxivPaper)
            .join(ArxivTopicMatch.paper)
            .join(Topic, Topic.id == ArxivTopicMatch.topic_id)
            .where(Topic.slug == topic_slug)
            .options(
                selectinload(ArxivTopicMatch.paper)
                .selectinload(ArxivPaper.authors)
                .selectinload(ArxivPaperAuthor.author)
            )
            .order_by(ArxivPaper.published_at.desc(), ArxivPaper.arxiv_id)
            .limit(limit)
        ).all()
        samples: list[dict[str, Any]] = []
        for match, paper in rows:
            latest_observation = self.session.scalar(
                select(ArxivPaperObservation)
                .where(ArxivPaperObservation.paper_id == paper.id)
                .options(selectinload(ArxivPaperObservation.raw_response))
                .order_by(ArxivPaperObservation.observed_at.desc())
                .limit(1)
            )
            raw: ArxivRawResponse | None = (
                latest_observation.raw_response if latest_observation else None
            )
            samples.append(
                {
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    "authors": [relation.author.display_name for relation in paper.authors],
                    "abstract_preview": paper.abstract[:500],
                    "published_at": paper.published_at,
                    "matched_query": match.matched_query,
                    "topic_slug": topic_slug,
                    "source_mapping_id": str(match.source_mapping_id),
                    "last_ingestion_run_id": str(match.last_ingestion_run_id),
                    "raw_path": raw.raw_path if raw else None,
                    "raw_checksum": raw.payload_checksum if raw else None,
                }
            )
        return samples

    def topic_exists(self, topic_slug: str) -> bool:
        return self.session.scalar(select(Topic.id).where(Topic.slug == topic_slug)) is not None

    def research(
        self,
        topic_slug: str,
        *,
        limit: int = 5,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        if limit < 1 or limit > 10:
            raise ValueError("latest research limit must be between 1 and 10")
        topic = self.session.scalar(select(Topic).where(Topic.slug == topic_slug))
        if topic is None:
            return None
        mapping = self.session.scalar(
            select(TopicSourceMapping)
            .join(TopicSourceMapping.source)
            .where(
                TopicSourceMapping.topic_id == topic.id,
                Source.name == "arxiv",
                TopicSourceMapping.enabled.is_(True),
            )
            .options(selectinload(TopicSourceMapping.source))
        )
        empty_summary = {
            "papers_total": 0,
            "papers_7d": 0,
            "papers_30d": 0,
            "unique_authors_30d": 0,
        }
        if mapping is None:
            return {
                "topic": {"slug": topic.slug, "canonical_name": topic.canonical_name},
                "source": "arxiv",
                "state": "not_configured",
                "last_observed_at": None,
                "collector_error": None,
                "summary": empty_summary,
                "latest_papers": [],
            }

        latest_cursor = self.session.scalar(
            select(ArxivCollectionCursor)
            .where(ArxivCollectionCursor.source_mapping_id == mapping.id)
            .order_by(ArxivCollectionCursor.updated_at.desc())
            .limit(1)
        )
        successful_cursor = self.session.scalar(
            select(ArxivCollectionCursor)
            .where(
                ArxivCollectionCursor.source_mapping_id == mapping.id,
                ArxivCollectionCursor.status == ArxivCursorStatus.SUCCEEDED,
            )
            .order_by(ArxivCollectionCursor.last_successful_run_at.desc())
            .limit(1)
        )
        if latest_cursor is None:
            state = "not_initialized"
        elif latest_cursor.status in {ArxivCursorStatus.FAILED, ArxivCursorStatus.PARTIAL}:
            state = "degraded"
        elif successful_cursor is not None:
            state = "live"
        else:
            state = "not_initialized"

        reference_time = now or utc_now()
        paper_ids = (
            select(ArxivTopicMatch.paper_id)
            .where(ArxivTopicMatch.topic_id == topic.id)
            .scalar_subquery()
        )
        papers_total = self.session.scalar(
            select(func.count(func.distinct(ArxivPaper.id))).where(ArxivPaper.id.in_(paper_ids))
        )
        seven_days = reference_time - timedelta(days=7)
        thirty_days = reference_time - timedelta(days=30)
        papers_7d = self.session.scalar(
            select(func.count(func.distinct(ArxivPaper.id))).where(
                ArxivPaper.id.in_(paper_ids), ArxivPaper.published_at >= seven_days
            )
        )
        papers_30d = self.session.scalar(
            select(func.count(func.distinct(ArxivPaper.id))).where(
                ArxivPaper.id.in_(paper_ids), ArxivPaper.published_at >= thirty_days
            )
        )
        unique_authors_30d = self.session.scalar(
            select(func.count(func.distinct(ArxivAuthor.normalized_name)))
            .select_from(ArxivPaperAuthor)
            .join(ArxivAuthor, ArxivAuthor.id == ArxivPaperAuthor.author_id)
            .join(ArxivPaper, ArxivPaper.id == ArxivPaperAuthor.paper_id)
            .where(
                ArxivPaper.id.in_(paper_ids),
                ArxivPaper.published_at >= thirty_days,
            )
        )
        last_observed = self.session.scalar(
            select(func.max(ArxivTopicMatch.last_matched_at)).where(
                ArxivTopicMatch.topic_id == topic.id
            )
        )
        papers = self.session.scalars(
            select(ArxivPaper)
            .where(ArxivPaper.id.in_(paper_ids))
            .options(
                selectinload(ArxivPaper.authors).selectinload(ArxivPaperAuthor.author),
                selectinload(ArxivPaper.categories).selectinload(ArxivPaperCategory.category),
            )
            .order_by(ArxivPaper.published_at.desc(), ArxivPaper.arxiv_id)
            .limit(limit)
        ).all()
        latest_papers = [self._research_paper(topic.id, paper) for paper in papers]
        return {
            "topic": {"slug": topic.slug, "canonical_name": topic.canonical_name},
            "source": "arxiv",
            "state": state,
            "last_observed_at": last_observed,
            "collector_error": (
                latest_cursor.last_error
                if latest_cursor is not None
                and latest_cursor.status in {ArxivCursorStatus.FAILED, ArxivCursorStatus.PARTIAL}
                else None
            ),
            "summary": {
                "papers_total": int(papers_total or 0),
                "papers_7d": int(papers_7d or 0),
                "papers_30d": int(papers_30d or 0),
                "unique_authors_30d": int(unique_authors_30d or 0),
            },
            "latest_papers": latest_papers,
        }

    def _research_paper(self, topic_id: UUID, paper: ArxivPaper) -> dict[str, Any]:
        match = self.session.scalar(
            select(ArxivTopicMatch)
            .where(
                ArxivTopicMatch.topic_id == topic_id,
                ArxivTopicMatch.paper_id == paper.id,
            )
            .order_by(ArxivTopicMatch.last_matched_at.desc())
            .limit(1)
        )
        assert match is not None
        latest_observation = self.session.scalar(
            select(ArxivPaperObservation)
            .where(ArxivPaperObservation.paper_id == paper.id)
            .options(selectinload(ArxivPaperObservation.raw_response))
            .order_by(ArxivPaperObservation.observed_at.desc())
            .limit(1)
        )
        raw = latest_observation.raw_response if latest_observation else None
        return {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": [relation.author.display_name for relation in paper.authors],
            "published_at": paper.published_at,
            "updated_at": paper.updated_at,
            "primary_category": paper.primary_category,
            "categories": [relation.category.code for relation in paper.categories],
            "abstract": paper.abstract,
            "abs_url": paper.abs_url,
            "matched_query": match.matched_query,
            "source_mapping_id": str(match.source_mapping_id),
            "ingestion_run_id": str(match.last_ingestion_run_id),
            "raw_checksum": raw.payload_checksum if raw else None,
        }
