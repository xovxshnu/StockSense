import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, Product, ReorderRule

FORBIDDEN_FIELDS = {
    "warehouse_id", "location_id", "current_stock", "quantity_on_hand", "quantity",
    "stock", "reserved_quantity", "supplier_id", "active", "lead_time", "min_stock",
    "max_stock", "price",
}


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def product_id(api: TestClient) -> int:
    category_id = api.post("/api/categories", json={"name": "Tools"}).json()["id"]
    body = {"name": "Widget", "sku": "W1", "category_id": category_id}
    return api.post("/api/products", json=body).json()["id"]


def create(api: TestClient, product: int, **overrides):
    body = {"product_id": product, "reorder_quantity": 50} | overrides
    return api.post("/api/reorder-rules", json=body)


def test_valid_create(api: TestClient, product_id: int) -> None:
    response = create(api, product_id)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1 and body["product_id"] == product_id
    assert body["reorder_quantity"] == 50
    assert "reorder_level" not in body
    assert body["created_at"]


def test_get_by_id(api: TestClient, product_id: int) -> None:
    rule_id = create(api, product_id).json()["id"]
    response = api.get(f"/api/reorder-rules/{rule_id}")
    assert response.status_code == 200 and response.json()["product_id"] == product_id


def test_list(api: TestClient, product_id: int) -> None:
    other = api.post(
        "/api/products", json={"name": "Bolt", "sku": "B1", "category_id": 1}
    ).json()["id"]
    create(api, product_id)
    create(api, other, reorder_quantity=1)
    response = api.get("/api/reorder-rules")
    assert response.status_code == 200
    assert [r["product_id"] for r in response.json()] == [product_id, other]


def test_update_reorder_quantity(api: TestClient, product_id: int) -> None:
    rule_id = create(api, product_id).json()["id"]
    body = api.put(f"/api/reorder-rules/{rule_id}", json={"reorder_quantity": 200}).json()
    assert body["reorder_quantity"] == 200 and body["product_id"] == product_id


def test_update_validates_values(api: TestClient, product_id: int) -> None:
    rule_id = create(api, product_id).json()["id"]
    for bad in ({"reorder_quantity": -1}, {"reorder_quantity": 0}, {"reorder_quantity": None}):
        assert api.put(f"/api/reorder-rules/{rule_id}", json=bad).status_code == 422


def test_delete(api: TestClient, product_id: int, db: Session) -> None:
    rule_id = create(api, product_id).json()["id"]
    assert api.delete(f"/api/reorder-rules/{rule_id}").status_code == 204
    assert api.get(f"/api/reorder-rules/{rule_id}").status_code == 404
    assert db.get(Product, product_id) is not None  # the product is untouched
    assert create(api, product_id).status_code == 201  # and can get a new rule


def test_missing_rule_returns_404(api: TestClient) -> None:
    assert api.get("/api/reorder-rules/999").status_code == 404
    assert api.put("/api/reorder-rules/999", json={"reorder_quantity": 1}).status_code == 404
    assert api.delete("/api/reorder-rules/999").status_code == 404


def test_missing_product_returns_404(api: TestClient) -> None:
    response = create(api, 999)
    assert response.status_code == 404 and "Product" in response.json()["detail"]


def test_duplicate_product_rule_returns_409(api: TestClient, product_id: int) -> None:
    first = create(api, product_id).json()
    assert create(api, product_id, reorder_quantity=99).status_code == 409
    assert api.get(f"/api/reorder-rules/{first['id']}").json()["reorder_quantity"] == 50  # not replaced


def test_product_id_is_immutable(api: TestClient, product_id: int) -> None:
    rule_id = create(api, product_id).json()["id"]
    assert api.put(f"/api/reorder-rules/{rule_id}", json={"product_id": 2}).status_code == 422
    assert api.get(f"/api/reorder-rules/{rule_id}").json()["product_id"] == product_id


@pytest.mark.parametrize("quantity", [0, -5])
def test_non_positive_reorder_quantity_rejected(
    api: TestClient, product_id: int, quantity: int
) -> None:
    assert create(api, product_id, reorder_quantity=quantity).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"reorder_level": 10}, {"location_id": 1}, {"warehouse_id": 1}, {"quantity": 5}, {"current_stock": 5},
        {"active": True}, {"supplier_id": 1},
    ],
)
def test_unknown_fields_rejected(api: TestClient, product_id: int, overrides: dict) -> None:
    assert create(api, product_id, **overrides).status_code == 422
    rule_id = create(api, product_id).json()["id"]
    assert api.put(f"/api/reorder-rules/{rule_id}", json=overrides).status_code == 422


