"""Delivery API tests (SQLite, through the HTTP API as the operations UI uses it)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Location, MovementType, Product
from tests.operation_fixtures import (  # noqa: F401 (fixtures)
    api,
    archive,
    delivery_body,
    md,
    movements,
    put_stock,
    stock_qty,
)


def create(api: TestClient, md, **overrides) -> dict:
    response = api.post("/api/deliveries", json=delivery_body(md, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def todo(api: TestClient, delivery: dict) -> dict:
    response = api.post(f"/api/deliveries/{delivery['id']}/todo")
    assert response.status_code == 200, response.text
    return response.json()


def validate(api: TestClient, delivery: dict):
    return api.post(f"/api/deliveries/{delivery['id']}/validate")


def status_of(api: TestClient, delivery: dict) -> str:
    return api.get(f"/api/deliveries/{delivery['id']}").json()["status"]


def out_movements(db: Session):
    return [m for m in movements(db) if m.movement_type is MovementType.OUT]


# --- Create / read / update -------------------------------------------------


def test_create_draft(api: TestClient, db: Session, md) -> None:
    body = create(api, md)
    assert body["status"] == "DRAFT" and body["reference"] == "WH/OUT/0001"
    assert (body["customer_id"], body["warehouse_id"], body["source_location_id"]) == (
        md.customer, md.wh, md.loc_a,
    )
    assert body["delivery_address"] == "1 Main Street"
    assert body["schedule_date"] == "2026-10-02"
    assert body["created_at"] and body["updated_at"]
    [line] = body["lines"]
    assert line["product"]["sku"] == "W1" and Decimal(line["quantity"]) == 20
    assert movements(db) == []  # creating needs no stock and moves none


def test_references_are_sequential(api: TestClient, md) -> None:
    assert [create(api, md)["reference"] for _ in range(2)] == ["WH/OUT/0001", "WH/OUT/0002"]


def test_list_newest_first_with_filters(api: TestClient, md) -> None:
    first = create(api, md)
    second = create(api, md)
    todo(api, second)  # no stock -> WAITING
    assert [d["id"] for d in api.get("/api/deliveries").json()] == [second["id"], first["id"]]
    assert [d["id"] for d in api.get("/api/deliveries", params={"status": "WAITING"}).json()] == [
        second["id"]
    ]
    assert [d["id"] for d in api.get("/api/deliveries", params={"search": "OUT/0001"}).json()] == [
        first["id"]
    ]


def test_get_detail(api: TestClient, md) -> None:
    delivery = create(api, md)
    assert api.get(f"/api/deliveries/{delivery['id']}").json() == delivery
    assert api.get("/api/deliveries/999").status_code == 404


def test_update_draft(api: TestClient, md) -> None:
    delivery = create(api, md)
    response = api.put(f"/api/deliveries/{delivery['id']}", json={
        "source_location_id": md.loc_b,
        "delivery_address": None,
        "lines": [{"product_id": md.p2, "quantity": 4}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_location_id"] == md.loc_b and body["delivery_address"] is None
    assert [(l["product_id"], Decimal(l["quantity"])) for l in body["lines"]] == [(md.p2, 4)]
    assert body["customer_id"] == md.customer  # not sent, not changed


def test_blank_address_is_stored_as_null(api: TestClient, md) -> None:
    assert create(api, md, delivery_address="   ")["delivery_address"] is None


@pytest.mark.parametrize("field", ["warehouse_id", "source_location_id", "schedule_date", "lines"])
def test_update_cannot_null_required_fields(api: TestClient, md, field) -> None:
    delivery = create(api, md)
    assert api.put(f"/api/deliveries/{delivery['id']}", json={field: None}).status_code == 422


def test_customer_must_be_a_customer_contact(api: TestClient, md) -> None:
    response = api.post("/api/deliveries", json=delivery_body(md, customer_id=md.supplier))
    assert response.status_code == 422 and "customer" in response.json()["detail"]


# --- Reference / quantity validation ----------------------------------------


@pytest.mark.parametrize(
    "overrides, detail",
    [
        ({"lines": [{"product_id": 999, "quantity": 1}]}, "Product 999 does not exist"),
        ({"source_location_id": 999}, "source_location_id does not exist"),
        ({"warehouse_id": 999}, "warehouse_id does not exist"),
    ],
    ids=["product", "location", "warehouse"],
)
def test_invalid_references(api: TestClient, md, overrides, detail) -> None:
    response = api.post("/api/deliveries", json=delivery_body(md, **overrides))
    assert response.status_code == 422 and response.json()["detail"] == detail


def test_archived_product(api: TestClient, md) -> None:
    response = api.post("/api/deliveries", json=delivery_body(
        md, lines=[{"product_id": md.archived_product, "quantity": 1}]))
    assert response.status_code == 422 and "archived" in response.json()["detail"]


def test_archived_location(api: TestClient, md) -> None:
    response = api.post("/api/deliveries", json=delivery_body(
        md, source_location_id=md.archived_loc))
    assert response.status_code == 422
    assert response.json()["detail"] == "source_location_id is archived"


def test_location_must_belong_to_warehouse(api: TestClient, md) -> None:
    response = api.post("/api/deliveries", json=delivery_body(md, source_location_id=md.other_loc))
    assert response.status_code == 422 and "does not belong" in response.json()["detail"]


@pytest.mark.parametrize(
    "lines",
    [[], [{"product_id": 1, "quantity": 0}], [{"product_id": 1, "quantity": -1}],
     [{"product_id": 1, "quantity": 0.0005}],
     [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 1}]],
    ids=["empty", "zero", "negative", "too-precise", "duplicate-product"],
)
def test_invalid_lines(api: TestClient, md, lines) -> None:
    assert api.post("/api/deliveries", json=delivery_body(md, lines=lines)).status_code == 422


# --- Workflow: todo / WAITING -----------------------------------------------


def test_todo_with_enough_stock_is_ready(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    assert todo(api, create(api, md))["status"] == "READY"
    assert stock_qty(db, md.p1, md.loc_a) == 100  # todo never moves stock


def test_todo_without_enough_stock_is_waiting(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 5)
    assert todo(api, create(api, md))["status"] == "WAITING"
    assert todo(api, create(api, md, source_location_id=md.loc_b))["status"] == "WAITING"


def test_every_line_must_be_covered(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = create(api, md, lines=[{"product_id": md.p1, "quantity": 20},
                                      {"product_id": md.p2, "quantity": 1}])
    assert todo(api, delivery)["status"] == "WAITING"


def test_waiting_rechecks_on_todo(api: TestClient, db: Session, md) -> None:
    delivery = todo(api, create(api, md))
    assert delivery["status"] == "WAITING"
    assert todo(api, delivery)["status"] == "WAITING"
    put_stock(db, md, md.p1, md.loc_a, 20)
    assert todo(api, delivery)["status"] == "READY"


def test_receipt_promotes_waiting_deliveries(api: TestClient, db: Session, md) -> None:
    waiting = todo(api, create(api, md))
    elsewhere = todo(api, create(api, md, source_location_id=md.loc_b))
    receipt = api.post("/api/receipts", json={
        "warehouse_id": md.wh, "destination_location_id": md.loc_a,
        "schedule_date": "2026-10-01", "lines": [{"product_id": md.p1, "quantity": 20}],
    }).json()
    api.post(f"/api/receipts/{receipt['id']}/todo")
    assert api.post(f"/api/receipts/{receipt['id']}/validate").status_code == 200
    assert status_of(api, waiting) == "READY"
    assert status_of(api, elsewhere) == "WAITING"  # other location: unaffected


@pytest.mark.parametrize("status_setup", ["waiting", "ready"])
def test_only_drafts_can_be_edited(api: TestClient, db: Session, md, status_setup) -> None:
    if status_setup == "ready":
        put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = todo(api, create(api, md))
    response = api.put(f"/api/deliveries/{delivery['id']}", json={"schedule_date": "2027-01-01"})
    assert response.status_code == 409


def test_validate_requires_ready(api: TestClient, db: Session, md) -> None:
    draft = create(api, md)
    assert validate(api, draft).status_code == 409
    waiting = todo(api, create(api, md))
    assert validate(api, waiting).status_code == 409
    assert movements(db) == []


def test_todo_on_ready_is_rejected(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = todo(api, create(api, md))
    assert api.post(f"/api/deliveries/{delivery['id']}/todo").status_code == 409


# --- Validate ---------------------------------------------------------------


def test_validate_delivers_and_creates_out_movement(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = todo(api, create(api, md))
    response = validate(api, delivery)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DONE" and response.json()["lines"]

    assert stock_qty(db, md.p1, md.loc_a) == 80
    [out] = out_movements(db)
    assert (out.product_id, out.quantity, out.from_location_id, out.to_location_id) == (
        md.p1, 20, md.loc_a, None,
    )
    assert (out.reference, out.source_type, out.source_id, out.performed_by) == (
        "WH/OUT/0001", "delivery", delivery["id"], md.user,
    )


def test_multi_line_delivery(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    put_stock(db, md, md.p2, md.loc_a, 10)
    delivery = todo(api, create(api, md, lines=[{"product_id": md.p2, "quantity": 10},
                                                {"product_id": md.p1, "quantity": 30}]))
    assert validate(api, delivery).json()["status"] == "DONE"
    assert stock_qty(db, md.p1, md.loc_a) == 70 and stock_qty(db, md.p2, md.loc_a) == 0
    assert len(out_movements(db)) == 2


def test_insufficient_stock_at_validation_moves_to_waiting(
    api: TestClient, db: Session, md
) -> None:
    """Blueprint section 6: if insufficient, status = WAITING and stock is not touched."""
    put_stock(db, md, md.p1, md.loc_a, 30)
    first = todo(api, create(api, md))
    second = todo(api, create(api, md))  # both READY against the same 30 (nothing reserved)
    assert validate(api, first).json()["status"] == "DONE"  # 30 -> 10

    response = validate(api, second)
    assert response.status_code == 200 and response.json()["status"] == "WAITING"
    assert stock_qty(db, md.p1, md.loc_a) == 10
    assert len(out_movements(db)) == 1


def test_delivery_never_uses_reserved_stock(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 25, reserved=10)  # free 15 < 20
    delivery = todo(api, create(api, md))
    assert delivery["status"] == "WAITING"

    exact = todo(api, create(api, md, lines=[{"product_id": md.p1, "quantity": 15}]))
    assert exact["status"] == "READY"
    assert validate(api, exact).json()["status"] == "DONE"
    assert stock_qty(db, md.p1, md.loc_a) == 10  # the reserved 10 remain


def test_reservation_made_after_ready_blocks_validation(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 20)
    delivery = todo(api, create(api, md))
    assert delivery["status"] == "READY"
    put_stock(db, md, md.p1, md.loc_a, 5, reserved=10)  # 25 on hand, 15 free
    assert validate(api, delivery).json()["status"] == "WAITING"
    assert stock_qty(db, md.p1, md.loc_a) == 25


def test_multi_line_shortage_rolls_back_every_line(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    put_stock(db, md, md.p2, md.loc_a, 10)
    delivery = todo(api, create(api, md, lines=[{"product_id": md.p1, "quantity": 30},
                                                {"product_id": md.p2, "quantity": 10}]))
    # p1 (lower id) is delivered first; then p2 runs short.
    put_stock(db, md, md.p2, md.loc_a, 1, reserved=5)
    assert validate(api, delivery).json()["status"] == "WAITING"
    assert stock_qty(db, md.p1, md.loc_a) == 100 and stock_qty(db, md.p2, md.loc_a) == 11
    assert out_movements(db) == []


def test_archived_product_blocks_validation(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = todo(api, create(api, md))
    archive(db, Product, md.p1)
    assert validate(api, delivery).status_code == 422
    assert status_of(api, delivery) == "READY" and stock_qty(db, md.p1, md.loc_a) == 100


def test_archived_location_blocks_validation(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = todo(api, create(api, md))
    archive(db, Location, md.loc_a)
    assert validate(api, delivery).status_code == 422
    assert stock_qty(db, md.p1, md.loc_a) == 100 and out_movements(db) == []


# --- Completed and cancelled deliveries -------------------------------------


def test_done_delivery_is_immutable(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = todo(api, create(api, md))
    validate(api, delivery)
    did = delivery["id"]
    assert validate(api, delivery).status_code == 409  # never delivered twice
    assert api.post(f"/api/deliveries/{did}/cancel").status_code == 409  # no silent reversal
    assert api.post(f"/api/deliveries/{did}/todo").status_code == 409
    assert api.put(f"/api/deliveries/{did}", json={"schedule_date": "2027-01-01"}).status_code == 409
    assert stock_qty(db, md.p1, md.loc_a) == 80 and len(out_movements(db)) == 1


@pytest.mark.parametrize("setup", ["draft", "waiting", "ready"])
def test_cancel(api: TestClient, db: Session, md, setup) -> None:
    if setup == "ready":
        put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = create(api, md)
    if setup != "draft":
        delivery = todo(api, delivery)
    before = stock_qty(db, md.p1, md.loc_a)

    response = api.post(f"/api/deliveries/{delivery['id']}/cancel")
    assert response.status_code == 200 and response.json()["status"] == "CANCELED"
    assert stock_qty(db, md.p1, md.loc_a) == before and out_movements(db) == []
    for action in ("cancel", "todo", "validate"):
        assert api.post(f"/api/deliveries/{delivery['id']}/{action}").status_code == 409


def test_canceled_delivery_is_not_promoted(api: TestClient, db: Session, md) -> None:
    delivery = todo(api, create(api, md))  # WAITING
    api.post(f"/api/deliveries/{delivery['id']}/cancel")
    put_stock(db, md, md.p1, md.loc_a, 100)
    from app.services.delivery_service import promote_waiting_deliveries

    assert promote_waiting_deliveries(db, md.loc_a) == []
    assert status_of(api, delivery) == "CANCELED"
