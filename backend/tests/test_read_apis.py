"""Stock / Move History / Dashboard read APIs (SQLite, over HTTP).

Database-sensitive behavior (filters, status boundaries, aggregation, ordering)
is also covered on PostgreSQL in test_inventory_reads.py.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Category, Location, Product, Stock, StockMovement, Warehouse
from tests.operation_fixtures import (  # noqa: F401 (fixtures)
    api,
    archive,
    md,
    put_stock,
)


def set_reorder_level(db: Session, product_id: int, level: int) -> None:
    db.get(Product, product_id).reorder_level = level
    db.commit()


def run(api: TestClient, path: str, body: dict, *actions: str) -> dict:
    """Create an operation document and run its workflow actions over HTTP."""
    response = api.post(path, json=body)
    assert response.status_code == 201, response.text
    document = response.json()
    for action in actions:
        response = api.post(f"{path}/{document['id']}/{action}")
        assert response.status_code == 200, response.text
        document = response.json()
    return document


def stock(api: TestClient, **params) -> list[dict]:
    response = api.get("/api/stock", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def movements(api: TestClient, **params) -> list[dict]:
    response = api.get("/api/movements", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def dashboard(api: TestClient, **params) -> dict:
    response = api.get("/api/dashboard", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def key(rows: list[dict]) -> list[tuple]:
    return [(r["product_id"], r["location_id"]) for r in rows]


# --- Stock list -------------------------------------------------------------


def test_list_stock_rows(api: TestClient, db: Session, md) -> None:
    set_reorder_level(db, md.p1, 10)
    put_stock(db, md, md.p1, md.loc_a, 100, reserved=30)
    [row] = stock(api)
    assert row == row | {
        "product_id": md.p1, "product_sku": "W1", "product_name": "Widget", "uom": "Unit",
        "reorder_level": 10, "category_id": row["category_id"], "category_name": "Tools",
        "warehouse_id": md.wh, "warehouse_code": "WH", "warehouse_name": "Main",
        "location_id": md.loc_a, "location_code": "A", "location_name": "Stock A",
        "status": "IN_STOCK",
    }
    assert (Decimal(row["quantity"]), Decimal(row["reserved_quantity"])) == (100, 30)
    assert Decimal(row["free_to_use"]) == 70  # quantity - reserved, derived
    assert row["id"] and row["updated_at"]


def test_product_at_several_locations_is_one_row_each(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_b, 5)
    put_stock(db, md, md.p1, md.loc_a, 10)
    put_stock(db, md, md.p2, md.loc_a, 1)
    # Ordered by SKU (B1 < W1), then warehouse, then location.
    assert key(stock(api)) == [(md.p2, md.loc_a), (md.p1, md.loc_a), (md.p1, md.loc_b)]


def test_filters(api: TestClient, db: Session, md) -> None:
    other_category = Category(name="Paint")
    db.add(other_category)
    db.commit()
    db.get(Product, md.p2).category_id = other_category.id
    db.commit()
    put_stock(db, md, md.p1, md.loc_a, 10)
    put_stock(db, md, md.p1, md.other_loc, 10)
    put_stock(db, md, md.p2, md.loc_b, 10)

    assert key(stock(api, warehouse_id=md.other_wh)) == [(md.p1, md.other_loc)]
    assert key(stock(api, location_id=md.loc_b)) == [(md.p2, md.loc_b)]
    assert key(stock(api, category_id=other_category.id)) == [(md.p2, md.loc_b)]
    assert key(stock(api, search="w1")) == [(md.p1, md.loc_a), (md.p1, md.other_loc)]  # SKU
    assert key(stock(api, search="bol")) == [(md.p2, md.loc_b)]  # name
    assert stock(api, search="%") == []  # LIKE wildcards are literal
    assert key(stock(api, warehouse_id=md.wh, search="W1")) == [(md.p1, md.loc_a)]  # combined


def test_low_and_out_of_stock_filters(api: TestClient, db: Session, md) -> None:
    set_reorder_level(db, md.p1, 10)
    put_stock(db, md, md.p1, md.loc_a, 10)  # = reorder level -> LOW
    put_stock(db, md, md.p1, md.loc_b, 11)  # above -> IN
    put_stock(db, md, md.p2, md.loc_a, 3)
    run(api, "/api/deliveries", {  # empty p2 at loc_a -> OUT (row still exists)
        "warehouse_id": md.wh, "source_location_id": md.loc_a, "schedule_date": "2026-10-01",
        "lines": [{"product_id": md.p2, "quantity": 3}]}, "todo", "validate")

    statuses = {(r["product_id"], r["location_id"]): r["status"] for r in stock(api)}
    assert statuses == {(md.p1, md.loc_a): "LOW_STOCK", (md.p1, md.loc_b): "IN_STOCK",
                        (md.p2, md.loc_a): "OUT_OF_STOCK"}
    assert key(stock(api, low_stock=True)) == [(md.p1, md.loc_a)]
    assert key(stock(api, out_of_stock=True)) == [(md.p2, md.loc_a)]
    assert sorted(key(stock(api, low_stock=True, out_of_stock=True))) == sorted(
        [(md.p1, md.loc_a), (md.p2, md.loc_a)])


def test_reserved_quantity_reduces_free_to_use_only(api: TestClient, db: Session, md) -> None:
    set_reorder_level(db, md.p1, 5)
    put_stock(db, md, md.p1, md.loc_a, 8, reserved=8)
    [row] = stock(api)
    assert (Decimal(row["quantity"]), Decimal(row["reserved_quantity"]),
            Decimal(row["free_to_use"])) == (8, 8, 0)
    assert row["status"] == "IN_STOCK"  # status uses the quantity on hand


def test_archived_products_and_locations(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 5)
    put_stock(db, md, md.p1, md.loc_b, 5)
    put_stock(db, md, md.p2, md.loc_a, 5)
    archive(db, Product, md.p2)
    archive(db, Location, md.loc_b)
    assert key(stock(api)) == [(md.p1, md.loc_a)]  # hidden by default
    assert len(stock(api, include_inactive=True)) == 3


def test_stock_requires_authentication(client: TestClient) -> None:
    for path in ("/api/stock", "/api/stock/1", "/api/movements", "/api/dashboard"):
        assert client.get(path).status_code == 401


# --- Stock detail -----------------------------------------------------------


def test_product_stock_detail(api: TestClient, db: Session, md) -> None:
    set_reorder_level(db, md.p1, 20)
    put_stock(db, md, md.p1, md.loc_a, 10, reserved=4)
    put_stock(db, md, md.p1, md.other_loc, 5)
    body = api.get(f"/api/stock/{md.p1}").json()
    assert body == body | {"product_id": md.p1, "product_sku": "W1", "product_name": "Widget",
                           "reorder_level": 20, "category_name": "Tools", "active": True,
                           "status": "LOW_STOCK"}  # 15 in total <= 20
    assert (Decimal(body["quantity"]), Decimal(body["reserved_quantity"]),
            Decimal(body["free_to_use"])) == (15, 4, 11)
    assert [(l["location_id"], l["warehouse_code"], Decimal(l["quantity"]), l["status"])
            for l in body["locations"]] == [
        (md.loc_a, "WH", 10, "LOW_STOCK"), (md.other_loc, "WH2", 5, "LOW_STOCK"),
    ]


def test_detail_of_product_without_stock(api: TestClient, md) -> None:
    body = api.get(f"/api/stock/{md.p2}").json()
    assert Decimal(body["quantity"]) == 0 and body["status"] == "OUT_OF_STOCK"
    assert body["locations"] == []


def test_detail_excludes_archived_locations_from_totals(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 10)
    put_stock(db, md, md.p1, md.loc_b, 7)
    archive(db, Location, md.loc_b)
    body = api.get(f"/api/stock/{md.p1}").json()
    assert Decimal(body["quantity"]) == 10 and len(body["locations"]) == 1
    everything = api.get(f"/api/stock/{md.p1}", params={"include_inactive": True}).json()
    assert len(everything["locations"]) == 2 and Decimal(everything["quantity"]) == 10


def test_detail_of_archived_product_and_missing_product(api: TestClient, db: Session, md) -> None:
    put_stock(db, md, md.p1, md.loc_a, 3)
    archive(db, Product, md.p1)
    body = api.get(f"/api/stock/{md.p1}").json()
    assert body["active"] is False and len(body["locations"]) == 1
    assert api.get("/api/stock/999").status_code == 404


# --- Movements --------------------------------------------------------------


@pytest.fixture
def history(api: TestClient, db: Session, md) -> dict:
    """IN 100 @A, TRANSFER 30 A->B, OUT 20 @B, ADJUSTMENT -3 @B (p1); IN 5 @A (p2)."""
    receipt = run(api, "/api/receipts", {
        "warehouse_id": md.wh, "destination_location_id": md.loc_a, "schedule_date": "2026-10-01",
        "lines": [{"product_id": md.p1, "quantity": 100}, {"product_id": md.p2, "quantity": 5}]},
        "todo", "validate")
    transfer = run(api, "/api/transfers", {
        "from_location_id": md.loc_a, "to_location_id": md.loc_b, "schedule_date": "2026-10-01",
        "lines": [{"product_id": md.p1, "quantity": 30}]}, "todo", "validate")
    delivery = run(api, "/api/deliveries", {
        "warehouse_id": md.wh, "source_location_id": md.loc_b, "schedule_date": "2026-10-01",
        "lines": [{"product_id": md.p1, "quantity": 20}]}, "todo", "validate")
    adjustment = run(api, "/api/adjustments", {
        "location_id": md.loc_b, "lines": [{"product_id": md.p1, "counted_quantity": 7}]},
        "validate")
    return {"receipt": receipt, "transfer": transfer, "delivery": delivery,
            "adjustment": adjustment}


def summary(rows: list[dict]) -> list[tuple]:
    return [(r["reference"], r["movement_type"], r["product_sku"], Decimal(r["quantity"]))
            for r in rows]


def test_list_movements_newest_first(api: TestClient, md, history) -> None:
    rows = movements(api)
    assert summary(rows) == [
        ("WH/ADJ/0001", "ADJUSTMENT", "W1", -3),
        ("WH/OUT/0001", "OUT", "W1", 20),
        ("WH/INT/0001", "TRANSFER", "W1", 30),
        ("WH/IN/0001", "IN", "B1", 5),  # same receipt: later line first (id breaks the tie)
        ("WH/IN/0001", "IN", "W1", 100),
    ]
    transfer = rows[2]
    assert transfer == transfer | {
        "product_id": md.p1, "product_name": "Widget",
        "from_location_id": md.loc_a, "from_location_name": "Stock A",
        "to_location_id": md.loc_b, "to_location_name": "Stock B",
        "source_type": "transfer", "source_id": history["transfer"]["id"],
        "performed_by": md.user, "performed_by_login": "tester",
    }
    assert transfer["created_at"] and transfer["id"]
    assert rows[1]["to_location_id"] is None and rows[1]["to_location_name"] is None  # OUT


def test_movement_filters(api: TestClient, md, history) -> None:
    refs = lambda **p: [r["reference"] for r in movements(api, **p)]  # noqa: E731
    assert refs(product_id=md.p2) == ["WH/IN/0001"]
    assert refs(movement_type="TRANSFER") == ["WH/INT/0001"]
    assert refs(reference="out/0") == ["WH/OUT/0001"]
    assert refs(from_location_id=md.loc_a) == ["WH/INT/0001"]
    assert refs(to_location_id=md.loc_b) == ["WH/ADJ/0001", "WH/INT/0001"]
    assert refs(location_id=md.loc_b) == ["WH/ADJ/0001", "WH/OUT/0001", "WH/INT/0001"]
    assert len(refs(warehouse_id=md.wh)) == 5 and refs(warehouse_id=md.other_wh) == []
    assert refs(search="bolt") == ["WH/IN/0001"]  # product name
    assert refs(search="b1") == ["WH/IN/0001"]  # SKU
    assert refs(search="WH/ADJ") == ["WH/ADJ/0001"]  # reference
    assert api.get("/api/movements", params={"movement_type": "SIDEWAYS"}).status_code == 422


def test_movement_category_filter(api: TestClient, db: Session, md, history) -> None:
    other = Category(name="Paint")
    db.add(other)
    db.commit()
    db.get(Product, md.p2).category_id = other.id
    db.commit()
    assert [r["product_id"] for r in movements(api, category_id=other.id)] == [md.p2]


def test_movement_paging(api: TestClient, md, history) -> None:
    everything = movements(api)
    assert movements(api, limit=2) == everything[:2]
    assert movements(api, limit=2, offset=2) == everything[2:4]
    assert api.get("/api/movements", params={"limit": 0}).status_code == 422
    assert api.get("/api/movements", params={"limit": 5000}).status_code == 422


def test_movements_are_read_only(api: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        assert getattr(api, method)("/api/movements").status_code == 405
        assert getattr(api, method)("/api/movements/1").status_code in (404, 405)
    for path in ("/api/stock", "/api/stock/1", "/api/dashboard"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(api, method)(path).status_code == 405


def test_read_apis_issue_no_writes(api: TestClient, db: Session, md, history) -> None:
    """Every SQL statement the read endpoints run is a SELECT."""
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        stock(api)
        stock(api, low_stock=True, warehouse_id=md.wh)
        api.get(f"/api/stock/{md.p1}")
        movements(api, search="W1")
        dashboard(api, warehouse_id=md.wh)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements
    writes = [s for s in statements
              if s.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    assert writes == []


# --- Dashboard --------------------------------------------------------------


def test_empty_dashboard(api: TestClient, md) -> None:
    assert dashboard(api) == {
        "inventory": {"total_products": 2, "in_stock": 0, "low_stock": 0, "out_of_stock": 2},
        "receipts": {"pending": 0, "late": 0, "operations": 0},
        "deliveries": {"pending": 0, "waiting": 0, "late": 0, "operations": 0},
        "transfers": {"scheduled": 0},
    }


def test_inventory_kpis(api: TestClient, db: Session, md) -> None:
    extra = Product(name="Nail", sku="N1", category_id=db.get(Product, md.p1).category_id,
                    reorder_level=50)
    db.add(extra)
    db.commit()
    set_reorder_level(db, md.p1, 10)
    put_stock(db, md, md.p1, md.loc_a, 6)
    put_stock(db, md, md.p1, md.loc_b, 5)  # 11 in total > 10 -> in stock
    put_stock(db, md, extra.id, md.loc_a, 50)  # = 50 -> low
    # p2: never stocked -> out; archived_product is not counted at all
    assert dashboard(api)["inventory"] == {
        "total_products": 3, "in_stock": 1, "low_stock": 1, "out_of_stock": 1,
    }
    # Scoped to one location, p1 has only 6 there -> low.
    assert dashboard(api, location_id=md.loc_a)["inventory"] == {
        "total_products": 3, "in_stock": 0, "low_stock": 2, "out_of_stock": 1,
    }


def test_operation_kpis(api: TestClient, db: Session, md) -> None:
    yesterday = (date.today() - timedelta(days=2)).isoformat()
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    receipt = {"warehouse_id": md.wh, "destination_location_id": md.loc_a,
               "lines": [{"product_id": md.p1, "quantity": 50}]}
    run(api, "/api/receipts", receipt | {"schedule_date": yesterday})  # DRAFT, late
    run(api, "/api/receipts", receipt | {"schedule_date": tomorrow}, "todo")  # READY
    run(api, "/api/receipts", receipt | {"schedule_date": yesterday}, "todo", "validate")  # DONE
    run(api, "/api/receipts", receipt | {"schedule_date": yesterday}, "cancel")  # CANCELED

    delivery = {"warehouse_id": md.wh, "source_location_id": md.loc_a,
                "lines": [{"product_id": md.p1, "quantity": 10}]}
    run(api, "/api/deliveries", delivery | {"schedule_date": tomorrow})  # DRAFT
    run(api, "/api/deliveries", delivery | {"schedule_date": yesterday}, "todo")  # READY, late
    run(api, "/api/deliveries", delivery | {"schedule_date": tomorrow,
        "lines": [{"product_id": md.p2, "quantity": 1}]}, "todo")  # WAITING

    transfer = {"from_location_id": md.loc_a, "to_location_id": md.loc_b,
                "schedule_date": tomorrow, "lines": [{"product_id": md.p1, "quantity": 1}]}
    run(api, "/api/transfers", transfer)  # DRAFT
    run(api, "/api/transfers", transfer, "todo")  # READY -> scheduled
    run(api, "/api/transfers", transfer, "todo", "validate")  # DONE

    body = dashboard(api)
    assert body["receipts"] == {"pending": 1, "late": 1, "operations": 2}
    assert body["deliveries"] == {"pending": 1, "waiting": 1, "late": 1, "operations": 3}
    assert body["transfers"] == {"scheduled": 1}

    other = dashboard(api, warehouse_id=md.other_wh)
    assert other["receipts"]["operations"] == other["deliveries"]["operations"] == 0
    assert other["transfers"]["scheduled"] == 0


def test_dashboard_follows_each_operation(api: TestClient, db: Session, md) -> None:
    set_reorder_level(db, md.p1, 10)
    inventory = lambda: dashboard(api)["inventory"]  # noqa: E731
    assert inventory()["out_of_stock"] == 2

    receipt = run(api, "/api/receipts", {
        "warehouse_id": md.wh, "destination_location_id": md.loc_a, "schedule_date": "2030-01-01",
        "lines": [{"product_id": md.p1, "quantity": 12}]}, "todo")
    assert dashboard(api)["receipts"]["pending"] == 1
    api.post(f"/api/receipts/{receipt['id']}/validate")  # receipt -> 12 in stock
    assert inventory()["in_stock"] == 1 and dashboard(api)["receipts"]["pending"] == 0

    run(api, "/api/transfers", {  # transfer: total unchanged, still in stock
        "from_location_id": md.loc_a, "to_location_id": md.loc_b, "schedule_date": "2030-01-01",
        "lines": [{"product_id": md.p1, "quantity": 12}]}, "todo", "validate")
    assert inventory()["in_stock"] == 1
    assert dashboard(api, location_id=md.loc_a)["inventory"]["out_of_stock"] == 2

    run(api, "/api/deliveries", {  # delivery: 12 -> 4 -> low
        "warehouse_id": md.wh, "source_location_id": md.loc_b, "schedule_date": "2030-01-01",
        "lines": [{"product_id": md.p1, "quantity": 8}]}, "todo", "validate")
    assert inventory()["low_stock"] == 1

    run(api, "/api/adjustments", {  # adjustment: counted 0 -> out
        "location_id": md.loc_b, "lines": [{"product_id": md.p1, "counted_quantity": 0}]},
        "validate")
    assert inventory() == {"total_products": 2, "in_stock": 0, "low_stock": 0, "out_of_stock": 2}


def test_dashboard_reads_stock_not_movements(api: TestClient, db: Session, md) -> None:
    """A Stock row with no movement counts; a movement with no Stock does not."""
    db.add(Stock(product_id=md.p1, location_id=md.loc_a, quantity=Decimal("5")))
    db.add(StockMovement(reference="WH/IN/X", product_id=md.p2, movement_type="IN",
                         to_location_id=md.loc_a, quantity=Decimal("99"), source_type="test",
                         source_id=0, performed_by=md.user))
    db.commit()
    assert dashboard(api)["inventory"] == {
        "total_products": 2, "in_stock": 1, "low_stock": 0, "out_of_stock": 1,
    }
    assert key(stock(api)) == [(md.p1, md.loc_a)]


def test_read_services_do_not_use_the_ledger_for_stock() -> None:
    """Stock and dashboard figures never import (let alone replay) the ledger."""
    import ast
    from pathlib import Path

    import app

    services = Path(app.__file__).resolve().parent / "services"
    for module in ("stock_service.py", "dashboard_service.py"):
        tree = ast.parse((services / module).read_text())
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        } | {
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "StockMovement" not in imported, module
        assert "app.models.stock_movement" not in imported, module


# --- Blueprint flow through every read API ----------------------------------


def test_blueprint_flow_is_reflected_everywhere(api: TestClient, db: Session, md, history) -> None:
    """Receive 100 -> transfer 30 -> deliver 20 -> adjust -3 (fixture `history`)."""
    set_reorder_level(db, md.p1, 10)
    rows = {(r["product_id"], r["location_id"]): Decimal(r["quantity"]) for r in stock(api)}
    assert rows == {(md.p1, md.loc_a): 70, (md.p1, md.loc_b): 7, (md.p2, md.loc_a): 5}

    detail = api.get(f"/api/stock/{md.p1}").json()
    assert Decimal(detail["quantity"]) == 77 and detail["status"] == "IN_STOCK"
    assert [(l["location_code"], Decimal(l["quantity"]), l["status"])
            for l in detail["locations"]] == [("A", 70, "IN_STOCK"), ("B", 7, "LOW_STOCK")]

    assert summary(movements(api, product_id=md.p1)) == [
        ("WH/ADJ/0001", "ADJUSTMENT", "W1", -3),
        ("WH/OUT/0001", "OUT", "W1", 20),
        ("WH/INT/0001", "TRANSFER", "W1", 30),
        ("WH/IN/0001", "IN", "W1", 100),
    ]
    body = dashboard(api)
    assert body["inventory"] == {"total_products": 2, "in_stock": 2, "low_stock": 0,
                                 "out_of_stock": 0}
    assert body["receipts"]["operations"] == body["deliveries"]["operations"] == 0
    assert body["transfers"]["scheduled"] == 0
    assert [(l["location_code"], l["status"]) for l in stock(api, low_stock=True)] == [("B", "LOW_STOCK")]


def test_warehouse_is_listed_with_its_code(api: TestClient, db: Session, md) -> None:
    db.get(Warehouse, md.other_wh).name = "Renamed"
    db.commit()
    put_stock(db, md, md.p1, md.other_loc, 1)
    assert stock(api)[0]["warehouse_name"] == "Renamed"
