from __future__ import annotations

import json

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from observatory_db.models import Source, Topic, TopicSourceMapping
from signal_observatory_cli.main import app

runner = CliRunner()


def test_github_cli_dry_run_status_sample_and_missing_auth(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNAL_DATABASE_URL", str(migrated_engine.url))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SIGNAL_GITHUB_TOKEN", raising=False)
    with Session(migrated_engine) as session:
        source = Source(name="github", kind="api", metadata_={})
        topic = Topic(
            canonical_name="Model Context Protocol",
            normalized_name="model context protocol",
            slug="model-context-protocol",
        )
        session.add_all(
            [
                source,
                topic,
                TopicSourceMapping(
                    topic=topic,
                    source=source,
                    enabled=True,
                    mapping_type="registry",
                    query="model context protocol",
                    configuration={"search_queries": ["model context protocol"]},
                ),
            ]
        )
        session.commit()

    dry_run = runner.invoke(
        app,
        ["github", "discover", "--topic", "model-context-protocol", "--dry-run", "--json"],
    )
    missing_auth = runner.invoke(
        app,
        ["github", "discover", "--topic", "model-context-protocol", "--json"],
    )
    snapshot_dry_run = runner.invoke(
        app, ["github", "snapshot", "--all-tracked", "--dry-run", "--json"]
    )
    status = runner.invoke(app, ["github", "status", "--json"])
    sample = runner.invoke(app, ["github", "sample", "--topic", "model-context-protocol", "--json"])

    assert dry_run.exit_code == 0
    assert json.loads(dry_run.stdout)["auth_configured"] is False
    assert missing_auth.exit_code == 2
    assert "authentication is not configured" in json.loads(missing_auth.stdout)["error"]
    assert snapshot_dry_run.exit_code == 0
    assert json.loads(snapshot_dry_run.stdout)["repositories_due"] == 0
    assert status.exit_code == 0
    assert json.loads(status.stdout)["collector_state"] == "not_configured"
    assert sample.exit_code == 0
    assert json.loads(sample.stdout)["items"] == []


def test_github_cli_requires_explicit_selection() -> None:
    discover = runner.invoke(app, ["github", "discover", "--json"])
    snapshot = runner.invoke(app, ["github", "snapshot", "--json"])
    assert discover.exit_code == 1
    assert snapshot.exit_code == 1
