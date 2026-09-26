import os
from collections.abc import Iterator

import pytest
from sqlalchemy import event
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Hermetic test config; must be set before app.main creates the app.
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-32b"
os.environ["ENVIRONMENT"] = "test"

from app.api.deps import get_reset_notifier
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, secret_key="test-secret-key-that-is-long-enough-32b")


@pytest.fixture
def db() -> Iterator[Session]:
    """A fresh in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def sent_resets() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def client(
    db: Session, settings: Settings, sent_resets: list[tuple[str, str]]
) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_reset_notifier] = lambda: (
        lambda _settings, email, token: sent_resets.append((email, token))
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/auth/signup",
        json={"login_id": "tester", "email": "tester@example.com", "password": "test-password-1"},
    )
    token = client.post(
        "/api/auth/login", json={"identifier": "tester", "password": "test-password-1"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
