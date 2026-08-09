import json
from pathlib import Path

import pytest
from sqlalchemy import Engine
from typer.testing import CliRunner

from signal_observatory_cli.main import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "topic_registry"
runner = CliRunner()


def test_validate_json_and_validation_exit_code() -> None:
    valid = runner.invoke(
        app, ["topics", "validate", "--registry-path", str(FIXTURES / "valid"), "--json"]
    )
    invalid = runner.invoke(
        app,
        ["topics", "validate", "--registry-path", str(FIXTURES / "duplicate_slug"), "--json"],
    )
    assert valid.exit_code == 0
    assert json.loads(valid.stdout)["topics"] == 1
    assert invalid.exit_code == 1
    assert json.loads(invalid.stdout)["exit_code"] == 1


def test_sync_list_show_and_noop_json(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNAL_DATABASE_URL", str(migrated_engine.url))
    registry_arguments = ["--registry-path", str(FIXTURES / "valid"), "--json"]
    first = runner.invoke(app, ["topics", "sync", *registry_arguments])
    second = runner.invoke(app, ["topics", "sync", *registry_arguments])
    listing = runner.invoke(app, ["topics", "list", "--search", "MCP", "--json"])
    detail = runner.invoke(app, ["topics", "show", "model-context-protocol", "--json"])
    assert first.exit_code == second.exit_code == listing.exit_code == detail.exit_code == 0
    assert json.loads(first.stdout)["version"] == 1
    assert json.loads(second.stdout)["changed"] is False
    assert json.loads(listing.stdout)["total"] == 1
    assert json.loads(detail.stdout)["slug"] == "model-context-protocol"


def test_diff_and_dry_run_do_not_mutate_database(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNAL_DATABASE_URL", str(migrated_engine.url))
    registry_arguments = ["--registry-path", str(FIXTURES / "valid"), "--json"]
    registry_diff = runner.invoke(app, ["topics", "diff", *registry_arguments])
    dry_run = runner.invoke(app, ["topics", "sync", "--dry-run", *registry_arguments])
    listing = runner.invoke(app, ["topics", "list", "--json"])
    assert registry_diff.exit_code == 0
    assert json.loads(registry_diff.stdout)["has_changes"] is True
    assert dry_run.exit_code == 0
    assert json.loads(dry_run.stdout)["dry_run"] is True
    assert json.loads(listing.stdout)["total"] == 0


def test_configuration_and_database_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNAL_DATABASE_URL", "not-a-supported-database-url")
    configuration_error = runner.invoke(app, ["topics", "list", "--json"])
    monkeypatch.setenv("SIGNAL_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    database_error = runner.invoke(app, ["topics", "list", "--json"])
    assert configuration_error.exit_code == 2
    assert json.loads(configuration_error.stdout)["exit_code"] == 2
    assert database_error.exit_code == 3
    assert json.loads(database_error.stdout)["exit_code"] == 3
