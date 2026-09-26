import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, Product

FORBIDDEN_STOCK_FIELDS = {
    "quantity",
    "stock",
    "stock_quantity",
    "current_stock",
    "quantity_on_hand",
    "reserved_quantity",
    "available_quantity",
    "warehouse_id",
    "location_id",
}


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def category_id(api: TestClient) -> int:
    return api.post("/api/categories", json={"name": "Electronics"}).json()["id"]


def payload(default_category_id: int, **overrides) -> dict:
    return {"name": "Widget", "sku": "SKU001", "category_id": default_category_id} | overrides


def create(api: TestClient, default_category_id: int, **overrides):
    return api.post("/api/products", json=payload(default_category_id, **overrides))


def test_create_product(api: TestClient, category_id: int) -> None:
    response = create(api, category_id, uom="kg", unit_cost="12.50", reorder_level=5)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Widget" and body["sku"] == "SKU001"
    assert body["category_id"] == category_id and body["uom"] == "kg"
    assert body["unit_cost"] == "12.50" and body["reorder_level"] == 5
    assert body["active"] is True and body["created_at"]


def test_create_product_defaults(api: TestClient, category_id: int) -> None:
    body = create(api, category_id).json()
    assert (body["uom"], body["unit_cost"], body["reorder_level"], body["active"]) == (
        "Unit",
        "0.00",
        0,
        True,
    )


def test_get_product(api: TestClient, category_id: int) -> None:
    product_id = create(api, category_id).json()["id"]
    response = api.get(f"/api/products/{product_id}")
    assert response.status_code == 200 and response.json()["sku"] == "SKU001"


def test_list_products(api: TestClient, category_id: int) -> None:
    create(api, category_id, name="Bolt", sku="B1")
    create(api, category_id, name="Anchor", sku="A1")
    response = api.get("/api/products")
    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Anchor", "Bolt"]


def test_update_product_is_partial(api: TestClient, category_id: int) -> None:
    product_id = create(api, category_id, unit_cost="3.00").json()["id"]
    response = api.put(f"/api/products/{product_id}", json={"name": "Gadget", "reorder_level": 9})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Gadget" and body["reorder_level"] == 9
    assert body["sku"] == "SKU001" and body["unit_cost"] == "3.00"


def test_update_product_moves_category_and_rejects_bad_one(
    api: TestClient, category_id: int
) -> None:
    other = api.post("/api/categories", json={"name": "Tools"}).json()["id"]
    product_id = create(api, category_id).json()["id"]
    assert api.put(f"/api/products/{product_id}", json={"category_id": other}).json()[
        "category_id"
    ] == other
    assert api.put(f"/api/products/{product_id}", json={"category_id": 999}).status_code == 422


def test_update_rejects_explicit_null(api: TestClient, category_id: int) -> None:
    product_id = create(api, category_id).json()["id"]
    assert api.put(f"/api/products/{product_id}", json={"name": None}).status_code == 422


def test_sku_must_be_unique(api: TestClient, category_id: int) -> None:
    assert create(api, category_id).status_code == 201
    assert create(api, category_id, name="Other").status_code == 409


def test_sku_is_normalized(api: TestClient, category_id: int) -> None:
    body = create(api, category_id, sku="  sku001 ").json()
    assert body["sku"] == "SKU001"
    assert create(api, category_id, sku="Sku001").status_code == 409


def test_update_sku_conflict_and_normalization(api: TestClient, category_id: int) -> None:
    create(api, category_id, sku="A1")
    second = create(api, category_id, sku="B1").json()["id"]
    assert api.put(f"/api/products/{second}", json={"sku": " a1"}).status_code == 409
    assert api.put(f"/api/products/{second}", json={"sku": "b1"}).status_code == 200
    assert api.put(f"/api/products/{second}", json={"sku": "c1"}).json()["sku"] == "C1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"sku": "  "},
        {"uom": " "},
        {"unit_cost": "-0.01"},
        {"unit_cost": "1.234"},
        {"reorder_level": -1},
        {"reorder_level": 2**31},
        {"category_id": 0},
    ],
)
def test_invalid_product_input_rejected(
    api: TestClient, category_id: int, overrides: dict
) -> None:
    assert create(api, category_id, **overrides).status_code == 422


def test_invalid_category_id_rejected(api: TestClient) -> None:
    response = create(api, 999)
    assert response.status_code == 422
    assert "category_id" in response.json()["detail"]


