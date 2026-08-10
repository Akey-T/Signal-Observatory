from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from arxiv_collector import ArxivAtomParser, ArxivPersistence, ArxivRequest
from arxiv_collector.models import ArxivHTTPResponse, PersistenceCounts
from collector_core import LocalRawStore
from observatory_db.arxiv_models import (
    ArxivAuthor,
    ArxivPaper,
    ArxivPaperAuthor,
    ArxivPaperCategory,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.models import IngestionRun, Source, Topic, TopicSourceMapping
from observatory_db.repositories import IngestionRunRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv"


def configured_mapping(
    session: Session, source: Source, *, slug: str
) -> tuple[Topic, TopicSourceMapping]:
    topic = Topic(
        canonical_name=slug.replace("-", " ").title(),
        normalized_name=slug.replace("-", " "),
        slug=slug,
    )
    mapping = TopicSourceMapping(
        topic=topic,
        source=source,
        enabled=True,
        mapping_type="registry",
        query="model context protocol",
        configuration={"search_terms": ["model context protocol"]},
    )
    session.add_all([topic, mapping])
    session.flush()
    return topic, mapping


def persist_fixture(
    session: Session,
    tmp_path: Path,
    *,
    source: Source,
    topic: Topic,
    mapping: TopicSourceMapping,
    fixture: str,
    observed_at: datetime,
) -> tuple[IngestionRun, ArxivRawResponse, PersistenceCounts]:
    payload = (FIXTURES / fixture).read_bytes()
    run = IngestionRunRepository(session).start(
        source=source, collector_version="0.1.0", metadata={"mode": "backfill"}
    )
    request = ArxivRequest(search_query='all:"model context protocol"')
    response = ArxivHTTPResponse(
        request=request,
        status_code=200,
        headers={"content-type": "application/atom+xml"},
        body=payload,
        requested_at=observed_at,
        duration_ms=10,
        attempt=1,
    )
    raw = LocalRawStore(tmp_path).write(
        source="arxiv",
        payload=payload,
        request_timestamp=observed_at,
        collector_version="0.1.0",
        schema_version="1",
        source_metadata={"query": request.search_query},
    )
    persistence = ArxivPersistence(session)
    raw_response = persistence.record_raw_response(
        run=run,
        topic=topic,
        mapping=mapping,
        raw=raw,
        response=response,
        request_metadata={"fixture": fixture},
    )
    feed = ArxivAtomParser().parse(payload)
    counts = persistence.persist_feed(
        feed=feed,
        raw_response=raw_response,
        run=run,
        topic=topic,
        mapping=mapping,
        matched_query='all:"model context protocol"',
    )
    session.flush()
    return run, raw_response, counts


def count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_persistence_is_idempotent_and_updates_current_paper(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    with Session(migrated_engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        session.add(source)
        session.flush()
        topic, mapping = configured_mapping(session, source, slug="model-context-protocol")
        first_at = datetime(2026, 8, 10, 1, tzinfo=UTC)

        _run, _raw, first = persist_fixture(
            session,
            tmp_path,
            source=source,
            topic=topic,
            mapping=mapping,
            fixture="single_result.xml",
            observed_at=first_at,
        )
        _run, _raw, second = persist_fixture(
            session,
            tmp_path,
            source=source,
            topic=topic,
            mapping=mapping,
            fixture="single_result.xml",
            observed_at=first_at + timedelta(minutes=1),
        )

        assert first.papers_inserted == 1
        assert first.topic_matches_added == 1
        assert second.papers_existing == 1
        assert second.topic_matches_added == 0
        assert count(session, ArxivPaper) == 1
        assert count(session, ArxivPaperAuthor) == 2
        assert count(session, ArxivPaperCategory) == 2
        assert count(session, ArxivTopicMatch) == 1
        assert count(session, ArxivPaperObservation) == 2
        assert count(session, ArxivRawResponse) == 2

        _run, _raw, updated = persist_fixture(
            session,
            tmp_path,
            source=source,
            topic=topic,
            mapping=mapping,
            fixture="updated_article.xml",
            observed_at=first_at + timedelta(minutes=2),
        )
        paper = session.scalar(select(ArxivPaper))
        assert paper is not None
        assert updated.papers_updated == 1
        assert paper.latest_version == 3
        assert paper.title.endswith("revised")
        assert count(session, ArxivPaperAuthor) == 1
        assert count(session, ArxivPaperCategory) == 2
        assert count(session, ArxivAuthor) == 2


def test_same_paper_can_match_two_topics_with_complete_provenance(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    with Session(migrated_engine) as session:
        source = Source(name="arxiv", kind="api", metadata_={})
        session.add(source)
        session.flush()
        first_topic, first_mapping = configured_mapping(session, source, slug="first-topic")
        second_topic, second_mapping = configured_mapping(session, source, slug="second-topic")
        observed = datetime(2026, 8, 10, tzinfo=UTC)
        first_run, first_raw, _counts = persist_fixture(
            session,
            tmp_path,
            source=source,
            topic=first_topic,
            mapping=first_mapping,
            fixture="single_result.xml",
            observed_at=observed,
        )
        persist_fixture(
            session,
            tmp_path,
            source=source,
            topic=second_topic,
            mapping=second_mapping,
            fixture="single_result.xml",
            observed_at=observed + timedelta(seconds=1),
        )

        paper = session.scalar(select(ArxivPaper))
        assert paper is not None
        matches = session.scalars(select(ArxivTopicMatch)).all()
        observation = session.scalar(
            select(ArxivPaperObservation).where(
                ArxivPaperObservation.raw_response_id == first_raw.id
            )
        )
        assert len(matches) == 2
        assert {match.topic_id for match in matches} == {first_topic.id, second_topic.id}
        assert observation is not None
        assert observation.paper_id == paper.id
        assert observation.ingestion_run_id == first_run.run_id
        assert first_raw.raw_path.endswith(first_raw.payload_checksum)
        assert first_raw.source_mapping_id == first_mapping.id
