"""Inventory adjustment API tests (SQLite, through the HTTP API as the operations UI uses it)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Location, MovementType, Product
from app.services import adjustment_service
from tests.operation_fixtures import (  # noqa: F401 (fixtures)
    api,
    archive,
    md,
    movements,
    put_stock,
    stock_qty,
)


def adjustment_body(md, lines=None, **overrides) -> dict:
    return {
        "location_id": md.loc_a,
        "reason": "Cycle count",
        "lines": lines if lines is not None else [{"product_id": md.p1, "counted_quantity": 7}],
    } | overrides


def create(api: TestClient, md, **overrides) -> dict:
    response = api.post("/api/adjustments", json=adjustment_body(md, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def validate(api: TestClient, adjustment: dict):
    return api.post(f"/api/adjustments/{adjustment['id']}/validate")


def adjustment_movements(db: Session):
    return [m for m in movements(db) if m.movement_type is MovementType.ADJUSTMENT]


def line_values(body: dict) -> list[tuple]:
    return [(l["product_id"], Decimal(l["counted_quantity"]), Decimal(l["system_quantity"]),
             Decimal(l["difference"])) for l in body["lines"]]


# --- Create / read / update -------------------------------------------------


def test_create_draft_with_backend_snapshot(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    body = create(api, md)
    assert body["status"] == "DRAFT" and body["reference"] == "WH/ADJ/0001"
    assert body["location_id"] == md.loc_a and body["reason"] == "Cycle count"
    assert body["created_at"] and body["updated_at"]
    assert line_values(body) == [(md.p1, 7, 10, -3)]
    assert body["lines"][0]["product"]["sku"] == "W1"
    assert stock_qty(db, md.p1, md.loc_a) == 10 and adjustment_movements(db) == []


def test_snapshot_is_zero_without_stock(api: TestClient, md) -> None:
    assert line_values(create(api, md))[0][2:] == (0, 7)


def test_list_newest_first_with_filters(api: TestClient, db: Session, md) -> None:
    first = create(api, md)
    second = create(api, md)
    validate(api, second)
    assert [a["id"] for a in api.get("/api/adjustments").json()] == [second["id"], first["id"]]
    assert [a["id"] for a in api.get("/api/adjustments", params={"status": "DONE"}).json()] == [
        second["id"]
    ]
    assert [a["id"] for a in api.get("/api/adjustments", params={"search": "ADJ/0001"}).json()] == [
        first["id"]
    ]


def test_get_detail(api: TestClient, md) -> None:
    adjustment = create(api, md)
    assert api.get(f"/api/adjustments/{adjustment['id']}").json() == adjustment
    assert api.get("/api/adjustments/999").status_code == 404


def test_update_draft_refreshes_snapshot(api: TestClient, db: Session, md) -> None:
    adjustment = create(api, md)
    put_stock(db, md, md.p1, md.loc_b, 4)
    response = api.put(f"/api/adjustments/{adjustment['id']}", json={
        "location_id": md.loc_b,
        "reason": None,
        "lines": [{"product_id": md.p1, "counted_quantity": 6},
                  {"product_id": md.p2, "counted_quantity": 0}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["location_id"] == md.loc_b and body["reason"] is None
    assert line_values(body) == [(md.p1, 6, 4, 2), (md.p2, 0, 0, 0)]


def test_update_without_lines_refreshes_snapshot_for_new_location(
    api: TestClient, db: Session, md
) -> None:
    adjustment = create(api, md)  # loc_a, no stock -> system 0
    put_stock(db, md, md.p1, md.loc_b, 9)
    body = api.put(f"/api/adjustments/{adjustment['id']}", json={"location_id": md.loc_b}).json()
    assert line_values(body) == [(md.p1, 7, 9, -2)]


def test_blank_reason_is_stored_as_null(api: TestClient, md) -> None:
    assert create(api, md, reason="  ")["reason"] is None
    body = adjustment_body(md)
    del body["reason"]
    assert api.post("/api/adjustments", json=body).json()["reason"] is None  # optional


@pytest.mark.parametrize("field", ["location_id", "lines"])
def test_update_cannot_null_required_fields(api: TestClient, md, field) -> None:
    adjustment = create(api, md)
    assert api.put(f"/api/adjustments/{adjustment['id']}", json={field: None}).status_code == 422


# --- The backend owns system quantity and difference ------------------------


@pytest.mark.parametrize("field", ["system_quantity", "difference", "quantity"])
def test_frontend_cannot_send_system_quantity_or_difference(api: TestClient, md, field) -> None:
    lines = [{"product_id": md.p1, "counted_quantity": 7, field: 999}]
    assert api.post("/api/adjustments", json=adjustment_body(md, lines=lines)).status_code == 422
    adjustment = create(api, md)
    assert api.put(f"/api/adjustments/{adjustment['id']}", json={"lines": lines}).status_code == 422


@pytest.mark.parametrize("field", ["status", "reference", "system_quantity"])
def test_backend_owned_document_fields_are_rejected(api: TestClient, md, field) -> None:
    assert api.post("/api/adjustments", json=adjustment_body(md, **{field: 1})).status_code == 422


def test_difference_is_computed_from_stock_at_validation(api: TestClient, db: Session, md) -> None:
    """Stock changes after the draft was saved: the stale snapshot is ignored."""
    put_stock(db, md, md.p1, md.loc_a, 10)
    adjustment = create(api, md)  # snapshot: system 10, difference -3
    put_stock(db, md, md.p1, md.loc_a, 5)  # now 15
    body = validate(api, adjustment).json()
    assert body["status"] == "DONE"
    assert line_values(body) == [(md.p1, 7, 15, -8)]  # recomputed and stored as applied
    assert stock_qty(db, md.p1, md.loc_a) == 7
    [movement] = adjustment_movements(db)
    assert movement.quantity == -8


# --- Validate ---------------------------------------------------------------


def test_negative_adjustment(api: TestClient, db: Session, md) -> None:
    """Blueprint example: stock 10, counted 7 -> difference -3 -> stock 7."""
    put_stock(db, md, md.p1, md.loc_a, 10)
    adjustment = create(api, md)
    response = validate(api, adjustment)
    assert response.status_code == 200 and response.json()["status"] == "DONE"
    assert stock_qty(db, md.p1, md.loc_a) == 7
    [movement] = adjustment_movements(db)
    assert (movement.quantity, movement.from_location_id, movement.to_location_id) == (
        -3, None, md.loc_a,
    )
    assert (movement.reference, movement.source_type, movement.source_id, movement.performed_by) == (
        "WH/ADJ/0001", "adjustment", adjustment["id"], md.user,
    )


def test_positive_adjustment(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    validate(api, create(api, md, lines=[{"product_id": md.p1, "counted_quantity": 12.5}]))
    assert stock_qty(db, md.p1, md.loc_a) == Decimal("12.5")
    assert adjustment_movements(db)[0].quantity == Decimal("2.5")


def test_positive_adjustment_creates_missing_stock(api: TestClient, db: Session, md) -> None:
    validate(api, create(api, md, lines=[{"product_id": md.p2, "counted_quantity": 4}]))
    assert stock_qty(db, md.p2, md.loc_a) == 4


def test_counted_zero_empties_the_stock(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    body = validate(api, create(api, md, lines=[{"product_id": md.p1, "counted_quantity": 0}])).json()
    assert body["status"] == "DONE" and line_values(body) == [(md.p1, 0, 10, -10)]
    assert stock_qty(db, md.p1, md.loc_a) == 0


def test_count_equal_to_stock_creates_no_movement(api: TestClient, db: Session, md) -> None:
    """StockMovement forbids a zero quantity, so a matching count is recorded on
    the line only."""
    put_stock(db, md, md.p1, md.loc_a, 10)
    body = validate(api, create(api, md, lines=[{"product_id": md.p1, "counted_quantity": 10},
                                                {"product_id": md.p2, "counted_quantity": 0}])).json()
    assert body["status"] == "DONE"
    assert line_values(body) == [(md.p1, 10, 10, 0), (md.p2, 0, 0, 0)]
    assert adjustment_movements(db) == [] and stock_qty(db, md.p1, md.loc_a) == 10


def test_multi_line_adjustment(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    put_stock(db, md, md.p2, md.loc_a, 3)
    validate(api, create(api, md, lines=[{"product_id": md.p2, "counted_quantity": 5},
                                         {"product_id": md.p1, "counted_quantity": 8}]))
    assert stock_qty(db, md.p1, md.loc_a) == 8 and stock_qty(db, md.p2, md.loc_a) == 5
    assert sorted(m.quantity for m in adjustment_movements(db)) == [-2, 2]


def test_count_below_reserved_is_rejected(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10, reserved=8)
    adjustment = create(api, md)  # counted 7 < reserved 8
    response = validate(api, adjustment)
    assert response.status_code == 409 and "reserved" in response.json()["detail"]
    assert stock_qty(db, md.p1, md.loc_a) == 10 and adjustment_movements(db) == []
    assert api.get(f"/api/adjustments/{adjustment['id']}").json()["status"] == "DRAFT"


def test_count_equal_to_reserved_is_allowed(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10, reserved=7)
    assert validate(api, create(api, md)).json()["status"] == "DONE"
    assert stock_qty(db, md.p1, md.loc_a) == 7


def test_multi_line_failure_rolls_back_every_line(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    put_stock(db, md, md.p2, md.loc_a, 10, reserved=9)
    adjustment = create(api, md, lines=[{"product_id": md.p1, "counted_quantity": 4},
                                        {"product_id": md.p2, "counted_quantity": 5}])  # p2 < reserved
    assert validate(api, adjustment).status_code == 409
    assert stock_qty(db, md.p1, md.loc_a) == 10 and stock_qty(db, md.p2, md.loc_a) == 10
    assert adjustment_movements(db) == []
    body = api.get(f"/api/adjustments/{adjustment['id']}").json()
    assert body["status"] == "DRAFT" and line_values(body)[0] == (md.p1, 4, 10, -6)  # snapshot kept


def test_stock_appearing_mid_validation_is_detected(
    api: TestClient, db: Session, md, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the stock read and the engine's lock disagree (a row created in between),
    nothing is applied and the caller is asked to retry."""
    put_stock(db, md, md.p1, md.loc_a, 10)
    adjustment = create(api, md)
    monkeypatch.setattr(adjustment_service, "_system_quantity",
                        lambda db, p, l, *, lock: Decimal("0"))  # pretend no row was seen
    response = validate(api, adjustment)
    assert response.status_code == 409 and "validate again" in response.json()["detail"]
    assert stock_qty(db, md.p1, md.loc_a) == 10 and adjustment_movements(db) == []


