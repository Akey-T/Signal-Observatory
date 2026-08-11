from __future__ import annotations

import json

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from observatory_db.models import Source, Topic, TopicSourceMapping
from signal_observatory_cli.main import app

runner = CliRunner()


def test_coverage_and_read_only_operations_commands(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNAL_DATABASE_URL", str(migrated_engine.url))
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setenv("SIGNAL_GITHUB_TOKEN", "")
    with Session(migrated_engine) as session:
        arxiv = Source(name="arxiv", kind="api", metadata_={})
        github = Source(name="github", kind="api", metadata_={})
        topic = Topic(
            canonical_name="Model Context Protocol",
            normalized_name="model context protocol",
            slug="model-context-protocol",
        )
        session.add_all([arxiv, github, topic])
        session.flush()
        session.add_all(
            [
                TopicSourceMapping(
                    topic_id=topic.id,
                    source_id=source.id,
                    enabled=True,
                    mapping_type="registry",
                    configuration={},
                )
                for source in (arxiv, github)
            ]
        )
        session.commit()

    rebuild = runner.invoke(app, ["coverage", "rebuild", "--json"])
    listing = runner.invoke(app, ["coverage", "list", "--status", "unknown", "--json"])
    show = runner.invoke(
        app,
        ["coverage", "show", "--topic", "model-context-protocol", "--json"],
    )
    cross_day = runner.invoke(app, ["github", "verify-cross-day", "--json"])
    soak = runner.invoke(app, ["arxiv", "verify-soak", "--days", "7", "--json"])
    raw = runner.invoke(app, ["ops", "verify-raw", "--json"])

    assert rebuild.exit_code == 0
    assert json.loads(rebuild.stdout)["created"] == 2
    assert listing.exit_code == 0
    assert json.loads(listing.stdout)["total"] == 2
    assert show.exit_code == 0
    channels = json.loads(show.stdout)["channels"]
    assert channels[0]["coverage"]["coverage_status"] == "unknown"
    assert channels[1]["coverage"]["coverage_strategy"] == "forward_snapshot"
    assert channels[2]["collection_state"] == "not_started"

    assert cross_day.exit_code == 1
    assert json.loads(cross_day.stdout)["modified_records"] == 0
    assert soak.exit_code == 1
    assert json.loads(soak.stdout)["status"] == "pending"
    assert raw.exit_code == 0
    assert json.loads(raw.stdout)["state"] == "not_initialized"
