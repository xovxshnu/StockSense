"""Receipt API tests (SQLite, through the HTTP API as the operations UI uses it)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Location, MovementType, Product
from app.services import inventory_service
from tests.operation_fixtures import (  # noqa: F401 (fixtures)
    api,
    archive,
    md,
    movements,
    receipt_body,
    stock_qty,
)


def create(api: TestClient, md, **overrides) -> dict:
    response = api.post("/api/receipts", json=receipt_body(md, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def ready(api: TestClient, md, **overrides) -> dict:
    receipt = create(api, md, **overrides)
    response = api.post(f"/api/receipts/{receipt['id']}/todo")
    assert response.status_code == 200, response.text
    return response.json()


# --- Create / read / update -------------------------------------------------


def test_create_draft(api: TestClient, md) -> None:
    body = create(api, md)
    assert body["status"] == "DRAFT"
    assert body["reference"] == "WH/IN/0001"
    assert (body["supplier_id"], body["warehouse_id"], body["destination_location_id"]) == (
        md.supplier, md.wh, md.loc_a,
    )
    assert body["schedule_date"] == "2026-10-01" and body["responsible_user_id"] is None
    assert body["created_at"] and body["updated_at"]
    [line] = body["lines"]
    assert line["product_id"] == md.p1 and Decimal(line["quantity"]) == 100
    assert line["product"] == {"id": md.p1, "sku": "W1", "name": "Widget", "uom": "Unit"}


def test_create_does_not_touch_stock(api: TestClient, db: Session, md) -> None:
    create(api, md)
    assert stock_qty(db, md.p1, md.loc_a) is None and movements(db) == []


def test_references_are_sequential_and_failed_creates_use_none(api: TestClient, md) -> None:
    assert create(api, md)["reference"] == "WH/IN/0001"
    bad = api.post("/api/receipts", json=receipt_body(md, destination_location_id=999))
    assert bad.status_code == 422
    assert create(api, md)["reference"] == "WH/IN/0002"


def test_list_newest_first_with_filters(api: TestClient, md) -> None:
    first = create(api, md)
    second = ready(api, md)
    listed = api.get("/api/receipts").json()
    assert [r["id"] for r in listed] == [second["id"], first["id"]]
    assert all("lines" in r for r in listed)
    assert [r["id"] for r in api.get("/api/receipts", params={"status": "READY"}).json()] == [
        second["id"]
    ]
    assert [r["id"] for r in api.get("/api/receipts", params={"search": "in/0001"}).json()] == [
        first["id"]
    ]
    assert api.get("/api/receipts", params={"search": "%"}).json() == []
    assert api.get("/api/receipts", params={"status": "bogus"}).status_code == 422


def test_get_detail(api: TestClient, md) -> None:
    receipt = create(api, md)
    response = api.get(f"/api/receipts/{receipt['id']}")
    assert response.status_code == 200 and response.json() == receipt
    assert api.get("/api/receipts/999").status_code == 404


def test_update_draft_replaces_fields_and_lines(api: TestClient, md) -> None:
    receipt = create(api, md, responsible_user_id=md.user)
    response = api.put(f"/api/receipts/{receipt['id']}", json={
        "schedule_date": "2026-11-05",
        "destination_location_id": md.loc_b,
        "supplier_id": None,
        "lines": [{"product_id": md.p1, "quantity": 7}, {"product_id": md.p2, "quantity": 3.5}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schedule_date"] == "2026-11-05" and body["destination_location_id"] == md.loc_b
    assert body["supplier_id"] is None and body["responsible_user_id"] == md.user  # untouched
    assert [(l["product_id"], Decimal(l["quantity"])) for l in body["lines"]] == [
        (md.p1, 7), (md.p2, Decimal("3.5")),
    ]
    assert body["reference"] == receipt["reference"]


def test_update_accepts_the_frontend_round_trip(api: TestClient, md) -> None:
    """The UI sends back every domain field it received, unchanged."""
    receipt = create(api, md)
    payload = {k: receipt[k] for k in ("warehouse_id", "destination_location_id",
                                       "schedule_date", "supplier_id", "responsible_user_id")}
    payload["lines"] = [{"product_id": l["product_id"], "quantity": float(l["quantity"])}
                        for l in receipt["lines"]]
    response = api.put(f"/api/receipts/{receipt['id']}", json=payload)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("field", ["warehouse_id", "destination_location_id",
                                   "schedule_date", "lines"])
def test_update_cannot_null_required_fields(api: TestClient, md, field) -> None:
    receipt = create(api, md)
    assert api.put(f"/api/receipts/{receipt['id']}", json={field: None}).status_code == 422


@pytest.mark.parametrize("field", ["status", "reference", "id", "created_at"])
def test_backend_owned_fields_are_rejected(api: TestClient, md, field) -> None:
    assert api.post("/api/receipts", json=receipt_body(md, **{field: "x"})).status_code == 422
    receipt = create(api, md)
    assert api.put(f"/api/receipts/{receipt['id']}", json={field: "x"}).status_code == 422


def test_update_missing_receipt(api: TestClient, md) -> None:
    assert api.put("/api/receipts/999", json={"schedule_date": "2026-01-01"}).status_code == 404


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/receipts").status_code == 401
    assert client.post("/api/receipts/1/validate").status_code == 401


# --- Reference validation ---------------------------------------------------


def test_invalid_product(api: TestClient, md) -> None:
    response = api.post("/api/receipts", json=receipt_body(
        md, lines=[{"product_id": 999, "quantity": 1}]))
    assert response.status_code == 422 and response.json()["detail"] == "Product 999 does not exist"


def test_archived_product(api: TestClient, md) -> None:
    response = api.post("/api/receipts", json=receipt_body(
        md, lines=[{"product_id": md.archived_product, "quantity": 1}]))
    assert response.status_code == 422 and "archived" in response.json()["detail"]


@pytest.mark.parametrize(
    "overrides, detail",
    [
        ({"destination_location_id": 999}, "destination_location_id does not exist"),
        ({"warehouse_id": 999}, "warehouse_id does not exist"),
    ],
)
def test_invalid_location_or_warehouse(api: TestClient, md, overrides, detail) -> None:
    response = api.post("/api/receipts", json=receipt_body(md, **overrides))
    assert response.status_code == 422 and response.json()["detail"] == detail


def test_archived_location(api: TestClient, md) -> None:
    response = api.post("/api/receipts", json=receipt_body(
        md, destination_location_id=md.archived_loc))
    assert response.status_code == 422
    assert response.json()["detail"] == "destination_location_id is archived"


def test_location_must_belong_to_warehouse(api: TestClient, md) -> None:
    response = api.post("/api/receipts", json=receipt_body(
        md, destination_location_id=md.other_loc))
    assert response.status_code == 422 and "does not belong" in response.json()["detail"]


def test_supplier_must_be_a_supplier_contact(api: TestClient, md) -> None:
    response = api.post("/api/receipts", json=receipt_body(md, supplier_id=md.customer))
    assert response.status_code == 422 and "supplier" in response.json()["detail"]
    assert api.post("/api/receipts", json=receipt_body(md, supplier_id=999)).status_code == 422


def test_supplier_is_optional(api: TestClient, md) -> None:
    body = receipt_body(md)
    del body["supplier_id"]
    assert api.post("/api/receipts", json=body).status_code == 201


def test_responsible_user_must_exist(api: TestClient, md) -> None:
    assert api.post("/api/receipts", json=receipt_body(
        md, responsible_user_id=999)).status_code == 422


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [{"product_id": 1, "quantity": 0}],
        [{"product_id": 1, "quantity": -5}],
        [{"product_id": 1, "quantity": 1.0001}],
        [{"product_id": 1, "quantity": "abc"}],
        [{"product_id": 1}],
        [{"product_id": 1, "quantity": 1, "unit_cost": 3}],
        [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 2}],  # duplicate
    ],
    ids=["empty", "zero", "negative", "too-precise", "not-a-number", "missing", "extra",
         "duplicate-product"],
)
def test_invalid_lines(api: TestClient, md, lines) -> None:
    assert api.post("/api/receipts", json=receipt_body(md, lines=lines)).status_code == 422


# --- Workflow ---------------------------------------------------------------


def test_todo_moves_draft_to_ready(api: TestClient, md) -> None:
    assert ready(api, md)["status"] == "READY"


def test_validate_receives_stock_and_creates_in_movements(
    api: TestClient, db: Session, md
) -> None:
    receipt = ready(api, md, lines=[{"product_id": md.p1, "quantity": 100},
                                    {"product_id": md.p2, "quantity": 50}])
    response = api.post(f"/api/receipts/{receipt['id']}/validate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DONE" and len(body["lines"]) == 2  # full document returned

    assert stock_qty(db, md.p1, md.loc_a) == 100 and stock_qty(db, md.p2, md.loc_a) == 50
    assert [(m.movement_type, m.product_id, m.quantity, m.from_location_id, m.to_location_id)
            for m in movements(db)] == [
        (MovementType.IN, md.p1, 100, None, md.loc_a),
        (MovementType.IN, md.p2, 50, None, md.loc_a),
    ]
    for m in movements(db):
        assert (m.reference, m.source_type, m.source_id, m.performed_by) == (
            "WH/IN/0001", "receipt", receipt["id"], md.user,
        )


def test_validate_adds_to_existing_stock(api: TestClient, db: Session, md) -> None:
    for _ in range(2):
        receipt = ready(api, md)
        assert api.post(f"/api/receipts/{receipt['id']}/validate").status_code == 200
    assert stock_qty(db, md.p1, md.loc_a) == 200


def test_validate_requires_ready(api: TestClient, db: Session, md) -> None:
    receipt = create(api, md)
    response = api.post(f"/api/receipts/{receipt['id']}/validate")
    assert response.status_code == 409 and "DRAFT" in response.json()["detail"]
    assert stock_qty(db, md.p1, md.loc_a) is None


def test_todo_requires_draft(api: TestClient, md) -> None:
    receipt = ready(api, md)
    assert api.post(f"/api/receipts/{receipt['id']}/todo").status_code == 409


def test_todo_rechecks_references(api: TestClient, db: Session, md) -> None:
    receipt = create(api, md)
    archive(db, Product, md.p1)
    assert api.post(f"/api/receipts/{receipt['id']}/todo").status_code == 422
    assert api.get(f"/api/receipts/{receipt['id']}").json()["status"] == "DRAFT"


def test_only_drafts_can_be_edited(api: TestClient, md) -> None:
    receipt = ready(api, md)
    response = api.put(f"/api/receipts/{receipt['id']}", json={"schedule_date": "2027-01-01"})
    assert response.status_code == 409


def test_workflow_actions_on_missing_receipt(api: TestClient, md) -> None:
    for action in ("todo", "validate", "cancel"):
        assert api.post(f"/api/receipts/999/{action}").status_code == 404


# --- All or nothing ---------------------------------------------------------


def test_line_failure_rolls_back_every_line(api: TestClient, db: Session, md) -> None:
    receipt = ready(api, md, lines=[{"product_id": md.p1, "quantity": 100},
                                    {"product_id": md.p2, "quantity": 50}])
    archive(db, Product, md.p2)  # line 2 now fails
    response = api.post(f"/api/receipts/{receipt['id']}/validate")
    assert response.status_code == 422
    assert stock_qty(db, md.p1, md.loc_a) is None and stock_qty(db, md.p2, md.loc_a) is None
    assert movements(db) == []
    assert api.get(f"/api/receipts/{receipt['id']}").json()["status"] == "READY"


def test_failure_after_a_line_was_applied_rolls_it_back(
    api: TestClient, db: Session, md, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line 1 really changes stock in the session before line 2 blows up."""
    receipt = ready(api, md, lines=[{"product_id": md.p1, "quantity": 100},
                                    {"product_id": md.p2, "quantity": 50}])
    real_receive = inventory_service.receive
    calls = []

    def receive_then_fail(db, **kwargs):
        calls.append(kwargs["product_id"])
        if len(calls) == 2:
            raise inventory_service.InventoryError("simulated failure on line 2")
        return real_receive(db, **kwargs)

    monkeypatch.setattr(inventory_service, "receive", receive_then_fail)
    response = api.post(f"/api/receipts/{receipt['id']}/validate")
    assert response.status_code == 409 and calls == [md.p1, md.p2]

    assert stock_qty(db, md.p1, md.loc_a) is None and movements(db) == []
    assert api.get(f"/api/receipts/{receipt['id']}").json()["status"] == "READY"


