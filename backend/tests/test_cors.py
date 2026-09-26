import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app

KEY = "k" * 32
ALLOWED = "http://localhost:5173"


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, secret_key=KEY, **overrides)


def preflight(client: TestClient, origin: str):
    return client.options(
        "/api/products",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:5173/ , https://app.example.com ,")
    monkeypatch.setenv("SECRET_KEY", KEY)
    assert Settings(_env_file=None).cors_origins == [
        "http://localhost:5173",
        "https://app.example.com",
    ]


def test_cors_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert make_settings().cors_origins == []
    response = preflight(TestClient(create_app(make_settings())), ALLOWED)
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["*", "localhost:5173", "ftp://x.example.com"])
def test_invalid_cors_origins_rejected(origin: str) -> None:
    with pytest.raises(ValidationError, match="invalid CORS origin"):
        make_settings(cors_origins=origin)


def test_allowed_origin_preflight_succeeds() -> None:
    client = TestClient(create_app(make_settings(cors_origins=ALLOWED)))
    response = preflight(client, ALLOWED)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    # Bearer auth: cookies/credentials are not enabled, and the origin is never "*".
    assert "access-control-allow-credentials" not in response.headers


def test_disallowed_origin_gets_no_cors_headers() -> None:
    client = TestClient(create_app(make_settings(cors_origins=ALLOWED)))
    response = preflight(client, "http://evil.example.com")
    assert "access-control-allow-origin" not in response.headers
    assert response.status_code == 400


def test_actual_request_carries_cors_header_for_allowed_origin() -> None:
    client = TestClient(create_app(make_settings(cors_origins=ALLOWED)))
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.headers["access-control-allow-origin"] == ALLOWED
    other = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_cors_origin_regex_allows_preview_deployments() -> None:
    settings = make_settings(cors_origin_regex=r"https://.*\.vercel\.app")
    client = TestClient(create_app(settings))
    ok = preflight(client, "https://stocksense-git-feature.vercel.app")
    assert ok.headers["access-control-allow-origin"] == "https://stocksense-git-feature.vercel.app"
    assert "access-control-allow-origin" not in preflight(client, "https://evil.example.com").headers
    assert "access-control-allow-credentials" not in ok.headers


def test_invalid_cors_origin_regex_rejected() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGIN_REGEX"):
        make_settings(cors_origin_regex="(unclosed")
