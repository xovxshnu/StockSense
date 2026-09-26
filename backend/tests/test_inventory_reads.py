"""Read services on SQLite and, with TEST_POSTGRES_URL, on migrated PostgreSQL:
the behavior that depends on the database (ILIKE/LIKE escaping, NUMERIC sums,
CASE boundaries, created_at ties within one transaction, aggregate counts)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Category, Location, MovementType, Product, Stock, Warehouse
from app.schemas.inventory import StockStatus
from app.services import (
    adjustment_service,
    dashboard_service,
    delivery_service,
    inventory_service,
    movement_service,
    receipt_service,
    stock_service,
    transfer_service,
)
from tests.test_stock_models import pg_engine, refs, session  # noqa: F401 (fixtures)
from tests.test_transfer_adjustment_flow import (
    new_adjustment,
    new_delivery,
    new_receipt,
    new_transfer,
)


def seed(db: Session, refs, product: str, location: str, quantity, reserved=0) -> None:
    inventory_service.receive(
        db, product_id=refs[product], location_id=refs[location],
        quantity=Decimal(str(quantity)), reference="WH/IN/SEED", source_type="seed",
        source_id=0, performed_by=refs["user"],
    )
    if reserved:
        stock = db.query(Stock).filter_by(product_id=refs[product], location_id=refs[location]).one()
        stock.reserved_quantity = Decimal(str(reserved))
    db.commit()


def set_level(db: Session, refs, product: str, level: int) -> None:
    db.get(Product, refs[product]).reorder_level = level
    db.commit()


@pytest.fixture
def second_site(session: Session, refs) -> dict:
    """Another warehouse with one location, and a second category."""
    warehouse = Warehouse(name="North", short_code="NTH")
    location = Location(warehouse=warehouse, name="North Bay", short_code="N1")
    category = Category(name="Paint_Supplies")
    session.add_all([location, category])
    session.commit()
    return {"warehouse": warehouse.id, "location": location.id, "category": category.id,
            "main_warehouse": session.get(Location, refs["loc_a"]).warehouse_id}


# --- Stock status and filters -----------------------------------------------


@pytest.mark.parametrize(
    "quantity, status",
    [("0", "OUT_OF_STOCK"), ("0.001", "LOW_STOCK"), ("10", "LOW_STOCK"),
     ("10.001", "IN_STOCK"), ("250", "IN_STOCK")],
)
def test_status_boundaries(session: Session, refs, quantity, status) -> None:
    set_level(session, refs, "product", 10)
    seed(session, refs, "product", "loc_a", "5")
    stock = session.query(Stock).one()
    stock.quantity = Decimal(quantity)  # state set directly: boundary check only
    session.commit()
    [row] = stock_service.list_stock(session)
    assert row.status is StockStatus(status)


def test_reorder_level_zero_is_never_low(session: Session, refs) -> None:
    seed(session, refs, "product", "loc_a", "0.5")
    assert stock_service.list_stock(session)[0].status is StockStatus.IN_STOCK


def test_search_is_case_insensitive_and_escapes_wildcards(
    session: Session, refs, second_site
) -> None:
    seed(session, refs, "product", "loc_a", 1)
    seed(session, refs, "other_product", "loc_a", 1)
    assert [r.product_sku for r in stock_service.list_stock(session, search="w1")] == ["W1"]
    assert [r.product_sku for r in stock_service.list_stock(session, search="BOL")] == ["B1"]
    assert stock_service.list_stock(session, search="_") == []  # not a wildcard
    assert stock_service.list_stock(session, search="%") == []


def test_location_warehouse_category_filters(session: Session, refs, second_site) -> None:
    session.get(Product, refs["other_product"]).category_id = second_site["category"]
    session.commit()
    seed(session, refs, "product", "loc_a", 3)
    seed(session, refs, "product", "loc_b", 4)
    seed(session, refs, "other_product", "loc_a", 5)
    refs = refs | {"north": second_site["location"]}
    seed(session, refs, "product", "north", 6)

    def quantities(**filters):
        return sorted(r.quantity for r in stock_service.list_stock(session, **filters))

    assert quantities(warehouse_id=second_site["warehouse"]) == [6]
    assert quantities(warehouse_id=second_site["main_warehouse"]) == [3, 4, 5]
    assert quantities(location_id=refs["loc_b"]) == [4]
    assert quantities(category_id=second_site["category"]) == [5]
    assert quantities() == [3, 4, 5, 6]


def test_low_and_out_filters(session: Session, refs) -> None:
    set_level(session, refs, "product", 5)
    seed(session, refs, "product", "loc_a", 5)  # LOW
    seed(session, refs, "product", "loc_b", 9)  # IN
    seed(session, refs, "other_product", "loc_a", 2)
    inventory_service.adjust(  # -> 0: OUT (row kept)
        session, product_id=refs["other_product"], location_id=refs["loc_a"], quantity=-2,
        reference="WH/ADJ/T", source_type="test", source_id=0, performed_by=refs["user"])
    session.commit()

    def rows(**filters):
        return sorted((r.product_sku, r.location_id) for r in stock_service.list_stock(session, **filters))

    assert rows(low_stock=True) == [("W1", refs["loc_a"])]
    assert rows(out_of_stock=True) == [("B1", refs["loc_a"])]
    assert rows(low_stock=True, out_of_stock=True) == [("B1", refs["loc_a"]), ("W1", refs["loc_a"])]


def test_archived_rows_hidden_unless_requested(session: Session, refs, second_site) -> None:
    seed(session, refs, "product", "loc_a", 1)
    seed(session, refs, "other_product", "loc_a", 1)
    refs = refs | {"north": second_site["location"]}
    seed(session, refs, "product", "north", 1)
    session.get(Product, refs["other_product"]).active = False
    session.get(Warehouse, second_site["warehouse"]).active = False  # its location too
    session.commit()
    assert [(r.product_sku, r.location_id) for r in stock_service.list_stock(session)] == [
        ("W1", refs["loc_a"])]
    assert len(stock_service.list_stock(session, include_inactive=True)) == 3


def test_product_totals_are_decimal_sums_over_active_locations(
    session: Session, refs, second_site
) -> None:
    set_level(session, refs, "product", 10)
    seed(session, refs, "product", "loc_a", "2.125", reserved="1.5")
    seed(session, refs, "product", "loc_b", "3.25")
    refs = refs | {"north": second_site["location"]}
    seed(session, refs, "product", "north", "100")
    session.get(Location, second_site["location"]).active = False
    session.commit()

    detail = stock_service.get_product_stock(session, refs["product"])
    assert (detail.quantity, detail.reserved_quantity, detail.free_to_use) == (
        Decimal("5.375"), Decimal("1.5"), Decimal("3.875"))
    assert detail.status is StockStatus.LOW_STOCK
    assert [l.location_id for l in detail.locations] == [refs["loc_a"], refs["loc_b"]]


# --- Movements --------------------------------------------------------------


def test_movement_order_breaks_same_transaction_ties_by_id(session: Session, refs) -> None:
    """On PostgreSQL now() is the transaction time: a two-line receipt gives two
    movements with the same created_at. Newest first, then highest id first."""
    receipt = new_receipt(session, refs, [("product", 1), ("other_product", 2)])
    receipt_service.validate_receipt(session, receipt.id, refs["user"])
    rows = movement_service.list_movements(session)
    assert [r.product_sku for r in rows] == ["B1", "W1"]
    assert rows[0].created_at == rows[1].created_at or rows[0].created_at > rows[1].created_at


def test_movement_filters_and_paging(session: Session, refs, second_site) -> None:
    refs_n = refs | {"north": second_site["location"]}
    seed(session, refs, "product", "loc_a", 50)
    transfer = new_transfer(session, refs_n, [("product", 10)], "loc_a", "north")
    transfer_service.validate_transfer(session, transfer.id, refs["user"])
    delivery = new_delivery(session, refs, [("product", 5)])
    delivery_service.validate_delivery(session, delivery.id, refs["user"])

    def types(**filters):
        return [r.movement_type for r in movement_service.list_movements(session, **filters)]

    assert types() == [MovementType.OUT, MovementType.TRANSFER, MovementType.IN]
    assert types(warehouse_id=second_site["warehouse"]) == [MovementType.TRANSFER]
    assert types(location_id=refs["loc_a"]) == [MovementType.OUT, MovementType.TRANSFER,
                                                MovementType.IN]
    assert types(to_location_id=second_site["location"]) == [MovementType.TRANSFER]
    assert types(from_location_id=refs["loc_a"]) == [MovementType.OUT, MovementType.TRANSFER]
    assert types(reference="int/") == [MovementType.TRANSFER]
    assert types(search="WIDGET") == types()
    assert types(movement_type=MovementType.IN) == [MovementType.IN]
    assert types(limit=1, offset=1) == [MovementType.TRANSFER]


# --- Dashboard --------------------------------------------------------------


def test_dashboard_counts(session: Session, refs, second_site) -> None:
    set_level(session, refs, "product", 10)
    seed(session, refs, "product", "loc_a", 4)
    seed(session, refs, "product", "loc_b", 4)  # 8 <= 10 -> low
    refs_n = refs | {"north": second_site["location"]}

    new_receipt(session, refs, [("product", 1)])  # READY, scheduled 2026-10-01
    new_receipt(session, refs_n, [("other_product", 1)], "north")  # READY, other warehouse
    new_delivery(session, refs, [("product", 3)])  # READY, scheduled 2026-10-02
    new_delivery(session, refs, [("other_product", 3)])  # WAITING, scheduled 2026-10-02
    new_transfer(session, refs, [("product", 1)])  # READY -> scheduled

    body = dashboard_service.get_dashboard(session, today=date(2026, 10, 3))
    assert body.inventory.model_dump() == {"total_products": 2, "in_stock": 0, "low_stock": 1,
                                           "out_of_stock": 1}
    assert body.receipts.model_dump() == {"pending": 2, "late": 2, "operations": 2}
    assert body.deliveries.model_dump() == {"pending": 1, "waiting": 1, "late": 2,
                                            "operations": 2}
    assert body.transfers.scheduled == 1

    # Due today is not late: on 2026-10-02 only the receipts (due 10-01) are.
    due_today = dashboard_service.get_dashboard(session, today=date(2026, 10, 2))
    assert due_today.receipts.late == 2 and due_today.deliveries.late == 0
    on_time = dashboard_service.get_dashboard(session, today=date(2026, 10, 1))
    assert on_time.receipts.late == 0 and on_time.deliveries.late == 0

    north = dashboard_service.get_dashboard(session, warehouse_id=second_site["warehouse"],
                                            today=date(2026, 10, 3))
    assert north.receipts.operations == 1 and north.deliveries.operations == 0
    assert north.inventory.out_of_stock == 2  # nothing stocked in that warehouse


def test_dashboard_category_filter(session: Session, refs, second_site) -> None:
    session.get(Product, refs["other_product"]).category_id = second_site["category"]
    session.commit()
    new_receipt(session, refs, [("product", 1)])
    new_receipt(session, refs, [("product", 1), ("other_product", 1)])
    body = dashboard_service.get_dashboard(session, category_id=second_site["category"])
    assert body.inventory.total_products == 1
    assert body.receipts.operations == 1  # only the receipt with a line in that category


def test_blueprint_flow_on_every_read_service(session: Session, refs) -> None:
    user = refs["user"]
    set_level(session, refs, "product", 10)
    receipt_service.validate_receipt(session, new_receipt(session, refs, [("product", 100)]).id, user)
    transfer_service.validate_transfer(session, new_transfer(session, refs, [("product", 30)]).id, user)
    delivery_service.validate_delivery(
        session, new_delivery(session, refs, [("product", 20)], location="loc_b").id, user)
    adjustment_service.validate_adjustment(
        session, new_adjustment(session, refs, [("product", 7)], location="loc_b").id, user)

    assert {(r.location_id, r.quantity, r.status.value)
            for r in stock_service.list_stock(session)} == {
        (refs["loc_a"], 70, "IN_STOCK"), (refs["loc_b"], 7, "LOW_STOCK")}
    assert stock_service.get_product_stock(session, refs["product"]).quantity == 77
    assert [(m.reference, m.movement_type.value, m.quantity)
            for m in movement_service.list_movements(session)] == [
        ("WH/ADJ/0001", "ADJUSTMENT", -3), ("WH/OUT/0001", "OUT", 20),
        ("WH/INT/0001", "TRANSFER", 30), ("WH/IN/0001", "IN", 100)]
    body = dashboard_service.get_dashboard(session)
    assert body.inventory.model_dump() == {"total_products": 2, "in_stock": 1, "low_stock": 0,
                                           "out_of_stock": 1}
    assert (body.receipts.operations, body.deliveries.operations, body.transfers.scheduled) == (0, 0, 0)