def test_search_by_sku_and_name_case_insensitive(api: TestClient, category_id: int) -> None:
    create(api, category_id, name="Steel Bolt", sku="SKU001")
    create(api, category_id, name="Copper Wire", sku="WIRE7")
    by_sku = api.get("/api/products", params={"search": "sku001"}).json()
    assert [p["sku"] for p in by_sku] == ["SKU001"]
    by_name = api.get("/api/products", params={"search": "COPPER"}).json()
    assert [p["sku"] for p in by_name] == ["WIRE7"]
    assert api.get("/api/products", params={"search": "nomatch"}).json() == []
    assert len(api.get("/api/products", params={"search": "  "}).json()) == 2


def test_search_treats_wildcards_literally(api: TestClient, category_id: int) -> None:
    create(api, category_id, name="Bolt", sku="B1")
    assert api.get("/api/products", params={"search": "%"}).json() == []
    assert api.get("/api/products", params={"search": "_"}).json() == []


def test_missing_product_returns_404(api: TestClient) -> None:
    assert api.get("/api/products/999").status_code == 404
    assert api.put("/api/products/999", json={"name": "X"}).status_code == 404
    assert api.delete("/api/products/999").status_code == 404


def test_product_has_no_stock_fields(api: TestClient, category_id: int, db: Session) -> None:
    body = create(api, category_id).json()
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(body)
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(c.key for c in inspect(Product).columns)


def test_stock_fields_are_rejected_on_input(api: TestClient, category_id: int) -> None:
    assert create(api, category_id, quantity=10).status_code == 422
    product_id = create(api, category_id).json()["id"]
    assert api.put(f"/api/products/{product_id}", json={"location_id": 1}).status_code == 422


def test_product_holds_no_stock_state_or_location_fields(
    api: TestClient, category_id: int
) -> None:
    """Stock is per location and lives in the Stock model, never on Product.

    Deliberately does not care whether a Stock table (or a Product.stocks
    relationship) exists elsewhere: only Product's own columns and API output.
    """
    mapper = inspect(Product)
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(c.key for c in mapper.columns)
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(create(api, category_id).json())


def test_delete_archives_instead_of_removing(api: TestClient, category_id: int, db: Session) -> None:
    product_id = create(api, category_id).json()["id"]
    assert api.delete(f"/api/products/{product_id}").status_code == 204
    assert api.delete(f"/api/products/{product_id}").status_code == 204  # idempotent

    assert api.get("/api/products").json() == []
    assert len(api.get("/api/products", params={"include_inactive": True}).json()) == 1
    archived = api.get(f"/api/products/{product_id}").json()
    assert archived["active"] is False
    assert db.get(Product, product_id) is not None

    restored = api.put(f"/api/products/{product_id}", json={"active": True}).json()
    assert restored["active"] is True
    assert len(api.get("/api/products").json()) == 1


def test_category_product_relationship(api: TestClient, category_id: int, db: Session) -> None:
    product_id = create(api, category_id).json()["id"]
    product = db.get(Product, product_id)
    assert product.category.name == "Electronics"
    assert [p.id for p in db.get(Category, category_id).products] == [product_id]


def test_category_with_products_cannot_be_deleted(
    api: TestClient, category_id: int, db: Session
) -> None:
    create(api, category_id)
    with pytest.raises(IntegrityError):
        db.execute(delete(Category).where(Category.id == category_id))
    db.rollback()
    assert db.scalar(select(Category.id)) == category_id


def test_empty_category_can_be_deleted_at_db_level(
    api: TestClient, category_id: int, db: Session
) -> None:
    db.execute(delete(Category).where(Category.id == category_id))
    db.commit()
    assert db.scalar(select(Category.id)) is None


def test_db_enforces_constraints_directly(category_id_db: int, db: Session) -> None:
    """The DB, not just the API, rejects bad rows (guards against races/bypass)."""
    rows = [
        dict(name="A", sku="DUP", category_id=category_id_db),
        dict(name="B", sku="DUP", category_id=category_id_db),  # duplicate SKU
    ]
    db.add(Product(**rows[0]))
    db.commit()
    for bad in (
        rows[1],
        dict(name="C", sku="C", category_id=999),  # FK
        dict(name="D", sku="D", category_id=category_id_db, unit_cost=-1),
        dict(name="E", sku="E", category_id=category_id_db, reorder_level=-1),
        dict(name="  ", sku="F", category_id=category_id_db),
    ):
        db.add(Product(**bad))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.fixture
def category_id_db(db: Session) -> int:
    category = Category(name="Direct")
    db.add(category)
    db.commit()
    return category.id


def test_db_enforces_case_insensitive_category_names(db: Session) -> None:
    db.add(Category(name="Tools"))
    db.commit()
    db.add(Category(name="TOOLS"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_product_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/products/1").status_code == 401
    assert client.post("/api/products", json={}).status_code == 401
    assert client.put("/api/products/1", json={}).status_code == 401
    assert client.delete("/api/products/1").status_code == 401
