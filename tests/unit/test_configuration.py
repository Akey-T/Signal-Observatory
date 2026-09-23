import pytest
from pydantic import ValidationError

from signal_observatory_config import Settings


def test_configuration_accepts_supported_database_driver() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", environment="test")
    assert settings.environment == "test"
    assert "database_url" not in settings.public_summary()


def test_blank_github_token_is_not_reported_as_configured() -> None:
    settings = Settings(github_token="")

    assert settings.github_token is None
    assert settings.public_summary()["github_auth_configured"] == "false"


def test_arxiv_partition_environment_aliases_are_applied(monkeypatch) -> None:
    monkeypatch.setenv("ARXIV_LARGE_QUERY_THRESHOLD", "321")
    monkeypatch.setenv("ARXIV_MIN_QUERY_PARTITION_MINUTES", "45")

    settings = Settings(_env_file=None)

    assert settings.arxiv_large_query_threshold == 321
    assert settings.arxiv_min_query_partition_minutes == 45


def test_configuration_rejects_unsupported_database_driver() -> None:
    with pytest.raises(ValidationError, match="psycopg PostgreSQL or SQLite"):
        Settings(database_url="mysql://localhost/example")


def test_configuration_requires_ordered_freshness_thresholds() -> None:
    with pytest.raises(ValidationError, match="very-stale threshold"):
        Settings(
            _env_file=None,
            arxiv_freshness_fresh_hours=72,
            arxiv_freshness_very_stale_hours=36,
        )
