from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from tests.integration.test_github_discovery import FakeWallClock, add_mapping, client, settings

from collector_core import LocalRawStore
from github_collector import GithubCollectionService, GithubQueryService
from observatory_db.github_models import GithubRepositoryPollState, GithubRepositorySnapshot
from observatory_db.models import Source
from observatory_operations import GithubCrossDayVerifier

FIXTURES = Path(__file__).parents[1] / "fixtures" / "github"


@pytest.mark.asyncio
async def test_cross_day_is_pending_then_passes_and_detects_snapshot_mutation(
    migrated_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))
    call = 0

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        nonlocal call
        fixture = (
            "search_single.json"
            if "/search/" in url
            else ("repository.json" if call == 0 else "repository_changed.json")
        )
        if "/repos/" in url:
            call += 1
        return (
            200,
            {"ETag": f'"fixture-{call}"', "X-RateLimit-Remaining": "4990"},
            (FIXTURES / fixture).read_bytes(),
            url,
        )

    runtime = settings(tmp_path)
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="cross-day", query="cross day")
        session.commit()
        service = GithubCollectionService(
            session,
            runtime,
            client=client(transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        await service.discover(topic_slugs=["cross-day"], max_results=1)
        await service.snapshot(topic_slugs=["cross-day"])

        pending = GithubCrossDayVerifier(session, runtime).verify()
        assert pending["status"] == "pending"
        assert pending["exit_code"] == 1
        assert pending["modified_records"] == 0

        clock.advance(timedelta(days=1))
        await service.snapshot(topic_slugs=["cross-day"])
        passed = GithubCrossDayVerifier(session, runtime).verify()
        assert passed["status"] == "passed"
        assert passed["observation_date_count"] == 2
        assert passed["repositories_with_multiple_dates"] == 1
        assert passed["changed_transitions"] == 1
        assert passed["missing_intermediate_dates"] == []

        original_development = GithubQueryService.development

        def bad_delta(
            query_service: GithubQueryService, slug: str, *, limit: int = 20
        ) -> dict[str, Any] | None:
            payload = original_development(query_service, slug, limit=limit)
            assert payload is not None
            summary = payload["summary"]
            assert isinstance(summary, dict)
            current = summary["stars_delta_since_previous_snapshot"]
            assert isinstance(current, int)
            summary["stars_delta_since_previous_snapshot"] = current + 1
            return payload

        with monkeypatch.context() as patcher:
            patcher.setattr(GithubQueryService, "development", bad_delta)
            delta_failed = GithubCrossDayVerifier(session, runtime).verify()
        assert delta_failed["status"] == "failed"
        assert delta_failed["delta_mismatches"] == ["cross-day: star delta mismatch"]

        latest = session.scalar(
            select(GithubRepositorySnapshot).order_by(GithubRepositorySnapshot.observed_at.desc())
        )
        assert latest is not None
        original_stars = latest.stargazers_count
        latest.stargazers_count += 1
        session.commit()
        failed = GithubCrossDayVerifier(session, runtime).verify()
        assert failed["status"] == "failed"
        assert failed["snapshot_raw_mismatches"]

        latest.stargazers_count = original_stars
        poll = session.scalar(
            select(GithubRepositoryPollState).where(
                GithubRepositoryPollState.repository_id == latest.repository_id
            )
        )
        assert poll is not None
        poll.last_snapshot_at = datetime(2026, 8, 11, 3, tzinfo=UTC)
        session.commit()
        poll_failed = GithubCrossDayVerifier(session, runtime).verify()
        assert poll_failed["status"] == "failed"
        assert poll_failed["poll_state_inconsistencies"] == [str(latest.repository_id)]


@pytest.mark.asyncio
async def test_cross_day_preserves_missing_date_and_unchanged_observation(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    clock = FakeWallClock(datetime(2026, 8, 11, 3, tzinfo=UTC))

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes, str]:
        fixture = "search_single.json" if "/search/" in url else "repository.json"
        return (
            200,
            {"ETag": '"same"', "X-RateLimit-Remaining": "4990"},
            (FIXTURES / fixture).read_bytes(),
            url,
        )

    runtime = settings(tmp_path)
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        add_mapping(session, source, slug="unchanged", query="unchanged")
        session.commit()
        service = GithubCollectionService(
            session,
            runtime,
            client=client(transport, clock),
            raw_store=LocalRawStore(tmp_path),
            now=clock,
        )
        await service.discover(topic_slugs=["unchanged"], max_results=1)
        await service.snapshot(topic_slugs=["unchanged"])
        clock.advance(timedelta(days=2))
        await service.snapshot(topic_slugs=["unchanged"])

        report = GithubCrossDayVerifier(session, runtime).verify()
        assert report["status"] == "passed"
        assert report["unchanged_transitions"] == 1
        assert report["missing_intermediate_dates"] == ["2026-08-12"]