def test_adjustment_promotes_waiting_deliveries(api: TestClient, db: Session, md) -> None:
    delivery = api.post("/api/deliveries", json={
        "warehouse_id": md.wh, "source_location_id": md.loc_a, "schedule_date": "2026-10-05",
        "lines": [{"product_id": md.p1, "quantity": 5}],
    }).json()
    assert api.post(f"/api/deliveries/{delivery['id']}/todo").json()["status"] == "WAITING"
    validate(api, create(api, md))  # counted 7 at loc_a
    assert api.get(f"/api/deliveries/{delivery['id']}").json()["status"] == "READY"


# --- Reference / quantity validation ----------------------------------------


@pytest.mark.parametrize(
    "overrides, detail",
    [({"location_id": 999}, "location_id does not exist"),
     ({"lines": [{"product_id": 999, "counted_quantity": 1}]}, "Product 999 does not exist")],
    ids=["location", "product"],
)
def test_invalid_references(api: TestClient, md, overrides, detail) -> None:
    response = api.post("/api/adjustments", json=adjustment_body(md, **overrides))
    assert response.status_code == 422 and response.json()["detail"] == detail


def test_archived_location_or_product_rejected(api: TestClient, md) -> None:
    assert api.post("/api/adjustments", json=adjustment_body(
        md, location_id=md.archived_loc)).status_code == 422
    assert api.post("/api/adjustments", json=adjustment_body(
        md, lines=[{"product_id": md.archived_product, "counted_quantity": 1}])).status_code == 422


