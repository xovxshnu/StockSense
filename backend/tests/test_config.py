import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.utils.notifications import deliver_password_reset

GOOD_KEY = "k" * 32


def test_missing_secret_key_fails_at_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None)


@pytest.mark.parametrize("key", ["", "change-me", "k" * 31])
def test_weak_secret_key_rejected(key: str) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be at least 32"):
        Settings(_env_file=None, secret_key=key)


def test_unknown_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key=GOOD_KEY, environment="staging")


def test_environment_defaults_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert Settings(_env_file=None, secret_key=GOOD_KEY).environment == "production"


@pytest.mark.parametrize("environment", ["production", "test"])
def test_reset_token_not_logged_outside_development(
    environment: str, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(_env_file=None, secret_key=GOOD_KEY, environment=environment)
    with caplog.at_level(logging.DEBUG):
        deliver_password_reset(settings, "a@example.com", "SECRET-RESET-TOKEN")
    assert "SECRET-RESET-TOKEN" not in caplog.text


def test_reset_token_logged_in_development(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(_env_file=None, secret_key=GOOD_KEY, environment="development")
    with caplog.at_level(logging.DEBUG):
        deliver_password_reset(settings, "a@example.com", "SECRET-RESET-TOKEN")
    assert "SECRET-RESET-TOKEN" in caplog.text


@pytest.mark.parametrize(
    "url, expected",
    [
        ("postgres://u:p@host:5432/db?sslmode=require", "postgresql+psycopg://u:p@host:5432/db?sslmode=require"),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_database_url_is_normalized_for_hosted_providers(url: str, expected: str) -> None:
    settings = Settings(_env_file=None, secret_key=GOOD_KEY, database_url_override=url)
    assert settings.database_url == expected
    assert settings.DATABASE_URL == expected  # scaffold-style alias


def test_database_url_env_var_takes_precedence_over_postgres_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@hosted/db")
    monkeypatch.setenv("POSTGRES_HOST", "ignored")
    settings = Settings(_env_file=None, secret_key=GOOD_KEY)
    assert settings.database_url == "postgresql+psycopg://u:p@hosted/db"


def test_single_declarative_base_is_shared() -> None:
    from app.core.database import Base as scaffold_base
    from app.models import Base

    assert scaffold_base is Base
    assert "users" in Base.metadata.tables
