from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from collector_core import LocalRawStore
from observatory_db.github_models import GithubRawResponse
from observatory_db.models import IngestionRun, IngestionStatus, Source
from observatory_operations import RawIntegrityVerifier


def test_raw_integrity_sample_passes_and_surfaces_corruption(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    observed_at = datetime(2026, 8, 11, 3, tzinfo=UTC)
    raw_store = LocalRawStore(tmp_path)
    record = raw_store.write(
        source="github",
        payload=b'{"id": 123}',
        request_timestamp=observed_at,
        collector_version="test",
        schema_version="test-v1",
        source_metadata={},
    )
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        session.add(source)
        session.flush()
        run = IngestionRun(
            source_id=source.id,
            started_at=observed_at,
            finished_at=observed_at,
            status=IngestionStatus.SUCCEEDED,
            collector_version="test",
            metadata_={},
        )
        session.add(run)
        session.flush()
        session.add(
            GithubRawResponse(
                ingestion_run_id=run.run_id,
                endpoint_type="repository",
                raw_path=str(record.directory),
                payload_checksum=record.sha256,
                observed_at=observed_at,
                request_url_hash="a" * 64,
                http_status=200,
                response_headers={},
                request_metadata={},
            )
        )
        session.commit()

        passed = RawIntegrityVerifier(session, tmp_path).verify(sample=100)
        assert passed["state"] == "pass"
        assert passed["records_checked"] == 1
        assert passed["modified_records"] == 0

        record.payload_path.write_bytes(b"corrupt")
        failed = RawIntegrityVerifier(session, tmp_path).verify(sample=100)
        assert failed["state"] == "fail"
        assert failed["failures"] == 1
        assert failed["failure_details"][0]["raw_id"]