def test_archived_destination_blocks_validation(api: TestClient, db: Session, md) -> None:
    receipt = ready(api, md)
    archive(db, Location, md.loc_a)
    assert api.post(f"/api/receipts/{receipt['id']}/validate").status_code == 422
    assert movements(db) == []


# --- Completed and cancelled receipts ---------------------------------------


def test_done_receipt_is_immutable(api: TestClient, db: Session, md) -> None:
    receipt = ready(api, md)
    api.post(f"/api/receipts/{receipt['id']}/validate")
    rid = receipt["id"]
    assert api.put(f"/api/receipts/{rid}", json={
        "lines": [{"product_id": md.p1, "quantity": 5}]}).status_code == 409
    assert api.post(f"/api/receipts/{rid}/validate").status_code == 409  # not twice
    assert api.post(f"/api/receipts/{rid}/todo").status_code == 409
    assert api.post(f"/api/receipts/{rid}/cancel").status_code == 409  # no silent reversal
    assert stock_qty(db, md.p1, md.loc_a) == 100 and len(movements(db)) == 1
    assert api.get(f"/api/receipts/{rid}").json()["lines"][0]["quantity"] == "100.000"


@pytest.mark.parametrize("make", [create, ready], ids=["draft", "ready"])
def test_cancel(api: TestClient, db: Session, md, make) -> None:
    receipt = make(api, md)
    response = api.post(f"/api/receipts/{receipt['id']}/cancel")
    assert response.status_code == 200 and response.json()["status"] == "CANCELED"
    assert stock_qty(db, md.p1, md.loc_a) is None and movements(db) == []
    for action in ("cancel", "todo", "validate"):
        assert api.post(f"/api/receipts/{receipt['id']}/{action}").status_code == 409
    assert api.put(f"/api/receipts/{receipt['id']}", json={
        "schedule_date": "2027-01-01"}).status_code == 409
