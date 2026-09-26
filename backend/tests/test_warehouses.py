import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Location, Warehouse

FORBIDDEN_STOCK_FIELDS = {
    "quantity",
    "stock",
    "current_stock",
    "product_id",
    "reserved_quantity",
}


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


def create(api: TestClient, **overrides):
    return api.post("/api/warehouses", json={"name": "Chennai", "short_code": "CHN"} | overrides)


def test_create_warehouse(api: TestClient) -> None:
    response = create(api, address="  12 Mount Road ")
    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "name": "Chennai",
        "short_code": "CHN",
        "address": "12 Mount Road",
        "active": True,
    }


def test_create_warehouse_defaults(api: TestClient) -> None:
    body = create(api).json()
    assert body["address"] is None and body["active"] is True


def test_list_warehouses(api: TestClient) -> None:
    create(api, name="Chennai", short_code="CHN")
    create(api, name="Bangalore", short_code="BLR")
    response = api.get("/api/warehouses")
    assert response.status_code == 200
    assert [w["short_code"] for w in response.json()] == ["BLR", "CHN"]


def test_get_warehouse(api: TestClient) -> None:
    warehouse_id = create(api).json()["id"]
    response = api.get(f"/api/warehouses/{warehouse_id}")
    assert response.status_code == 200 and response.json()["short_code"] == "CHN"


def test_update_warehouse_is_partial(api: TestClient) -> None:
    warehouse_id = create(api, address="Old").json()["id"]
    response = api.put(f"/api/warehouses/{warehouse_id}", json={"name": "Chennai Hub"})
    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Chennai Hub" and body["short_code"] == "CHN"
    assert body["address"] == "Old"
    cleared = api.put(f"/api/warehouses/{warehouse_id}", json={"address": None}).json()
    assert cleared["address"] is None


@pytest.mark.parametrize("overrides", [{"name": ""}, {"name": "   "}, {"name": None}])
def test_blank_name_rejected(api: TestClient, overrides: dict) -> None:
    assert create(api, **overrides).status_code == 422
    warehouse_id = create(api).json()["id"]
    assert api.put(f"/api/warehouses/{warehouse_id}", json=overrides).status_code == 422


@pytest.mark.parametrize("overrides", [{"short_code": ""}, {"short_code": "  "}, {"short_code": None}])
def test_blank_short_code_rejected(api: TestClient, overrides: dict) -> None:
    assert create(api, **overrides).status_code == 422
    warehouse_id = create(api).json()["id"]
    assert api.put(f"/api/warehouses/{warehouse_id}", json=overrides).status_code == 422


@pytest.mark.parametrize("raw", ["chn", " CHN ", "Chn"])
def test_short_code_is_normalized(api: TestClient, raw: str) -> None:
    assert create(api, short_code=raw).json()["short_code"] == "CHN"


def test_duplicate_short_code_rejected_after_normalization(api: TestClient) -> None:
    create(api)
    assert create(api, name="Other", short_code=" chn ").status_code == 409


def test_update_short_code_conflict_and_normalization(api: TestClient) -> None:
    create(api)
    other = create(api, name="Bangalore", short_code="BLR").json()["id"]
    assert api.put(f"/api/warehouses/{other}", json={"short_code": "chn"}).status_code == 409
    assert api.put(f"/api/warehouses/{other}", json={"short_code": "blr"}).status_code == 200
    assert api.put(f"/api/warehouses/{other}", json={"short_code": "hyd"}).json()["short_code"] == "HYD"


def test_missing_warehouse_returns_404(api: TestClient) -> None:
    assert api.get("/api/warehouses/999").status_code == 404
    assert api.put("/api/warehouses/999", json={"name": "X"}).status_code == 404


def test_archive_behavior(api: TestClient) -> None:
    warehouse_id = create(api).json()["id"]
    assert api.put(f"/api/warehouses/{warehouse_id}", json={"active": False}).json()["active"] is False
    assert api.get("/api/warehouses").json() == []
    assert len(api.get("/api/warehouses", params={"include_inactive": True}).json()) == 1
    assert api.get(f"/api/warehouses/{warehouse_id}").json()["active"] is False
    api.put(f"/api/warehouses/{warehouse_id}", json={"active": True})
    assert len(api.get("/api/warehouses").json()) == 1


def test_no_delete_endpoint(api: TestClient) -> None:
    warehouse_id = create(api).json()["id"]
    assert api.delete(f"/api/warehouses/{warehouse_id}").status_code == 405


def test_warehouse_has_no_stock_fields() -> None:
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(c.key for c in inspect(Warehouse).columns)
    assert {c.key for c in inspect(Warehouse).columns} == {
        "id", "name", "short_code", "address", "active",
    }


def test_warehouse_response_has_no_stock_fields(api: TestClient) -> None:
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(create(api).json())


def test_db_enforces_warehouse_constraints(db: Session) -> None:
    db.add(Warehouse(name="A", short_code="X"))
    db.commit()
    for bad in (
        Warehouse(name="B", short_code="X"),  # duplicate
        Warehouse(name="  ", short_code="Y"),  # blank name
        Warehouse(name="C", short_code="  "),  # blank code
    ):
        db.add(bad)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_warehouse_with_locations_cannot_be_deleted(db: Session) -> None:
    warehouse = Warehouse(name="A", short_code="A")
    warehouse.locations.append(Location(name="Main", short_code="MAIN"))
    db.add(warehouse)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(delete(Warehouse).where(Warehouse.id == warehouse.id))
    db.rollback()
    assert db.scalar(select(Warehouse.id)) == warehouse.id


def test_warehouse_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/warehouses").status_code == 401
    assert client.post("/api/warehouses", json={}).status_code == 401
    assert client.get("/api/warehouses/1").status_code == 401
    assert client.put("/api/warehouses/1", json={}).status_code == 401
