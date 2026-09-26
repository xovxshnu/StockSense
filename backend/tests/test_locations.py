import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Location, Product, Warehouse

FORBIDDEN_STOCK_FIELDS = {"quantity", "stock", "current_stock", "product_id", "reserved_quantity"}


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def chn(api: TestClient) -> int:
    return api.post("/api/warehouses", json={"name": "Chennai", "short_code": "CHN"}).json()["id"]


@pytest.fixture
def blr(api: TestClient) -> int:
    return api.post("/api/warehouses", json={"name": "Bangalore", "short_code": "BLR"}).json()["id"]


def create(api: TestClient, warehouse: int, **overrides):
    body = {"warehouse_id": warehouse, "name": "Main", "short_code": "MAIN"} | overrides
    return api.post("/api/locations", json=body)


def test_create_location(api: TestClient, chn: int) -> None:
    response = create(api, chn, name="  Main Hall ")
    assert response.status_code == 201
    assert response.json() == {
        "id": 1, "warehouse_id": chn, "name": "Main Hall", "short_code": "MAIN", "active": True,
    }


def test_list_locations(api: TestClient, chn: int) -> None:
    create(api, chn, name="Receiving", short_code="RCV")
    create(api, chn, name="Dispatch", short_code="DSP")
    response = api.get("/api/locations")
    assert response.status_code == 200
    assert [x["short_code"] for x in response.json()] == ["DSP", "RCV"]


def test_filter_locations_by_warehouse(api: TestClient, chn: int, blr: int) -> None:
    create(api, chn)
    create(api, blr)
    create(api, blr, short_code="RCV", name="Receiving")
    assert len(api.get("/api/locations").json()) == 3
    filtered = api.get("/api/locations", params={"warehouse_id": blr}).json()
    assert len(filtered) == 2 and {x["warehouse_id"] for x in filtered} == {blr}
    assert api.get("/api/locations", params={"warehouse_id": 999}).json() == []


def test_get_location(api: TestClient, chn: int) -> None:
    location_id = create(api, chn).json()["id"]
    response = api.get(f"/api/locations/{location_id}")
    assert response.status_code == 200 and response.json()["short_code"] == "MAIN"


def test_update_location_is_partial(api: TestClient, chn: int) -> None:
    location_id = create(api, chn).json()["id"]
    response = api.put(f"/api/locations/{location_id}", json={"name": "Main Store"})
    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Main Store" and body["short_code"] == "MAIN"
    assert body["warehouse_id"] == chn


@pytest.mark.parametrize("overrides", [{"name": ""}, {"name": "  "}, {"name": None}])
def test_blank_name_rejected(api: TestClient, chn: int, overrides: dict) -> None:
    assert create(api, chn, **overrides).status_code == 422
    location_id = create(api, chn).json()["id"]
    assert api.put(f"/api/locations/{location_id}", json=overrides).status_code == 422


@pytest.mark.parametrize("overrides", [{"short_code": ""}, {"short_code": "  "}, {"short_code": None}])
def test_blank_short_code_rejected(api: TestClient, chn: int, overrides: dict) -> None:
    assert create(api, chn, **overrides).status_code == 422
    location_id = create(api, chn).json()["id"]
    assert api.put(f"/api/locations/{location_id}", json=overrides).status_code == 422


@pytest.mark.parametrize("raw", ["main", " MAIN ", "Main"])
def test_short_code_is_normalized(api: TestClient, chn: int, raw: str) -> None:
    assert create(api, chn, short_code=raw).json()["short_code"] == "MAIN"


def test_invalid_warehouse_id_rejected(api: TestClient) -> None:
    response = create(api, 999)
    assert response.status_code == 422 and "warehouse_id" in response.json()["detail"]
    assert create(api, 0).status_code == 422


def test_missing_warehouse_id_rejected(api: TestClient) -> None:
    assert api.post("/api/locations", json={"name": "Main", "short_code": "MAIN"}).status_code == 422


def test_duplicate_short_code_in_same_warehouse_rejected(api: TestClient, chn: int) -> None:
    create(api, chn)
    assert create(api, chn, name="Another", short_code=" main ").status_code == 409


def test_same_short_code_allowed_in_different_warehouses(
    api: TestClient, chn: int, blr: int
) -> None:
    assert create(api, chn).status_code == 201
    assert create(api, blr).status_code == 201


