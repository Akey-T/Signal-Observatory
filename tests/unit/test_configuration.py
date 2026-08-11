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


def test_configuration_rejects_unsupported_database_driver() -> None:
    with pytest.raises(ValidationError, match="psycopg PostgreSQL or SQLite"):
        Settings(database_url="mysql://localhost/example")
