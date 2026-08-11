from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from collector_core import LocalRawStore
from github_collector import (
    GithubHTTPResponse,
    GithubJsonParser,
    GithubPersistence,
    GithubRateLimit,
    GithubRequest,
)
from observatory_db.github_models import (
    GithubRawResponse,
    GithubRepository,
    GithubRepositoryPollState,
    GithubRepositorySnapshot,
    GithubSnapshotMethod,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import IngestionRun, Source, Topic, TopicSourceMapping
from observatory_db.repositories import IngestionRunRepository

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"


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
        configuration={"search_queries": ["model context protocol"]},
    )
    session.add_all([topic, mapping])
    session.flush()
    return topic, mapping


def raw_response(
    session: Session,
    tmp_path: Path,
    *,
    source: Source,
    observed_at: datetime,
    payload: bytes,
    status: int = 200,
    etag: str = '"repo-v1"',
    mapping: TopicSourceMapping | None = None,
    repository: GithubRepository | None = None,
) -> tuple[IngestionRun, GithubRawResponse]:
    run = IngestionRunRepository(session).start(
        source=source, collector_version="0.1.0", metadata={"mode": "snapshot"}
    )
    request = GithubRequest(
        endpoint_type="repository",
        url="https://api.github.com/repos/modelcontextprotocol/servers",
        github_repository_id=1001,
        etag=etag if status == 304 else None,
    )
    response = GithubHTTPResponse(
        request=request,
        status_code=status,
        headers={"ETag": etag, "X-RateLimit-Remaining": "4999"},
        payload=payload,
        requested_at=observed_at,
        final_url=request.url,
        rate_limit=GithubRateLimit(resource="core", limit=5000, remaining=4999),
        attempts=1,
    )
    raw = LocalRawStore(tmp_path).write(
        source="github",
        payload=payload,
        request_timestamp=observed_at,
        collector_version="0.1.0",
        schema_version="1",
        source_metadata={"endpoint_type": "repository"},
    )
    indexed = GithubPersistence(session).record_raw_response(
        response=response,
        run=run,
        raw_record=raw,
        mapping=mapping,
        repository=repository,
    )
    return run, indexed


def count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_numeric_identity_survives_rename_and_topic_is_many_to_many(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    parser = GithubJsonParser()
    first_at = datetime(2026, 8, 11, 2, tzinfo=UTC)
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        _first_topic, first_mapping = configured_mapping(session, source, slug="mcp")
        _second_topic, second_mapping = configured_mapping(session, source, slug="protocols")
        first_run, first_raw = raw_response(
            session,
            tmp_path,
            source=source,
            observed_at=first_at,
            payload=(FIXTURES / "repository.json").read_bytes(),
            mapping=first_mapping,
        )
        persistence = GithubPersistence(session)
        repository, created = persistence.upsert_repository(
            parser.parse_repository((FIXTURES / "repository.json").read_bytes()),
            observed_at=first_at,
        )
        assert created is True
        assert persistence.upsert_match(
            repository=repository,
            mapping=first_mapping,
            query="model context protocol",
            rank=1,
            run=first_run,
            observed_at=first_at,
            tracking_state=GithubTrackingState.TRACKED,
            raw_response=first_raw,
        )
        assert persistence.upsert_match(
            repository=repository,
            mapping=second_mapping,
            query="protocol servers",
            rank=2,
            run=first_run,
            observed_at=first_at,
            tracking_state=GithubTrackingState.TRACKED,
            raw_response=first_raw,
        )

        renamed, created_again = persistence.upsert_repository(
            parser.parse_repository((FIXTURES / "repository_renamed.json").read_bytes()),
            observed_at=first_at + timedelta(hours=1),
        )
        assert created_again is False
        assert renamed.id == repository.id
        assert renamed.full_name == "modelcontextprotocol/reference-servers"
        assert count(session, GithubRepository) == 1
        assert count(session, GithubTopicRepositoryMatch) == 2


def test_daily_snapshots_are_immutable_idempotent_and_304_is_observed(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    parser = GithubJsonParser()
    first_at = datetime(2026, 8, 11, 2, tzinfo=UTC)
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        _topic, mapping = configured_mapping(session, source, slug="mcp")
        first_payload = (FIXTURES / "repository.json").read_bytes()
        first_run, first_raw = raw_response(
            session,
            tmp_path,
            source=source,
            observed_at=first_at,
            payload=first_payload,
            mapping=mapping,
        )
        persistence = GithubPersistence(session)
        first_data = parser.parse_repository(first_payload)
        repository, _created = persistence.upsert_repository(first_data, observed_at=first_at)
        baseline, baseline_created = persistence.create_full_snapshot(
            repository=repository,
            data=first_data,
            run=first_run,
            raw_response=first_raw,
            observed_at=first_at,
            etag='"repo-v1"',
        )
        duplicate, duplicate_created = persistence.create_full_snapshot(
            repository=repository,
            data=first_data,
            run=first_run,
            raw_response=first_raw,
            observed_at=first_at + timedelta(hours=1),
            etag='"repo-v1"',
        )
        assert baseline_created is True
        assert duplicate_created is False
        assert duplicate.id == baseline.id

        second_at = first_at + timedelta(days=1)
        second_payload = (FIXTURES / "repository_changed.json").read_bytes()
        second_run, second_raw = raw_response(
            session,
            tmp_path,
            source=source,
            observed_at=second_at,
            payload=second_payload,
            mapping=mapping,
            repository=repository,
            etag='"repo-v2"',
        )
        second_data = parser.parse_repository(second_payload)
        repository, _created = persistence.upsert_repository(second_data, observed_at=second_at)
        changed, changed_created = persistence.create_full_snapshot(
            repository=repository,
            data=second_data,
            run=second_run,
            raw_response=second_raw,
            observed_at=second_at,
            etag='"repo-v2"',
        )
        assert changed_created is True
        assert changed.stargazers_count - baseline.stargazers_count == 150

        third_at = second_at + timedelta(days=1)
        third_run, third_raw = raw_response(
            session,
            tmp_path,
            source=source,
            observed_at=third_at,
            payload=b"",
            status=304,
            mapping=mapping,
            repository=repository,
            etag='"repo-v2"',
        )
        unchanged, unchanged_created = persistence.create_unchanged_snapshot(
            repository=repository,
            run=third_run,
            raw_response=third_raw,
            observed_at=third_at,
        )
        poll = session.scalar(select(GithubRepositoryPollState))
        assert unchanged_created is True
        assert unchanged.observation_method is GithubSnapshotMethod.CONDITIONAL_304
        assert unchanged.stargazers_count == changed.stargazers_count
        assert poll is not None
        assert poll.last_snapshot_at == third_at
        assert count(session, GithubRepositorySnapshot) == 3
        assert count(session, GithubRawResponse) == 3
