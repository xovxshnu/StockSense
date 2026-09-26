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