@pytest.mark.parametrize("model, key", [(Location, "loc_a"), (Product, "p1")])
def test_archived_after_draft_blocks_validation(api: TestClient, db: Session, md, model, key) -> None:
    adjustment = create(api, md)
    archive(db, model, getattr(md, key))
    assert validate(api, adjustment).status_code == 422
    assert adjustment_movements(db) == []


@pytest.mark.parametrize(
    "lines",
    [[], [{"product_id": 1, "counted_quantity": -1}],
     [{"product_id": 1, "counted_quantity": 1.0001}],
     [{"product_id": 1, "counted_quantity": "x"}], [{"product_id": 1}],
     [{"product_id": 1, "counted_quantity": 1}, {"product_id": 1, "counted_quantity": 2}]],
    ids=["empty", "negative", "too-precise", "not-a-number", "missing", "duplicate-product"],
)
def test_invalid_lines(api: TestClient, md, lines) -> None:
    assert api.post("/api/adjustments", json=adjustment_body(md, lines=lines)).status_code == 422


# --- Completed adjustments --------------------------------------------------


def test_completed_adjustment_cannot_be_changed(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    adjustment = create(api, md)
    validate(api, adjustment)
    assert api.put(f"/api/adjustments/{adjustment['id']}", json={
        "lines": [{"product_id": md.p1, "counted_quantity": 1}]}).status_code == 409
    assert validate(api, adjustment).status_code == 409  # never applied twice
    assert stock_qty(db, md.p1, md.loc_a) == 7 and len(adjustment_movements(db)) == 1


def test_no_todo_or_cancel_endpoints(api: TestClient, md) -> None:
    adjustment = create(api, md)
    for action in ("todo", "cancel"):
        assert api.post(f"/api/adjustments/{adjustment['id']}/{action}").status_code in (404, 405)


def test_validate_missing_adjustment(api: TestClient, md) -> None:
    assert api.post("/api/adjustments/999/validate").status_code == 404
