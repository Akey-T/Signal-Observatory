from __future__ import annotations

import asyncio
import json
import urllib.parse
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from arxiv_collector import ArxivClient, ArxivCollectionService
from collector_core import LocalRawStore
from observatory_db.arxiv_models import (
    ArxivCollectionCursor,
    ArxivCursorStatus,
    ArxivPaper,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.models import IngestionRun, Source, Topic, TopicSourceMapping
from signal_observatory_cli.main import app
from signal_observatory_config import Settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv"
runner = CliRunner()


class FakeTime:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.base = datetime(2026, 8, 10, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.seconds

    def wall(self) -> datetime:
        return self.base + timedelta(seconds=self.seconds)

    async def sleep(self, seconds: float) -> None:
        self.seconds += seconds
        await asyncio.sleep(0)


def configured(session: Session) -> tuple[Source, Topic, TopicSourceMapping]:
    source = Source(name="arxiv", kind="api", metadata_={})
    topic = Topic(
        canonical_name="Model Context Protocol",
        normalized_name="model context protocol",
        slug="model-context-protocol",
    )
    mapping = TopicSourceMapping(
        topic=topic,
        source=source,
        enabled=True,
        mapping_type="registry",
        query="model context protocol",
        configuration={"search_terms": ["model context protocol"]},
    )
    session.add_all([source, topic, mapping])
    session.commit()
    return source, topic, mapping


def settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "environment": "test",
        "raw_data_path": tmp_path,
        "arxiv_page_size": 1,
        "arxiv_max_requests_per_run": 20,
        "arxiv_max_results_per_topic": 100,
        "arxiv_backfill_window_days": 90,
        "arxiv_large_query_threshold": 100,
        "arxiv_max_runtime_minutes": 5,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def client(
    fake_time: FakeTime,
    transport: object,
) -> ArxivClient:
    return ArxivClient(
        base_url="https://export.arxiv.org/api/query",
        user_agent="Signal-Observatory/test",
        transport=transport,  # type: ignore[arg-type]
        clock=fake_time.monotonic,
        wall_clock=fake_time.wall,
        sleep=fake_time.sleep,
        jitter=lambda: 0,
    )


def start_parameter(url: str) -> int:
    return int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["start"][0])


def scalar_count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


async def paged_transport(
    url: str, _headers: Mapping[str, str], _timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    fixture = "pagination_page_1.xml" if start_parameter(url) == 0 else "pagination_page_2.xml"
    return 200, {"Content-Type": "application/atom+xml"}, (FIXTURES / fixture).read_bytes()


def test_backfill_paginates_checkpoints_and_skips_completed_rerun(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fake_time = FakeTime()
    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, paged_transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
            monotonic=fake_time.monotonic,
        )
        first = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )
        second = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )

        cursor = session.scalar(select(ArxivCollectionCursor))
        assert first.status == "succeeded"
        assert first.api_requests == 2
        assert first.entries_received == 2
        assert first.new_papers == 2
        assert first.topic_matches_added == 2
        assert second.status == "succeeded"
        assert second.api_requests == 0
        assert cursor is not None
        assert cursor.status is ArxivCursorStatus.SUCCEEDED
        assert cursor.next_start == 2
        assert scalar_count(session, ArxivPaper) == 2
        assert scalar_count(session, ArxivTopicMatch) == 2
        assert scalar_count(session, ArxivPaperObservation) == 2
        assert scalar_count(session, ArxivRawResponse) == 2


def test_backfill_dry_run_has_no_network_raw_or_database_writes(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    calls = 0

    async def transport(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        return 200, {}, (FIXTURES / "empty_result.xml").read_bytes()

    fake_time = FakeTime()
    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        summary = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
                dry_run=True,
            )
        )
        assert summary.mode == "dry_run"
        assert len(summary.planned_queries) == 1
        assert calls == 0
        assert scalar_count(session, IngestionRun) == 0
        assert list(LocalRawStore(tmp_path).iter_records("arxiv")) == []


def test_backfill_max_pages_checkpoint_resumes_without_repeating_page(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    requested_starts: list[int] = []

    async def transport(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        requested_starts.append(start_parameter(url))
        return await paged_transport(url, headers, timeout)

    fake_time = FakeTime()
    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        partial = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
                max_pages=1,
            )
        )
        resumed = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
                max_pages=1,
            )
        )
        assert partial.status == "partial"
        assert resumed.status == "succeeded"
        assert requested_starts == [0, 1]


