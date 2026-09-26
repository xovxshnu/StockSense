import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


@pytest.mark.parametrize("path", ["/api/health", "/health"])
def test_health(path: str) -> None:
    response = TestClient(app).get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_legacy_health_route_is_hidden_from_openapi() -> None:
    paths = app.openapi()["paths"]
    assert "/api/health" in paths and "/api/health/db" in paths
    assert "/health" not in paths


def test_health_db_reports_unavailable_database_as_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("connection refused: secret-host"))

    monkeypatch.setattr("app.api.health.get_engine", lambda: BrokenEngine())
    response = TestClient(app).get("/api/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}  # no driver details leaked
    assert "secret-host" not in response.text


def test_health_db_ok_when_database_reachable(monkeypatch: pytest.MonkeyPatch, db) -> None:
    monkeypatch.setattr("app.api.health.get_engine", lambda: db.get_bind())
    response = TestClient(app).get("/api/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
