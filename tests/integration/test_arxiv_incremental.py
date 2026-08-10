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
    ArxivRawResponse,
)
from observatory_db.models import IngestionError, IngestionRun, Source, Topic, TopicSourceMapping
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


def add_mapping(session: Session, source: Source, *, slug: str, term: str) -> TopicSourceMapping:
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
        query=term,
        configuration={"search_terms": [term]},
    )
    session.add_all([topic, mapping])
    session.flush()
    return mapping


def configured(session: Session, *, second: bool = False) -> list[TopicSourceMapping]:
    source = Source(name="arxiv", kind="api", metadata_={})
    session.add(source)
    session.flush()
    mappings = [
        add_mapping(
            session,
            source,
            slug="model-context-protocol",
            term="model context protocol",
        )
    ]
    if second:
        mappings.append(add_mapping(session, source, slug="data-lakehouse", term="data lakehouse"))
    session.commit()
    return mappings


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        environment="test",
        raw_data_path=tmp_path,
        arxiv_page_size=1,
        arxiv_max_requests_per_run=20,
        arxiv_max_results_per_topic=100,
        arxiv_large_query_threshold=100,
        arxiv_incremental_overlap_hours=48,
        arxiv_max_runtime_minutes=5,
    )


def client(fake_time: FakeTime, transport: object) -> ArxivClient:
    return ArxivClient(
        base_url="https://export.arxiv.org/api/query",
        user_agent="Signal-Observatory/test",
        transport=transport,  # type: ignore[arg-type]
        clock=fake_time.monotonic,
        wall_clock=fake_time.wall,
        sleep=fake_time.sleep,
        jitter=lambda: 0,
    )


def request_values(url: str) -> dict[str, str]:
    return {
        key: values[0]
        for key, values in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()
    }


def scalar_count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_incremental_first_and_second_run_use_overlap_window(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    queries: list[str] = []
    starts: list[str] = []

    async def transport(
        url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        values = request_values(url)
        queries.append(values["search_query"])
        starts.append(values["start"])
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
            monotonic=fake_time.monotonic,
        )
        first = asyncio.run(service.collect())
        fake_time.seconds += 24 * 60 * 60
        second = asyncio.run(service.collect())

        cursor = session.scalar(
            select(ArxivCollectionCursor).where(ArxivCollectionCursor.cursor_key == "incremental")
        )
        assert first.status == second.status == "succeeded"
        assert "submittedDate:[202608080000 TO 202608100000]" in queries[0]
        assert "submittedDate:[202608080000 TO 202608110000]" in queries[1]
        assert starts == ["0", "0"]
        assert cursor is not None
        assert cursor.status is ArxivCursorStatus.SUCCEEDED
        assert cursor.last_successful_run_at == fake_time.wall()
        assert scalar_count(session, ArxivRawResponse) == 2


def test_incremental_updates_existing_paper_version(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fixture_names = iter(["single_result.xml", "updated_article.xml"])

    async def transport(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        return 200, {}, (FIXTURES / next(fixture_names)).read_bytes()

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
        first = asyncio.run(service.collect())
        fake_time.seconds += 24 * 60 * 60
        second = asyncio.run(service.collect())

        paper = session.scalar(select(ArxivPaper))
        assert paper is not None
        assert first.new_papers == 1
        assert second.updated_papers == 1
        assert paper.latest_version == 3
        assert scalar_count(session, ArxivPaper) == 1


def test_incremental_failure_resumes_and_advances_success_only_after_completion(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fake_time = FakeTime()

    async def interrupted(
        url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        start = int(request_values(url)["start"])
        if start == 1:
            raise ConnectionError("simulated interruption")
        return 200, {}, (FIXTURES / "pagination_page_1.xml").read_bytes()

    async def resume(
        url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        assert request_values(url)["start"] == "1"
        return 200, {}, (FIXTURES / "pagination_page_2.xml").read_bytes()

    with Session(migrated_engine) as session:
        configured(session)
        first_service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, interrupted),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        failed = asyncio.run(first_service.collect())
        cursor = session.scalar(
            select(ArxivCollectionCursor).where(ArxivCollectionCursor.cursor_key == "incremental")
        )
        assert cursor is not None
        assert failed.status == "failed"
        assert cursor.next_start == 1
        assert cursor.last_successful_run_at is None

        resume_service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, resume),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        completed = asyncio.run(resume_service.collect())
        assert completed.status == "succeeded"
        assert cursor.status is ArxivCursorStatus.SUCCEEDED
        assert cursor.last_successful_run_at is not None
        assert scalar_count(session, ArxivPaper) == 2


def test_incremental_partial_failure_isolated_between_mappings(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fake_time = FakeTime()

    async def transport(
        url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        query = request_values(url)["search_query"]
        if "data lakehouse" in query:
            raise ConnectionError("second mapping unavailable")
        return 200, {}, (FIXTURES / "empty_result.xml").read_bytes()

    with Session(migrated_engine) as session:
        configured(session, second=True)
        service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        summary = asyncio.run(service.collect())
        statuses = session.scalars(
            select(ArxivCollectionCursor.status).where(
                ArxivCollectionCursor.cursor_key == "incremental"
            )
        ).all()
        assert summary.status == "partial"
        assert summary.errors == 1
        assert ArxivCursorStatus.SUCCEEDED in statuses
        assert ArxivCursorStatus.FAILED in statuses


def test_incremental_403_preserves_raw_and_stops_run(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    calls = 0

    async def forbidden(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        nonlocal calls
        calls += 1
        return 403, {}, b"forbidden"

    fake_time = FakeTime()
    with Session(migrated_engine) as session:
        configured(session, second=True)
        service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, forbidden),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        summary = asyncio.run(service.collect())
        error = session.scalar(select(IngestionError))
        run = session.scalar(select(IngestionRun))
        assert summary.status == "failed"
        assert calls == 1
        assert summary.raw_payloads_preserved == 1
        assert error is not None
        assert error.details["critical"] is True
        assert run is not None
        assert run.error_count == 1


def test_status_and_sample_cli_read_persisted_lineage(
    migrated_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_time = FakeTime()

    async def transport(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        return 200, {}, (FIXTURES / "single_result.xml").read_bytes()

    with Session(migrated_engine) as session:
        configured(session)
        service = ArxivCollectionService(
            session,
            settings(tmp_path),
            client=client(fake_time, transport),
            raw_store=LocalRawStore(tmp_path),
            now=fake_time.wall,
        )
        asyncio.run(service.collect())

    monkeypatch.setenv("SIGNAL_DATABASE_URL", str(migrated_engine.url))
    status_result = runner.invoke(app, ["arxiv", "status", "--json"])
    sample_result = runner.invoke(
        app,
        [
            "arxiv",
            "sample",
            "--topic",
            "model-context-protocol",
            "--limit",
            "20",
            "--json",
        ],
    )
    assert status_result.exit_code == 0, status_result.stdout
    assert sample_result.exit_code == 0, sample_result.stdout
    status_payload = json.loads(status_result.stdout)
    sample_payload = json.loads(sample_result.stdout)
    assert status_payload["collector_state"] == "healthy"
    assert status_payload["papers_observed"] == 1
    assert len(sample_payload["items"]) == 1
    assert sample_payload["items"][0]["matched_query"] == 'all:"model context protocol"'
    assert sample_payload["items"][0]["raw_checksum"]
