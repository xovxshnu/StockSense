"""Internal transfer API tests (SQLite, through the HTTP API as the operations UI uses it)."""

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
    put_stock,
    stock_qty,
)


def transfer_body(md, lines=None, **overrides) -> dict:
    return {
        "from_location_id": md.loc_a,
        "to_location_id": md.loc_b,
        "schedule_date": "2026-10-03",
        "lines": lines if lines is not None else [{"product_id": md.p1, "quantity": 30}],
    } | overrides


def create(api: TestClient, md, **overrides) -> dict:
    response = api.post("/api/transfers", json=transfer_body(md, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def act(api: TestClient, transfer: dict, action: str):
    return api.post(f"/api/transfers/{transfer['id']}/{action}")


def ready(api: TestClient, md, **overrides) -> dict:
    response = act(api, create(api, md, **overrides), "todo")
    assert response.status_code == 200, response.text
    return response.json()


def status_of(api: TestClient, transfer: dict) -> str:
    return api.get(f"/api/transfers/{transfer['id']}").json()["status"]


def transfer_movements(db: Session):
    return [m for m in movements(db) if m.movement_type is MovementType.TRANSFER]


# --- Create / read / update -------------------------------------------------


def test_create_draft(api: TestClient, db: Session, md) -> None:
    body = create(api, md)
    assert body["status"] == "DRAFT" and body["reference"] == "WH/INT/0001"
    assert (body["from_location_id"], body["to_location_id"]) == (md.loc_a, md.loc_b)
    assert body["schedule_date"] == "2026-10-03" and body["responsible_user_id"] is None
    assert body["created_at"] and body["updated_at"]
    [line] = body["lines"]
    assert line["product"]["sku"] == "W1" and Decimal(line["quantity"]) == 30
    assert movements(db) == []


def test_references_are_sequential_and_failed_creates_use_none(api: TestClient, md) -> None:
    assert create(api, md)["reference"] == "WH/INT/0001"
    assert api.post("/api/transfers", json=transfer_body(md, to_location_id=999)).status_code == 422
    assert create(api, md)["reference"] == "WH/INT/0002"


def test_list_newest_first_with_filters(api: TestClient, md) -> None:
    first = create(api, md)
    second = ready(api, md)
    assert [t["id"] for t in api.get("/api/transfers").json()] == [second["id"], first["id"]]
    assert [t["id"] for t in api.get("/api/transfers", params={"status": "READY"}).json()] == [
        second["id"]
    ]
    assert [t["id"] for t in api.get("/api/transfers", params={"search": "INT/0001"}).json()] == [
        first["id"]
    ]


def test_get_detail(api: TestClient, md) -> None:
    transfer = create(api, md)
    assert api.get(f"/api/transfers/{transfer['id']}").json() == transfer
    assert api.get("/api/transfers/999").status_code == 404


def test_update_draft(api: TestClient, md) -> None:
    transfer = create(api, md)
    response = api.put(f"/api/transfers/{transfer['id']}", json={
        "to_location_id": md.other_loc,  # another warehouse is allowed
        "schedule_date": "2026-12-01",
        "lines": [{"product_id": md.p1, "quantity": 5}, {"product_id": md.p2, "quantity": 2}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["to_location_id"] == md.other_loc and body["schedule_date"] == "2026-12-01"
    assert [(l["product_id"], Decimal(l["quantity"])) for l in body["lines"]] == [
        (md.p1, 5), (md.p2, 2),
    ]


def test_update_cannot_make_locations_equal(api: TestClient, md) -> None:
    transfer = create(api, md)
    response = api.put(f"/api/transfers/{transfer['id']}", json={"to_location_id": md.loc_a})
    assert response.status_code == 422 and "must differ" in response.json()["detail"]


@pytest.mark.parametrize("field", ["from_location_id", "to_location_id", "schedule_date", "lines"])
def test_update_cannot_null_required_fields(api: TestClient, md, field) -> None:
    transfer = create(api, md)
    assert api.put(f"/api/transfers/{transfer['id']}", json={field: None}).status_code == 422


def test_backend_owned_fields_are_rejected(api: TestClient, md) -> None:
    for field in ("status", "reference", "warehouse_id"):
        assert api.post("/api/transfers", json=transfer_body(md, **{field: 1})).status_code == 422


# --- Validation of the document ---------------------------------------------


def test_same_source_and_destination_rejected(api: TestClient, md) -> None:
    response = api.post("/api/transfers", json=transfer_body(md, to_location_id=md.loc_a))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides, detail",
    [
        ({"from_location_id": 999}, "from_location_id does not exist"),
        ({"to_location_id": 999}, "to_location_id does not exist"),
        ({"lines": [{"product_id": 999, "quantity": 1}]}, "Product 999 does not exist"),
    ],
    ids=["source", "destination", "product"],
)
def test_invalid_references(api: TestClient, md, overrides, detail) -> None:
    response = api.post("/api/transfers", json=transfer_body(md, **overrides))
    assert response.status_code == 422 and response.json()["detail"] == detail


def test_inactive_source_rejected(api: TestClient, md) -> None:
    response = api.post("/api/transfers", json=transfer_body(md, from_location_id=md.archived_loc))
    assert response.status_code == 422 and response.json()["detail"] == "from_location_id is archived"


def test_inactive_destination_rejected(api: TestClient, md) -> None:
    response = api.post("/api/transfers", json=transfer_body(md, to_location_id=md.archived_loc))
    assert response.status_code == 422 and response.json()["detail"] == "to_location_id is archived"


def test_archived_product_rejected(api: TestClient, md) -> None:
    response = api.post("/api/transfers", json=transfer_body(
        md, lines=[{"product_id": md.archived_product, "quantity": 1}]))
    assert response.status_code == 422 and "archived" in response.json()["detail"]


@pytest.mark.parametrize(
    "lines",
    [[], [{"product_id": 1, "quantity": 0}], [{"product_id": 1, "quantity": -2}],
     [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 3}]],
    ids=["empty", "zero", "negative", "duplicate-product"],
)
def test_invalid_lines(api: TestClient, md, lines) -> None:
    assert api.post("/api/transfers", json=transfer_body(md, lines=lines)).status_code == 422


# --- Workflow ---------------------------------------------------------------


def test_todo_moves_draft_to_ready(api: TestClient, db: Session, md) -> None:
    assert ready(api, md)["status"] == "READY"
    assert movements(db) == []


def test_validate_on_draft_only_confirms(api: TestClient, db: Session, md) -> None:
    """The UI offers Validate on a DRAFT: it confirms the transfer, nothing moves."""
    put_stock(db, md, md.p1, md.loc_a, 100)
    transfer = create(api, md)
    response = act(api, transfer, "validate")
    assert response.status_code == 200 and response.json()["status"] == "READY"
    assert stock_qty(db, md.p1, md.loc_a) == 100 and transfer_movements(db) == []


def test_validate_moves_stock_and_creates_transfer_movement(
    api: TestClient, db: Session, md
) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    transfer = ready(api, md)
    response = act(api, transfer, "validate")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DONE" and response.json()["lines"]

    assert stock_qty(db, md.p1, md.loc_a) == 70  # source decreases
    assert stock_qty(db, md.p1, md.loc_b) == 30  # destination increases
    [moved] = transfer_movements(db)
    assert (moved.product_id, moved.quantity, moved.from_location_id, moved.to_location_id) == (
        md.p1, 30, md.loc_a, md.loc_b,
    )
    assert (moved.reference, moved.source_type, moved.source_id, moved.performed_by) == (
        "WH/INT/0001", "transfer", transfer["id"], md.user,
    )


def test_ui_flow_validate_twice(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    transfer = create(api, md)
    assert act(api, transfer, "validate").json()["status"] == "READY"
    assert act(api, transfer, "validate").json()["status"] == "DONE"
    assert stock_qty(db, md.p1, md.loc_b) == 30


def test_transfer_between_warehouses(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    transfer = ready(api, md, to_location_id=md.other_loc, lines=[{"product_id": md.p1, "quantity": 4}])
    assert act(api, transfer, "validate").json()["status"] == "DONE"
    assert stock_qty(db, md.p1, md.other_loc) == 4


def test_insufficient_stock_rejected(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 20)
    transfer = ready(api, md)
    response = act(api, transfer, "validate")
    assert response.status_code == 409 and "Insufficient" in response.json()["detail"]
    assert status_of(api, transfer) == "READY"
    assert stock_qty(db, md.p1, md.loc_a) == 20 and stock_qty(db, md.p1, md.loc_b) is None


def test_missing_source_stock_rejected(api: TestClient, db: Session, md) -> None:
    transfer = ready(api, md)
    assert act(api, transfer, "validate").status_code == 409
    assert movements(db) == []


def test_reserved_stock_is_not_transferred(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 40, reserved=15)  # free 25 < 30
    transfer = ready(api, md)
    assert act(api, transfer, "validate").status_code == 409
    assert stock_qty(db, md.p1, md.loc_a) == 40


@pytest.mark.parametrize("model, key", [(Location, "loc_a"), (Location, "loc_b"), (Product, "p1")],
                         ids=["source", "destination", "product"])
def test_archived_after_ready_blocks_validation(api: TestClient, db: Session, md, model, key) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    transfer = ready(api, md)
    archive(db, model, getattr(md, key))
    assert act(api, transfer, "validate").status_code == 422
    assert status_of(api, transfer) == "READY" and transfer_movements(db) == []


def test_multi_line_failure_rolls_back_every_line(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    put_stock(db, md, md.p2, md.loc_a, 5)
    transfer = ready(api, md, lines=[{"product_id": md.p1, "quantity": 30},
                                     {"product_id": md.p2, "quantity": 6}])  # p2 is short
    assert act(api, transfer, "validate").status_code == 409
    assert stock_qty(db, md.p1, md.loc_a) == 100 and stock_qty(db, md.p1, md.loc_b) is None
    assert stock_qty(db, md.p2, md.loc_a) == 5
    assert transfer_movements(db) == [] and status_of(api, transfer) == "READY"


def test_failure_after_a_line_was_applied_rolls_it_back(
    api: TestClient, db: Session, md, monkeypatch: pytest.MonkeyPatch
) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    put_stock(db, md, md.p2, md.loc_a, 100)
    transfer = ready(api, md, lines=[{"product_id": md.p1, "quantity": 30},
                                     {"product_id": md.p2, "quantity": 30}])
    real_transfer = inventory_service.transfer
    calls = []

    def transfer_then_fail(db, **kwargs):
        calls.append(kwargs["product_id"])
        if len(calls) == 2:
            raise inventory_service.InventoryError("simulated failure on line 2")
        return real_transfer(db, **kwargs)

    monkeypatch.setattr(inventory_service, "transfer", transfer_then_fail)
    assert act(api, transfer, "validate").status_code == 409 and len(calls) == 2
    assert stock_qty(db, md.p1, md.loc_a) == 100 and stock_qty(db, md.p1, md.loc_b) is None
    assert transfer_movements(db) == []


def test_transfer_promotes_waiting_delivery_at_destination(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    delivery = api.post("/api/deliveries", json={
        "warehouse_id": md.wh, "source_location_id": md.loc_b, "schedule_date": "2026-10-05",
        "lines": [{"product_id": md.p1, "quantity": 25}],
    }).json()
    assert api.post(f"/api/deliveries/{delivery['id']}/todo").json()["status"] == "WAITING"
    act(api, ready(api, md), "validate")  # 30 arrive at loc_b
    assert api.get(f"/api/deliveries/{delivery['id']}").json()["status"] == "READY"


# --- Completed and cancelled transfers --------------------------------------


def test_completed_transfer_cannot_be_changed(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    transfer = ready(api, md)
    act(api, transfer, "validate")
    assert api.put(f"/api/transfers/{transfer['id']}", json={
        "lines": [{"product_id": md.p1, "quantity": 1}]}).status_code == 409
    for action in ("validate", "todo", "cancel"):
        assert act(api, transfer, action).status_code == 409
    assert stock_qty(db, md.p1, md.loc_a) == 70 and len(transfer_movements(db)) == 1


@pytest.mark.parametrize("make", [create, ready], ids=["draft", "ready"])
def test_cancel_does_not_change_stock(api: TestClient, db: Session, md, make) -> None:
    put_stock(db, md, md.p1, md.loc_a, 100)
    transfer = make(api, md)
    response = act(api, transfer, "cancel")
    assert response.status_code == 200 and response.json()["status"] == "CANCELED"
    assert stock_qty(db, md.p1, md.loc_a) == 100 and stock_qty(db, md.p1, md.loc_b) is None
    for action in ("cancel", "todo", "validate"):
        assert act(api, transfer, action).status_code == 409


def test_workflow_actions_on_missing_transfer(api: TestClient, md) -> None:
    for action in ("todo", "validate", "cancel"):
        assert api.post(f"/api/transfers/999/{action}").status_code == 404