def test_update_short_code_conflicts_only_within_warehouse(
    api: TestClient, chn: int, blr: int
) -> None:
    create(api, chn)
    create(api, blr, short_code="RCV", name="Receiving")
    rcv_chn = create(api, chn, short_code="RCV", name="Receiving").json()["id"]
    assert api.put(f"/api/locations/{rcv_chn}", json={"short_code": "main"}).status_code == 409
    assert api.put(f"/api/locations/{rcv_chn}", json={"short_code": "rcv"}).status_code == 200


def test_warehouse_id_is_immutable(api: TestClient, chn: int, blr: int) -> None:
    location_id = create(api, chn).json()["id"]
    response = api.put(f"/api/locations/{location_id}", json={"warehouse_id": blr})
    assert response.status_code == 422
    assert api.get(f"/api/locations/{location_id}").json()["warehouse_id"] == chn


def test_missing_location_returns_404(api: TestClient) -> None:
    assert api.get("/api/locations/999").status_code == 404
    assert api.put("/api/locations/999", json={"name": "X"}).status_code == 404


def test_archive_behavior(api: TestClient, chn: int) -> None:
    location_id = create(api, chn).json()["id"]
    assert api.put(f"/api/locations/{location_id}", json={"active": False}).json()["active"] is False
    assert api.get("/api/locations").json() == []
    assert len(api.get("/api/locations", params={"include_inactive": True}).json()) == 1
    assert api.get(f"/api/locations/{location_id}").json()["active"] is False
    api.put(f"/api/locations/{location_id}", json={"active": True})
    assert len(api.get("/api/locations").json()) == 1


def test_archiving_warehouse_keeps_its_locations(api: TestClient, chn: int) -> None:
    location_id = create(api, chn).json()["id"]
    api.put(f"/api/warehouses/{chn}", json={"active": False})
    location = api.get(f"/api/locations/{location_id}").json()
    assert location["warehouse_id"] == chn and location["active"] is True


def test_no_delete_endpoint(api: TestClient, chn: int) -> None:
    location_id = create(api, chn).json()["id"]
    assert api.delete(f"/api/locations/{location_id}").status_code == 405


def test_warehouse_location_relationship(api: TestClient, chn: int, db: Session) -> None:
    location_id = create(api, chn).json()["id"]
    location = db.get(Location, location_id)
    assert location.warehouse.short_code == "CHN"
    assert [x.id for x in db.get(Warehouse, chn).locations] == [location_id]


def test_location_cannot_exist_without_warehouse(db: Session) -> None:
    db.add(Location(name="Orphan", short_code="ORP", warehouse_id=999))  # dangling FK
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Location(name="NoWh", short_code="NW"))  # no warehouse at all
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_db_enforces_location_constraints(db: Session) -> None:
    warehouse = Warehouse(name="A", short_code="A")
    other = Warehouse(name="B", short_code="B")
    db.add_all([warehouse, other])
    db.commit()
    db.add(Location(warehouse_id=warehouse.id, name="Main", short_code="MAIN"))
    db.add(Location(warehouse_id=other.id, name="Main", short_code="MAIN"))  # other warehouse: ok
    db.commit()
    for bad in (
        Location(warehouse_id=warehouse.id, name="Dup", short_code="MAIN"),
        Location(warehouse_id=warehouse.id, name="  ", short_code="X"),
        Location(warehouse_id=warehouse.id, name="Blank code", short_code="  "),
    ):
        db.add(bad)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_location_has_no_stock_fields(api: TestClient, chn: int) -> None:
    columns = {c.key for c in inspect(Location).columns}
    assert columns == {"id", "warehouse_id", "name", "short_code", "active"}
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(columns)
    assert FORBIDDEN_STOCK_FIELDS.isdisjoint(create(api, chn).json())


def test_stock_fields_rejected_on_input(api: TestClient, chn: int) -> None:
    assert create(api, chn, quantity=5).status_code == 422
    location_id = create(api, chn).json()["id"]
    assert api.put(f"/api/locations/{location_id}", json={"product_id": 1}).status_code == 422


def test_product_model_unchanged() -> None:
    assert {c.key for c in inspect(Product).columns} == {
        "id", "name", "sku", "category_id", "uom", "unit_cost", "reorder_level", "active", "created_at",
    }


def test_location_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/locations").status_code == 401
    assert client.post("/api/locations", json={}).status_code == 401
    assert client.get("/api/locations/1").status_code == 401
    assert client.put("/api/locations/1", json={}).status_code == 401
