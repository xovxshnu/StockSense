import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


def test_create_category(api: TestClient) -> None:
    response = api.post("/api/categories", json={"name": "  Electronics  "})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Electronics"}


def test_list_categories_sorted(api: TestClient) -> None:
    for name in ("Tools", "apparel", "Electronics"):
        api.post("/api/categories", json={"name": name})
    response = api.get("/api/categories")
    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["apparel", "Electronics", "Tools"]


def test_update_category(api: TestClient) -> None:
    category_id = api.post("/api/categories", json={"name": "Tools"}).json()["id"]
    response = api.put(f"/api/categories/{category_id}", json={"name": "Hardware"})
    assert response.status_code == 200
    assert response.json() == {"id": category_id, "name": "Hardware"}


def test_update_category_to_own_name_or_casing_is_allowed(api: TestClient) -> None:
    category_id = api.post("/api/categories", json={"name": "Tools"}).json()["id"]
    assert api.put(f"/api/categories/{category_id}", json={"name": "TOOLS"}).status_code == 200


@pytest.mark.parametrize("name", ["", "   ", None])
def test_blank_category_name_rejected(api: TestClient, name) -> None:
    assert api.post("/api/categories", json={"name": name}).status_code == 422
    category_id = api.post("/api/categories", json={"name": "Tools"}).json()["id"]
    assert api.put(f"/api/categories/{category_id}", json={"name": name}).status_code == 422


def test_duplicate_category_rejected_case_insensitively(api: TestClient) -> None:
    api.post("/api/categories", json={"name": "Tools"})
    assert api.post("/api/categories", json={"name": " tools "}).status_code == 409


def test_update_conflicting_with_other_category(api: TestClient) -> None:
    api.post("/api/categories", json={"name": "Tools"})
    other = api.post("/api/categories", json={"name": "Parts"}).json()["id"]
    assert api.put(f"/api/categories/{other}", json={"name": "TOOLS"}).status_code == 409


def test_update_missing_category_returns_404(api: TestClient) -> None:
    assert api.put("/api/categories/999", json={"name": "X"}).status_code == 404


def test_category_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/categories").status_code == 401
    assert client.post("/api/categories", json={"name": "X"}).status_code == 401
    assert client.put("/api/categories/1", json={"name": "X"}).status_code == 401
