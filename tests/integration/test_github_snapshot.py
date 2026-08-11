from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from tests.integration.test_github_discovery import FakeWallClock, add_mapping, client, settings

from collector_core import LocalRawStore
from github_collector import GithubCollectionService
from observatory_db.github_models import (
    GithubRawResponse,
    GithubRepositoryPollState,
    GithubRepositorySnapshot,
    GithubSnapshotMethod,
)
from observatory_db.models import Source

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"


async def discover_one(
    session: Session, tmp_path: Path, clock: FakeWallClock
) -> GithubCollectionService:
    async def search_transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        return (
            200,
            {"X-RateLimit-Remaining": "20", "X-RateLimit-Resource": "search"},
            (FIXTURES / "search_single.json").read_bytes(),
            url,
        )

    source = Source(name="github", kind="api", metadata_={})
    session.add(source)
    session.flush()
    add_mapping(session, source, slug="mcp", query="model context protocol")
    session.commit()
    service = GithubCollectionService(
        session,
        settings(tmp_path),
        client=client(search_transport, clock),
        raw_store=LocalRawStore(tmp_path),
        now=clock,
    )
    await service.discover(topic_slugs=["mcp"], max_results=1)
    return service


def count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_baseline_then_304_creates_two_real_daily_observations(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    conditional_headers: list[str | None] = []
    response_status = 200

    async def repository_transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        conditional_headers.append(headers.get("If-None-Match"))
        if response_status == 304:
            return (
                304,
                {
                    "ETag": '"repo-v1"',
                    "X-RateLimit-Remaining": "4990",
                    "X-RateLimit-Resource": "core",
                },
                b"",
                url,
            )
        return (
            200,
            {"ETag": '"repo-v1"', "X-RateLimit-Remaining": "4999", "X-RateLimit-Resource": "core"},
            (FIXTURES / "repository.json").read_bytes(),
            url,
        )

    with Session(migrated_engine) as session:
        await discover_one(session, tmp_path, clock)
        snapshot_service = GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(repository_transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        baseline = await snapshot_service.snapshot(topic_slugs=["mcp"])
        clock.advance(timedelta(days=1))
        response_status = 304
        unchanged = await snapshot_service.snapshot(topic_slugs=["mcp"])

        snapshots = session.scalars(
            select(GithubRepositorySnapshot).order_by(GithubRepositorySnapshot.observed_at)
        ).all()
        assert baseline.status == unchanged.status == "succeeded"
        assert baseline.snapshots_created == unchanged.snapshots_created == 1
        assert conditional_headers == [None, '"repo-v1"']
        assert len(snapshots) == 2
        assert snapshots[0].observation_method is GithubSnapshotMethod.FULL_200
        assert snapshots[1].observation_method is GithubSnapshotMethod.CONDITIONAL_304
        assert snapshots[1].stargazers_count == snapshots[0].stargazers_count


@pytest.mark.asyncio
async def test_changed_snapshot_preserves_negative_and_positive_deltas(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    call = 0

    async def repository_transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        nonlocal call
        call += 1
        fixture = "repository.json" if call == 1 else "repository_changed.json"
        etag = '"repo-v1"' if call == 1 else '"repo-v2"'
        return (
            200,
            {"ETag": etag, "X-RateLimit-Remaining": "4990", "X-RateLimit-Resource": "core"},
            (FIXTURES / fixture).read_bytes(),
            url,
        )

    with Session(migrated_engine) as session:
        await discover_one(session, tmp_path, clock)
        service = GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(repository_transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        await service.snapshot(topic_slugs=["mcp"])
        clock.advance(timedelta(days=1))
        await service.snapshot(topic_slugs=["mcp"])
        snapshots = session.scalars(
            select(GithubRepositorySnapshot).order_by(GithubRepositorySnapshot.observed_at)
        ).all()

        assert snapshots[1].stargazers_count - snapshots[0].stargazers_count == 150
        assert snapshots[1].open_issues_count - snapshots[0].open_issues_count == -4


@pytest.mark.asyncio
async def test_raw_survives_normalization_failure_and_poll_does_not_advance(
    migrated_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))

    async def repository_transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        return (
            200,
            {"ETag": '"repo-v1"', "X-RateLimit-Remaining": "4999", "X-RateLimit-Resource": "core"},
            (FIXTURES / "repository.json").read_bytes(),
            url,
        )

    with Session(migrated_engine) as session:
        await discover_one(session, tmp_path, clock)
        service = GithubCollectionService(
            session,
            settings(tmp_path),
            client=client(repository_transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )

        def fail_snapshot(*args: object, **kwargs: object) -> object:
            raise ValueError("fixture database failure")

        monkeypatch.setattr(service.persistence, "create_full_snapshot", fail_snapshot)
        summary = await service.snapshot(topic_slugs=["mcp"])
        poll = session.scalar(select(GithubRepositoryPollState))

        assert summary.status == "partial"
        assert summary.raw_payloads_preserved == 1
        assert count(session, GithubRawResponse) == 2  # discovery + snapshot HTTP evidence
        assert count(session, GithubRepositorySnapshot) == 0
        assert poll is None or poll.last_successful_at is None