@pytest.mark.parametrize("product", [0, -1, None, "abc"])
def test_invalid_product_id_rejected(api: TestClient, product) -> None:
    assert create(api, product).status_code == 422


def test_archived_product_cannot_receive_new_rule(api: TestClient, product_id: int) -> None:
    api.delete(f"/api/products/{product_id}")  # archives
    response = create(api, product_id)
    assert response.status_code == 422 and "archived" in response.json()["detail"]
    assert api.get("/api/reorder-rules").json() == []


def test_existing_rule_survives_product_archive(api: TestClient, product_id: int) -> None:
    rule_id = create(api, product_id).json()["id"]
    api.delete(f"/api/products/{product_id}")
    assert api.get(f"/api/reorder-rules/{rule_id}").status_code == 200
    assert api.put(f"/api/reorder-rules/{rule_id}", json={"reorder_quantity": 1}).status_code == 200


def test_auth_required(client: TestClient) -> None:
    assert client.get("/api/reorder-rules").status_code == 401
    assert client.post("/api/reorder-rules", json={}).status_code == 401
    assert client.get("/api/reorder-rules/1").status_code == 401
    assert client.put("/api/reorder-rules/1", json={}).status_code == 401
    assert client.delete("/api/reorder-rules/1").status_code == 401


@pytest.fixture
def db_product(db: Session) -> Product:
    category = Category(name="Direct")
    db.add(category)
    db.flush()
    product = Product(name="P", sku="P1", category_id=category.id)
    db.add(product)
    db.commit()
    return product


def test_db_enforces_unique_product_id(db: Session, db_product: Product) -> None:
    db.add(ReorderRule(product_id=db_product.id, reorder_quantity=1))
    db.commit()
    db.add(ReorderRule(product_id=db_product.id, reorder_quantity=2))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize(
    "values",
    [
        dict(reorder_quantity=0),
        dict(reorder_quantity=-1),
    ],
)
def test_db_enforces_check_constraints(db: Session, db_product: Product, values: dict) -> None:
    db.add(ReorderRule(product_id=db_product.id, **values))
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_enforces_foreign_key_and_not_null(db: Session) -> None:
    db.add(ReorderRule(product_id=999, reorder_quantity=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(ReorderRule(reorder_quantity=1))  # no product_id
    with pytest.raises(IntegrityError):
        db.commit()


def test_product_relationship(db: Session, db_product: Product) -> None:
    assert db_product.reorder_rule is None
    rule = ReorderRule(product_id=db_product.id, reorder_quantity=20)
    db.add(rule)
    db.commit()
    db.refresh(db_product)
    assert db_product.reorder_rule.id == rule.id
    assert rule.product.sku == "P1"


def test_product_deletion_restricted_by_rule(db: Session, db_product: Product) -> None:
    db.add(ReorderRule(product_id=db_product.id, reorder_quantity=20))
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(delete(Product).where(Product.id == db_product.id))
    db.rollback()
    assert db.scalar(select(Product.id)) == db_product.id


def test_exact_reorder_rule_field_set(api: TestClient, product_id: int) -> None:
    columns = {c.key for c in inspect(ReorderRule).columns}
    assert columns == {"id", "product_id", "reorder_quantity", "created_at"}
    assert FORBIDDEN_FIELDS.isdisjoint(columns)
    assert set(create(api, product_id).json()) == columns


def test_product_still_has_no_stock_or_rule_columns() -> None:
    columns = {c.key for c in inspect(Product).columns}
    assert columns == {
        "id", "name", "sku", "category_id", "uom", "unit_cost", "reorder_level", "active", "created_at",
    }


def test_reorder_level_is_no_longer_a_rule_field(api: TestClient, product_id: int) -> None:
    assert create(api, product_id, reorder_level=10).status_code == 422
    rule_id = create(api, product_id).json()["id"]
    assert api.put(f"/api/reorder-rules/{rule_id}", json={"reorder_level": 10}).status_code == 422
    assert "reorder_level" not in {c.key for c in inspect(ReorderRule).columns}


def test_product_reorder_level_remains_the_threshold(api: TestClient, product_id: int, db: Session) -> None:
    assert "reorder_level" in {c.key for c in inspect(Product).columns}
    api.put(f"/api/products/{product_id}", json={"reorder_level": 7})
    create(api, product_id)
    db.expire_all()
    product = db.get(Product, product_id)
    assert product.reorder_level == 7 and product.reorder_rule.reorder_quantity == 50
    assert api.get(f"/api/products/{product_id}").json()["reorder_level"] == 7
