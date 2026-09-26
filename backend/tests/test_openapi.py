"""The OpenAPI schema is the frontend contract: it must document the error
responses the routes actually return."""

import pytest
from fastapi.testclient import TestClient

PUBLIC = {
    ("/api/auth/signup", "post"),
    ("/api/auth/login", "post"),
    ("/api/auth/forgot-password", "post"),
    ("/api/auth/reset-password", "post"),
    ("/health", "get"),
}

# (path, method) -> status codes that must be documented (beyond 401/422).
EXPECTED = {
    ("/api/auth/signup", "post"): {"201", "409", "422"},
    ("/api/auth/login", "post"): {"200", "401", "422"},
    ("/api/auth/me", "get"): {"200", "401"},
    ("/api/auth/forgot-password", "post"): {"202", "422"},
    ("/api/auth/reset-password", "post"): {"200", "400", "422"},
    ("/api/categories", "post"): {"201", "409", "422"},
    ("/api/categories/{category_id}", "put"): {"404", "409", "422"},
    ("/api/products", "post"): {"201", "409", "422"},
    ("/api/products/{product_id}", "get"): {"404"},
    ("/api/products/{product_id}", "put"): {"404", "409", "422"},
    ("/api/products/{product_id}", "delete"): {"204", "404"},
    ("/api/warehouses", "post"): {"201", "409", "422"},
    ("/api/warehouses/{warehouse_id}", "get"): {"404"},
    ("/api/warehouses/{warehouse_id}", "put"): {"404", "409"},
    ("/api/locations", "post"): {"201", "409", "422"},
    ("/api/locations/{location_id}", "get"): {"404"},
    ("/api/locations/{location_id}", "put"): {"404", "409"},
    ("/api/contacts/{contact_id}", "get"): {"404"},
    ("/api/contacts/{contact_id}", "put"): {"404"},
    ("/api/reorder-rules", "post"): {"201", "404", "409", "422"},
    ("/api/reorder-rules/{rule_id}", "get"): {"404"},
    ("/api/reorder-rules/{rule_id}", "put"): {"404"},
    ("/api/reorder-rules/{rule_id}", "delete"): {"204", "404"},
}


@pytest.fixture(scope="module")
def paths() -> dict:
    from app.main import app

    return app.openapi()["paths"]


def operations(paths: dict):
    for path, item in paths.items():
        for method, operation in item.items():
            yield path, method, operation


def test_expected_responses_are_documented(paths: dict) -> None:
    for (path, method), codes in EXPECTED.items():
        documented = set(paths[path][method]["responses"])
        assert codes <= documented, f"{method.upper()} {path}: missing {codes - documented}"


def test_every_protected_operation_documents_401(paths: dict) -> None:
    protected = [(p, m, o) for p, m, o in operations(paths) if (p, m) not in PUBLIC]
    assert len(protected) > 20
    for path, method, operation in protected:
        assert "401" in operation["responses"], f"{method.upper()} {path} lacks 401"


def test_public_operations_do_not_document_401_unless_they_return_it(paths: dict) -> None:
    for path, method in PUBLIC - {("/api/auth/login", "post")}:
        assert "401" not in paths[path][method]["responses"], (path, method)


def test_every_operation_with_a_path_parameter_documents_404(paths: dict) -> None:
    for path, method, operation in operations(paths):
        if "{" in path:
            assert "404" in operation["responses"], f"{method.upper()} {path} lacks 404"


def test_error_bodies_use_the_detail_schema(paths: dict) -> None:
    schema = paths["/api/products/{product_id}"]["get"]["responses"]["404"]["content"][
        "application/json"
    ]["schema"]
    assert schema == {"$ref": "#/components/schemas/ErrorResponse"}


def test_documentation_matches_runtime_behavior(client: TestClient, auth_headers: dict) -> None:
    """Spot-check that documented codes are really what the API returns."""
    assert client.get("/api/products/1").status_code == 401
    client.headers.update(auth_headers)
    assert client.get("/api/products/999").status_code == 404
    assert client.post("/api/categories", json={"name": "A"}).status_code == 201
    assert client.post("/api/categories", json={"name": "a"}).status_code == 409
    assert client.post("/api/products", json={"name": "X"}).status_code == 422
    assert client.delete("/api/reorder-rules/999").status_code == 404
    assert client.post("/api/auth/reset-password", json={"token": "x", "new_password": "longenough1"}).status_code == 400


def test_docs_page_is_served() -> None:
    from app.main import app

    assert TestClient(app).get("/docs").status_code == 200