def test_backfill_interruption_preserves_page_then_resumes(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fake_time = FakeTime()

    async def interrupted(
        url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        if start_parameter(url) == 1:
            raise ConnectionError("simulated interruption")
        return 200, {}, (FIXTURES / "pagination_page_1.xml").read_bytes()

    with Session(migrated_engine) as session:
        configured(session)
        failed_service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, interrupted),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        failed = asyncio.run(
            failed_service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )
        cursor = session.scalar(select(ArxivCollectionCursor))
        assert failed.status == "failed"
        assert cursor is not None
        assert cursor.next_start == 1
        assert scalar_count(session, ArxivPaper) == 1

        resumed_service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, paged_transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        resumed = asyncio.run(
            resumed_service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )
        assert resumed.status == "succeeded"
        assert scalar_count(session, ArxivPaper) == 2


def test_large_query_is_partitioned_into_smaller_date_windows(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fake_time = FakeTime()
    calls = 0

    async def transport(
        url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["search_query"][0]
        payload = (FIXTURES / "empty_result.xml").read_text(encoding="utf-8")
        if "202608010000 TO 202608030000" in query:
            payload = payload.replace("<opensearch:totalResults>0", "<opensearch:totalResults>1001")
        return 200, {}, payload.encode()

    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path, arxiv_large_query_threshold=10),
            client=client(fake_time, transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        summary = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 3, tzinfo=UTC),
            )
        )
        assert summary.status == "succeeded"
        assert calls == 3
        assert scalar_count(session, ArxivRawResponse) == 3
        statuses = session.scalars(select(ArxivCollectionCursor.status)).all()
        assert statuses.count(ArxivCursorStatus.PARTIAL) == 1
        assert statuses.count(ArxivCursorStatus.SUCCEEDED) == 2


def test_retry_attempts_count_toward_the_run_request_limit(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    calls = 0

    async def transient(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        return 503, {}, b"temporarily unavailable"

    fake_time = FakeTime()
    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path, arxiv_max_requests_per_run=1),
            client=client(fake_time, transient),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
            monotonic=fake_time.monotonic,
        )
        summary = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )

        assert summary.status == "failed"
        assert summary.api_requests == 1
        assert summary.raw_payloads_preserved == 1
        assert calls == 1


def test_result_limit_applies_across_all_windows_for_a_topic(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    calls = 0

    async def one_result(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        return 200, {}, (FIXTURES / "single_result.xml").read_bytes()

    fake_time = FakeTime()
    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(
                tmp_path,
                arxiv_backfill_window_days=1,
                arxiv_max_results_per_topic=1,
            ),
            client=client(fake_time, one_result),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
            monotonic=fake_time.monotonic,
        )
        summary = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 3, tzinfo=UTC),
            )
        )

        assert summary.status == "partial"
        assert summary.entries_received == 1
        assert calls == 1


def test_runtime_limit_is_checked_between_pages(migrated_engine: Engine, tmp_path: Path) -> None:
    calls = 0
    fake_time = FakeTime()

    async def slow_page(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        fake_time.seconds += 61
        return 200, {}, (FIXTURES / "pagination_page_1.xml").read_bytes()

    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path, arxiv_max_runtime_minutes=1),
            client=client(fake_time, slow_page),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
            monotonic=fake_time.monotonic,
        )
        summary = asyncio.run(
            service.backfill(
                topic_slugs=["model-context-protocol"],
                window_from=datetime(2026, 8, 1, tzinfo=UTC),
                window_until=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )

        assert summary.status == "partial"
        assert summary.entries_received == 1
        assert calls == 1


def test_backfill_cli_dry_run_is_machine_readable(
    migrated_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(migrated_engine) as session:
        configured(session)
    monkeypatch.setenv("SIGNAL_DATABASE_URL", str(migrated_engine.url))
    monkeypatch.setenv("SIGNAL_RAW_DATA_PATH", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "arxiv",
            "backfill",
            "--topic",
            "model-context-protocol",
            "--from",
            "2026-08-01",
            "--until",
            "2026-08-02",
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["planned_queries"][0]["topic_slug"] == "model-context-protocol"
    assert list(LocalRawStore(tmp_path).iter_records("arxiv")) == []
