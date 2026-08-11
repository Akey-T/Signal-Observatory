from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from collector_core import LocalRawStore
from github_collector import GithubClient, GithubCollectionError, GithubCollectionService
from observatory_db.github_models import (
    GithubDiscoveryState,
    GithubRawResponse,
    GithubRepository,
    GithubTopicRepositoryMatch,
    GithubTrackingState,
)
from observatory_db.models import IngestionRun, Source, Topic, TopicSourceMapping
from signal_observatory_config import Settings

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"


class FakeWallClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(microseconds=1)
        return value

    def advance(self, value: timedelta) -> None:
        self.current += value


def settings(tmp_path: Path) -> Settings:
    return Settings(
        raw_data_path=tmp_path,
        github_token=SecretStr("fixture-token"),
        github_min_search_remaining=0,
        github_min_core_remaining=0,
        github_discovery_page_size=1,
        github_discovery_max_results_per_mapping=20,
    )


def add_mapping(
    session: Session,
    source: Source,
    *,
    slug: str,
    query: str,
    enabled: bool = True,
) -> TopicSourceMapping:
    topic = Topic(
        canonical_name=slug.replace("-", " ").title(),
        normalized_name=slug.replace("-", " "),
        slug=slug,
    )
    mapping = TopicSourceMapping(
        topic=topic,
        source=source,
        enabled=enabled,
        mapping_type="registry",
        query=query,
        configuration={"search_queries": [query]},
    )
    session.add_all([topic, mapping])
    session.flush()
    return mapping


def client(transport: object, clock: FakeWallClock) -> GithubClient:
    return GithubClient(
        token="fixture-token",
        api_version="2022-11-28",
        user_agent="Signal Observatory fixture",
        min_search_remaining=0,
        min_core_remaining=0,
        transport=transport,  # type: ignore[arg-type]
        wall_clock=clock,
        jitter=lambda: 0.0,
    )


def count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_dry_run_has_no_network_database_or_raw_writes(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="mcp", query="model context protocol")
        session.commit()

        summary = await GithubCollectionService(
            session, Settings(raw_data_path=tmp_path), raw_store=LocalRawStore(tmp_path)
        ).discover(topic_slugs=["mcp"], dry_run=True)

        assert summary.mode == "dry_run"
        assert summary.auth_configured is False
        assert summary.planned_queries[0]["queries"] == [
            "model context protocol is:public fork:false"
        ]
        assert count(session, IngestionRun) == 0
        assert list(LocalRawStore(tmp_path).iter_records("github")) == []


@pytest.mark.asyncio
async def test_discovery_paginates_by_link_and_is_idempotent(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    requests: list[str] = []

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        requests.append(url)
        if "page=2" in url:
            return (
                200,
                {"X-RateLimit-Remaining": "28", "X-RateLimit-Resource": "search"},
                (FIXTURES / "search_page_2.json").read_bytes(),
                url,
            )
        return (
            200,
            {
                "Link": f'<{url.replace("page=1", "page=2")}>; rel="next"',
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Resource": "search",
            },
            (FIXTURES / "search_page_1.json").read_bytes(),
            url,
        )

    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="mcp", query="model context protocol")
        session.commit()
        service = GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )

        first = await service.discover(topic_slugs=["mcp"], max_results=2)
        clock.advance(timedelta(minutes=1))
        second = await service.discover(topic_slugs=["mcp"], max_results=2)

        assert first.status == second.status == "succeeded"
        assert first.requests_sent == second.requests_sent == 2
        assert first.new_repositories == 2
        assert second.new_repositories == 0
        assert second.existing_repositories == 2
        assert second.topic_matches_added == 0
        assert count(session, GithubRepository) == 2
        assert count(session, GithubTopicRepositoryMatch) == 2
        assert count(session, GithubRawResponse) == 4
        assert len(requests) == 4


@pytest.mark.asyncio
async def test_same_repo_can_match_two_topics_and_forks_are_candidates(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    calls = 0

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        nonlocal calls
        calls += 1
        payload = (
            (FIXTURES / "search_multiple.json").read_bytes()
            if "first-topic" in url
            else (FIXTURES / "search_single.json").read_bytes()
        )
        return 200, {"X-RateLimit-Remaining": "20", "X-RateLimit-Resource": "search"}, payload, url

    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="first-topic", query="first-topic")
        add_mapping(session, source, slug="second-topic", query="second-topic")
        session.commit()
        summary = await GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        ).discover(topic_slugs=["first-topic", "second-topic"], max_results=3)

        matches = session.scalars(select(GithubTopicRepositoryMatch)).all()
        fork_match = next(
            match for match in matches if match.repository.github_repository_id == 1003
        )
        shared_matches = [
            match for match in matches if match.repository.github_repository_id == 1001
        ]
        assert summary.status == "succeeded"
        assert summary.fork_count == 1
        assert fork_match.tracking_state is GithubTrackingState.CANDIDATE
        assert len(shared_matches) == 2


@pytest.mark.asyncio
async def test_result_and_request_caps_stop_safely(migrated_engine: Engine, tmp_path: Path) -> None:
    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        return (
            200,
            {
                "Link": f'<{url.replace("page=1", "page=2")}>; rel="next"',
                "X-RateLimit-Remaining": "20",
                "X-RateLimit-Resource": "search",
            },
            (FIXTURES / "search_page_1.json").read_bytes(),
            url,
        )

    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="mcp", query="mcp")
        session.commit()
        service = GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        capped = await service.discover(topic_slugs=["mcp"], max_results=1)
        clock.advance(timedelta(minutes=1))
        request_limited = await service.discover(topic_slugs=["mcp"], max_results=2, max_requests=1)

        assert capped.status == "succeeded"
        assert capped.repositories_received == 1
        assert request_limited.status == "partial"
        assert request_limited.requests_sent == 1
        assert request_limited.errors == 1


@pytest.mark.asyncio
async def test_zero_results_initialize_mapping_and_disabled_mapping_is_rejected(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        return (
            200,
            {"X-RateLimit-Remaining": "20", "X-RateLimit-Resource": "search"},
            (FIXTURES / "search_empty.json").read_bytes(),
            url,
        )

    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="empty", query="no results")
        add_mapping(session, source, slug="disabled", query="disabled", enabled=False)
        session.commit()
        service = GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        summary = await service.discover(topic_slugs=["empty"])
        state = session.scalar(select(GithubDiscoveryState))

        assert summary.status == "succeeded"
        assert summary.repositories_received == 0
        assert state is not None
        assert state.last_successful_at is not None
        with pytest.raises(GithubCollectionError):
            await service.discover(topic_slugs=["disabled"], dry_run=True)
