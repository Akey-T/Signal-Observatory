from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivMatchMethod,
    ArxivPaper,
    ArxivTopicMatch,
)
from observatory_db.coverage_models import CoverageStatus, CoverageStrategy, TopicSourceCoverage
from observatory_db.github_models import (
    GithubDiscoveryState,
    GithubMatchMethod,
    GithubOperationStatus,
    GithubRawResponse,
    GithubRepository,
    GithubRepositoryPollState,
    GithubRepositorySnapshot,
    GithubSnapshotMethod,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import (
    IngestionRun,
    IngestionStatus,
    Source,
    Topic,
    TopicSourceMapping,
)
from observatory_operations import CoverageDeriver, CoverageQueryService
from signal_observatory_config import Settings


def test_coverage_derivation_missing_dates_and_rebuild_idempotency(
    migrated_engine: Engine,
) -> None:
    first_day = datetime(2026, 8, 11, 3, tzinfo=UTC)
    with Session(migrated_engine) as session:
        arxiv = Source(name="arxiv", kind="api", metadata_={})
        github = Source(name="github", kind="api", metadata_={})
        hacker_news = Source(name="hacker_news", kind="api", metadata_={})
        complete = Topic(
            canonical_name="Complete Research",
            normalized_name="complete research",
            slug="complete-research",
        )
        partial = Topic(
            canonical_name="Partial Research",
            normalized_name="partial research",
            slug="partial-research",
        )
        developer = Topic(
            canonical_name="Forward Developer",
            normalized_name="forward developer",
            slug="forward-developer",
        )
        empty_research = Topic(
            canonical_name="Empty Research",
            normalized_name="empty research",
            slug="empty-research",
        )
        never_initialized = Topic(
            canonical_name="Never Initialized",
            normalized_name="never initialized",
            slug="never-initialized",
        )
        empty_developer = Topic(
            canonical_name="Empty Developer",
            normalized_name="empty developer",
            slug="empty-developer",
        )
        community = Topic(
            canonical_name="Community Evidence",
            normalized_name="community evidence",
            slug="community-evidence",
        )
        session.add_all(
            [
                arxiv,
                github,
                hacker_news,
                complete,
                partial,
                developer,
                empty_research,
                never_initialized,
                empty_developer,
                community,
            ]
        )
        session.flush()
        complete_mapping = _mapping(complete, arxiv)
        partial_mapping = _mapping(partial, arxiv)
        github_mapping = _mapping(developer, github)
        empty_research_mapping = _mapping(empty_research, arxiv)
        never_initialized_mapping = _mapping(never_initialized, github)
        empty_developer_mapping = _mapping(empty_developer, github)
        session.add_all(
            [
                complete_mapping,
                partial_mapping,
                github_mapping,
                empty_research_mapping,
                never_initialized_mapping,
                empty_developer_mapping,
            ]
        )
        arxiv_run = _run(arxiv, first_day)
        github_run = _run(github, first_day)
        session.add_all([arxiv_run, github_run])
        session.flush()
        session.add(
            TopicSourceCoverage(
                topic_id=community.id,
                source_id=hacker_news.id,
                coverage_status=CoverageStatus.FORWARD_ONLY,
                coverage_strategy=CoverageStrategy.EVENT_STREAM,
                coverage_start=first_day.date(),
                coverage_end=first_day.date(),
                target_start=None,
                target_end=None,
                first_observed_at=first_day,
                last_observed_at=first_day,
                last_successful_run_at=first_day,
                observation_count=1,
                expected_observation_count=None,
                missing_observation_count=0,
                partial_reason=None,
                derived_at=first_day,
                derivation_version="hacker-news-test-v1",
                metadata_={"source_owned": True},
            )
        )

        paper = ArxivPaper(
            arxiv_id="2608.00001",
            title="Coverage facts",
            abstract="Persisted evidence.",
            published_at=datetime(2026, 8, 5, tzinfo=UTC),
            updated_at=datetime(2026, 8, 5, tzinfo=UTC),
            primary_category="cs.SE",
            abs_url="https://arxiv.org/abs/2608.00001",
            last_observed_at=first_day,
            metadata_={},
        )
        session.add(paper)
        session.flush()
        session.add_all(
            [
                ArxivCollectionCursor(
                    topic_id=complete.id,
                    source_mapping_id=complete_mapping.id,
                    cursor_key="2026-08-01/2026-08-11",
                    mode="backfill",
                    last_successful_run_at=first_day,
                    window_from=datetime(2026, 8, 1, tzinfo=UTC),
                    window_until=datetime(2026, 8, 11, tzinfo=UTC),
                    next_start=0,
                    checkpoint={},
                    status=ArxivCursorStatus.SUCCEEDED,
                ),
                ArxivCollectionCursor(
                    topic_id=partial.id,
                    source_mapping_id=partial_mapping.id,
                    cursor_key="2026-08-01/2026-08-11",
                    mode="backfill",
                    window_from=datetime(2026, 8, 1, tzinfo=UTC),
                    window_until=datetime(2026, 8, 11, tzinfo=UTC),
                    next_start=100,
                    checkpoint={"reason": "safety limit"},
                    status=ArxivCursorStatus.PARTIAL,
                    last_error="safety limit",
                ),
                ArxivCollectionCursor(
                    topic_id=empty_research.id,
                    source_mapping_id=empty_research_mapping.id,
                    cursor_key="2026-08-01/2026-08-11",
                    mode="backfill",
                    last_successful_run_at=first_day,
                    window_from=datetime(2026, 8, 1, tzinfo=UTC),
                    window_until=datetime(2026, 8, 11, tzinfo=UTC),
                    next_start=0,
                    checkpoint={"result_count": 0},
                    status=ArxivCursorStatus.SUCCEEDED,
                ),
                GithubDiscoveryState(
                    topic_id=empty_developer.id,
                    source_mapping_id=empty_developer_mapping.id,
                    status=GithubOperationStatus.SUCCEEDED,
                    last_checked_at=first_day,
                    last_successful_at=first_day,
                    last_ingestion_run_id=github_run.run_id,
                    metadata_={"result_count": 0},
                ),
                ArxivTopicMatch(
                    paper_id=paper.id,
                    topic_id=complete.id,
                    source_mapping_id=complete_mapping.id,
                    matched_query="all:coverage",
                    match_method=ArxivMatchMethod.ARXIV_API_QUERY,
                    first_matched_at=first_day,
                    last_matched_at=first_day,
                    first_ingestion_run_id=arxiv_run.run_id,
                    last_ingestion_run_id=arxiv_run.run_id,
                    metadata_={},
                ),
            ]
        )

        repository = _repository(first_day)
        session.add(repository)
        session.flush()
        raw = _github_raw(github_run, repository, first_day, suffix="one")
        session.add(raw)
        session.flush()
        session.add_all(
            [
                GithubTopicRepositoryMatch(
                    topic_id=developer.id,
                    repository_id=repository.id,
                    source_mapping_id=github_mapping.id,
                    matched_query="forward developer",
                    match_method=GithubMatchMethod.GITHUB_REPOSITORY_SEARCH,
                    discovery_rank=1,
                    first_discovered_at=first_day,
                    last_discovered_at=first_day,
                    first_ingestion_run_id=github_run.run_id,
                    last_ingestion_run_id=github_run.run_id,
                    tracking_state=GithubTrackingState.TRACKED,
                    metadata_={},
                ),
                _snapshot(repository, github_run, raw, first_day, stars=10),
                GithubRepositoryPollState(
                    repository_id=repository.id,
                    last_checked_at=first_day,
                    last_successful_at=first_day,
                    last_snapshot_at=first_day,
                    last_status=200,
                    consecutive_failures=0,
                ),
            ]
        )
        session.commit()

        first_rebuild = CoverageDeriver(session, now=first_day).rebuild()
        first_derived_at = session.scalar(
            select(TopicSourceCoverage.derived_at).where(
                TopicSourceCoverage.topic_id == complete.id
            )
        )
        second_rebuild = CoverageDeriver(
            session, now=datetime(2026, 8, 11, 4, tzinfo=UTC)
        ).rebuild()
        second_derived_at = session.scalar(
            select(TopicSourceCoverage.derived_at).where(
                TopicSourceCoverage.topic_id == complete.id
            )
        )

        assert first_rebuild["created"] == 6
        assert second_rebuild["unchanged"] == 6
        assert second_rebuild["updated"] == 0
        assert first_derived_at == second_derived_at
        states = {
            row.topic_id: row.coverage_status
            for row in session.scalars(select(TopicSourceCoverage)).all()
        }
        assert states[complete.id] == CoverageStatus.COMPLETE
        assert states[partial.id] == CoverageStatus.PARTIAL
        assert states[developer.id] == CoverageStatus.FORWARD_ONLY
        assert states[empty_research.id] == CoverageStatus.EMPTY
        assert states[never_initialized.id] == CoverageStatus.UNKNOWN
        assert states[empty_developer.id] == CoverageStatus.EMPTY
        assert states[community.id] == CoverageStatus.FORWARD_ONLY
        preserved = session.scalar(
            select(TopicSourceCoverage).where(TopicSourceCoverage.topic_id == community.id)
        )
        assert preserved is not None
        assert preserved.derivation_version == "hacker-news-test-v1"
        assert (
            session.scalar(
                select(TopicSourceCoverage.derivation_version).where(
                    TopicSourceCoverage.topic_id == complete.id
                )
            )
            == "coverage-v1"
        )

        third_day = datetime(2026, 8, 13, 3, tzinfo=UTC)
        raw_two = _github_raw(github_run, repository, third_day, suffix="two")
        session.add(raw_two)
        session.flush()
        session.add(_snapshot(repository, github_run, raw_two, third_day, stars=10))
        poll = session.scalar(
            select(GithubRepositoryPollState).where(
                GithubRepositoryPollState.repository_id == repository.id
            )
        )
        assert poll is not None
        poll.last_checked_at = third_day
        poll.last_successful_at = third_day
        poll.last_snapshot_at = third_day
        session.commit()
        CoverageDeriver(session, now=third_day).rebuild()

        developer_coverage = session.scalar(
            select(TopicSourceCoverage).where(TopicSourceCoverage.topic_id == developer.id)
        )
        assert developer_coverage is not None
        assert developer_coverage.coverage_status == CoverageStatus.FORWARD_ONLY
        assert developer_coverage.observation_count == 2
        assert developer_coverage.expected_observation_count == 3
        assert developer_coverage.missing_observation_count == 1
        assert developer_coverage.metadata_["missing_dates"] == ["2026-08-12"]

        topic_payload = CoverageQueryService(
            session,
            Settings(_env_file=None, github_token=None),
            now=third_day,
        ).topic("forward-developer")
        assert topic_payload is not None
        assert topic_payload["channels"][1]["coverage"]["coverage_status"] == "forward_only"
        assert topic_payload["channels"][2]["collection_state"] == "not_started"
        assert topic_payload["channels"][3]["coverage"] is None


def _mapping(topic: Topic, source: Source) -> TopicSourceMapping:
    return TopicSourceMapping(
        topic_id=topic.id,
        source_id=source.id,
        enabled=True,
        mapping_type="registry",
        query=topic.slug,
        configuration={},
    )


def _run(source: Source, observed_at: datetime) -> IngestionRun:
    return IngestionRun(
        source_id=source.id,
        started_at=observed_at,
        finished_at=observed_at,
        status=IngestionStatus.SUCCEEDED,
        collector_version="test",
        metadata_={},
    )


def _repository(observed_at: datetime) -> GithubRepository:
    return GithubRepository(
        github_repository_id=123,
        node_id="R_123",
        owner_login="example",
        name="coverage",
        full_name="example/coverage",
        html_url="https://github.com/example/coverage",
        api_url="https://api.github.com/repos/example/coverage",
        visibility="public",
        created_at_github=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at_github=observed_at,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        metadata_={},
    )


def _github_raw(
    run: IngestionRun,
    repository: GithubRepository,
    observed_at: datetime,
    *,
    suffix: str,
) -> GithubRawResponse:
    return GithubRawResponse(
        ingestion_run_id=run.run_id,
        repository_id=repository.id,
        endpoint_type="repository",
        raw_path=f"raw/{suffix}",
        payload_checksum=suffix.ljust(64, "0"),
        observed_at=observed_at,
        request_url_hash=suffix.ljust(64, "1"),
        http_status=200,
        response_headers={},
        request_metadata={},
    )


def _snapshot(
    repository: GithubRepository,
    run: IngestionRun,
    raw: GithubRawResponse,
    observed_at: datetime,
    *,
    stars: int,
) -> GithubRepositorySnapshot:
    return GithubRepositorySnapshot(
        repository_id=repository.id,
        observed_at=observed_at,
        observation_date=observed_at.date(),
        full_name=repository.full_name,
        stargazers_count=stars,
        forks_count=2,
        open_issues_count=1,
        subscribers_count=1,
        size_kb=10,
        archived=False,
        disabled=False,
        updated_at_github=observed_at,
        topics=[],
        ingestion_run_id=run.run_id,
        raw_response_id=raw.id,
        observation_method=GithubSnapshotMethod.FULL_200,
    )
