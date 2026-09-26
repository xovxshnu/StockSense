"""Receipt / delivery -> Inventory Engine -> Stock + StockMovement, at service level.

Runs on SQLite and, with TEST_POSTGRES_URL, on migrated PostgreSQL (fixtures from
test_stock_models). The concurrency tests only run on PostgreSQL.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app
from app.models import DeliveryStatus, Location, MovementType, ReceiptStatus, Stock, StockMovement
from app.schemas.delivery import DeliveryCreate
from app.schemas.receipt import ReceiptCreate
from app.services import delivery_service, inventory_service, receipt_service
from app.services.operation_common import InvalidTransitionError
from tests.test_inventory_service import run_concurrently, stock_mutations
from tests.test_stock_models import pg_engine, refs, session  # noqa: F401 (fixtures)

SERVICES = Path(app.__file__).resolve().parent / "services"


def warehouse_of(db: Session, location_id: int) -> int:
    return db.get(Location, location_id).warehouse_id


def new_receipt(db: Session, refs, lines, location="loc_a"):
    receipt = receipt_service.create_receipt(db, ReceiptCreate(
        warehouse_id=warehouse_of(db, refs[location]),
        destination_location_id=refs[location],
        schedule_date="2026-10-01",
        lines=[{"product_id": refs[p], "quantity": q} for p, q in lines],
    ))
    return receipt_service.mark_receipt_todo(db, receipt.id)


def new_delivery(db: Session, refs, lines, location="loc_a"):
    delivery = delivery_service.create_delivery(db, DeliveryCreate(
        warehouse_id=warehouse_of(db, refs[location]),
        source_location_id=refs[location],
        schedule_date="2026-10-02",
        lines=[{"product_id": refs[p], "quantity": q} for p, q in lines],
    ))
    return delivery_service.mark_delivery_todo(db, delivery.id)


def qty(db: Session, refs, product="product", location="loc_a") -> Decimal | None:
    db.expire_all()
    return db.scalar(select(Stock.quantity).where(
        Stock.product_id == refs[product], Stock.location_id == refs[location]))


def ledger(db: Session) -> list[tuple]:
    db.expire_all()
    return [
        (m.reference, m.movement_type, m.product_id, m.quantity, m.source_type, m.source_id)
        for m in db.scalars(select(StockMovement).order_by(StockMovement.id))
    ]


def ledger_balance(db: Session, product_id: int, location_id: int) -> Decimal:
    """Stock implied by the movements alone (IN/ADJUSTMENT/TRANSFER-in minus OUT/TRANSFER-out)."""
    total = Decimal("0")
    for m in db.scalars(select(StockMovement).where(StockMovement.product_id == product_id)):
        if m.to_location_id == location_id:
            total += m.quantity
        if m.from_location_id == location_id:
            total -= m.quantity
    return total


# --- End to end -------------------------------------------------------------


def test_receipt_goes_through_the_engine(session: Session, refs) -> None:
    receipt = new_receipt(session, refs, [("product", 100)])
    done = receipt_service.validate_receipt(session, receipt.id, refs["user"])
    assert done.status is ReceiptStatus.DONE
    assert qty(session, refs) == 100
    assert ledger(session) == [
        ("WH/IN/0001", MovementType.IN, refs["product"], 100, "receipt", receipt.id)
    ]


def test_delivery_goes_through_the_engine(session: Session, refs) -> None:
    receipt_service.validate_receipt(session, new_receipt(session, refs, [("product", 50)]).id,
                                     refs["user"])
    delivery = new_delivery(session, refs, [("product", 20)])
    assert delivery.status is DeliveryStatus.READY
    done = delivery_service.validate_delivery(session, delivery.id, refs["user"])
    assert done.status is DeliveryStatus.DONE
    assert qty(session, refs) == 30
    assert ledger(session)[-1] == (
        "WH/OUT/0001", MovementType.OUT, refs["product"], 20, "delivery", delivery.id
    )


def test_receive_then_deliver_matches_the_ledger(session: Session, refs) -> None:
    """Blueprint section 14, receipt and delivery part: receive 100, deliver 20."""
    receipt = new_receipt(session, refs, [("product", 100), ("other_product", 40)])
    receipt_service.validate_receipt(session, receipt.id, refs["user"])
    delivery = new_delivery(session, refs, [("product", 20)])
    delivery_service.validate_delivery(session, delivery.id, refs["user"])

    assert qty(session, refs) == 80 and qty(session, refs, "other_product") == 40
    assert [(r, t.value, q) for r, t, _, q, _, _ in ledger(session)] == [
        ("WH/IN/0001", "IN", 100), ("WH/IN/0001", "IN", 40), ("WH/OUT/0001", "OUT", 20),
    ]
    for product in ("product", "other_product"):
        assert ledger_balance(session, refs[product], refs["loc_a"]) == qty(session, refs, product)


def test_multi_line_receipt_is_atomic(
    session: Session, refs, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = new_receipt(session, refs, [("product", 100), ("other_product", 50)])
    real_receive = inventory_service.receive
    calls = []

    def fail_on_second_line(db, **kwargs):
        calls.append(kwargs["product_id"])
        if len(calls) == 2:
            raise RuntimeError("simulated crash on line 2")
        return real_receive(db, **kwargs)

    monkeypatch.setattr(inventory_service, "receive", fail_on_second_line)
    with pytest.raises(RuntimeError):
        receipt_service.validate_receipt(session, receipt.id, refs["user"])

    assert len(calls) == 2
    assert qty(session, refs) is None and qty(session, refs, "other_product") is None
    assert ledger(session) == []
    assert receipt_service.get_receipt(session, receipt.id).status is ReceiptStatus.READY


def test_multi_line_delivery_shortage_is_atomic(session: Session, refs) -> None:
    receipt_service.validate_receipt(
        session, new_receipt(session, refs, [("product", 10), ("other_product", 10)]).id,
        refs["user"])
    first = new_delivery(session, refs, [("other_product", 8)])
    second = new_delivery(session, refs, [("product", 5), ("other_product", 5)])
    delivery_service.validate_delivery(session, first.id, refs["user"])  # other_product -> 2

    result = delivery_service.validate_delivery(session, second.id, refs["user"])
    assert result.status is DeliveryStatus.WAITING
    assert qty(session, refs) == 10 and qty(session, refs, "other_product") == 2
    assert [t for _, t, *_ in ledger(session)].count(MovementType.OUT) == 1


# --- Architecture guard -----------------------------------------------------


@pytest.mark.parametrize("module", ["receipt_service.py", "delivery_service.py",
                                    "operation_common.py"])
def test_operation_services_never_write_stock(module: str) -> None:
    assert stock_mutations(SERVICES / module) == []


def test_operation_services_change_stock_only_through_the_engine(
    session: Session, refs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the engine's functions replaced, validating documents changes nothing:
    every stock change they make is an engine call."""
    calls = []
    monkeypatch.setattr(inventory_service, "receive", lambda db, **kw: calls.append(("IN", kw)))
    monkeypatch.setattr(inventory_service, "deliver", lambda db, **kw: calls.append(("OUT", kw)))

    receipt = new_receipt(session, refs, [("product", 5)])
    receipt_service.validate_receipt(session, receipt.id, refs["user"])
    session.add(Stock(product_id=refs["product"], location_id=refs["loc_a"],
                      quantity=Decimal("5")))  # so the delivery is READY
    session.commit()
    delivery = new_delivery(session, refs, [("product", 5)])
    delivery_service.validate_delivery(session, delivery.id, refs["user"])

    assert [(kind, kw["reference"], kw["source_type"], kw["performed_by"]) for kind, kw in calls] == [
        ("IN", receipt.reference, "receipt", refs["user"]),
        ("OUT", delivery.reference, "delivery", refs["user"]),
    ]
    assert qty(session, refs) == 5 and ledger(session) == []  # only the test's own row


# --- Concurrency (PostgreSQL only) ------------------------------------------


@pytest.fixture
def pg(session: Session) -> Session:
    if session.get_bind().dialect.name != "postgresql":
        pytest.skip("row locking can only be demonstrated on PostgreSQL")
    return session


def test_concurrent_validation_of_one_receipt_applies_it_once(pg: Session, refs) -> None:
    receipt = new_receipt(pg, refs, [("product", 100), ("other_product", 5)])

    def validate(db: Session) -> None:
        receipt_service.validate_receipt(db, receipt.id, refs["user"])

    errors = run_concurrently(pg.get_bind(), [validate] * 8)
    assert len(errors) == 7 and all(isinstance(e, InvalidTransitionError) for e in errors), errors
    assert qty(pg, refs) == 100 and qty(pg, refs, "other_product") == 5
    assert len(ledger(pg)) == 2


def test_competing_deliveries_cannot_oversell(pg: Session, refs) -> None:
    receipt_service.validate_receipt(pg, new_receipt(pg, refs, [("product", 10)]).id, refs["user"])
    deliveries = [new_delivery(pg, refs, [("product", 4)]) for _ in range(4)]
    assert all(d.status is DeliveryStatus.READY for d in deliveries)  # 4 x 4 > 10: advisory

    def validator(delivery_id: int):
        return lambda db: delivery_service.validate_delivery(db, delivery_id, refs["user"])

    assert run_concurrently(pg.get_bind(), [validator(d.id) for d in deliveries]) == []
    pg.expire_all()
    statuses = sorted(delivery_service.get_delivery(pg, d.id).status.value for d in deliveries)
    assert statuses == ["DONE", "DONE", "WAITING", "WAITING"]
    assert qty(pg, refs) == 2
    assert ledger_balance(pg, refs["product"], refs["loc_a"]) == 2


def test_validate_and_cancel_race_leaves_a_consistent_delivery(pg: Session, refs) -> None:
    receipt_service.validate_receipt(pg, new_receipt(pg, refs, [("product", 50)]).id, refs["user"])
    for _ in range(5):
        delivery = new_delivery(pg, refs, [("product", 1)])
        errors = run_concurrently(pg.get_bind(), [
            lambda db: delivery_service.validate_delivery(db, delivery.id, refs["user"]),
            lambda db: delivery_service.cancel_delivery(db, delivery.id),
        ])
        assert len(errors) == 1 and isinstance(errors[0], InvalidTransitionError)
        pg.expire_all()
        final = delivery_service.get_delivery(pg, delivery.id).status
        moved = pg.scalar(select(func.count(StockMovement.id)).where(
            StockMovement.source_type == "delivery", StockMovement.source_id == delivery.id))
        assert (final, moved) in {(DeliveryStatus.DONE, 1), (DeliveryStatus.CANCELED, 0)}
    assert qty(pg, refs) == ledger_balance(pg, refs["product"], refs["loc_a"])


def test_mixed_receipts_and_deliveries_do_not_deadlock(pg: Session, refs) -> None:
    receipt_service.validate_receipt(
        pg, new_receipt(pg, refs, [("product", 10), ("other_product", 10)]).id, refs["user"])
    receipts = [new_receipt(pg, refs, [("other_product", 5), ("product", 5)]) for _ in range(4)]
    deliveries = [new_delivery(pg, refs, [("product", 3), ("other_product", 3)])
                  for _ in range(4)]
    work = [lambda db, r=r.id: receipt_service.validate_receipt(db, r, refs["user"])
            for r in receipts]
    work += [lambda db, d=d.id: delivery_service.validate_delivery(db, d, refs["user"])
             for d in deliveries]

    assert run_concurrently(pg.get_bind(), work) == []  # in particular no DeadlockDetected
    for product in ("product", "other_product"):
        on_hand = qty(pg, refs, product)
        assert on_hand >= 0
        assert on_hand == ledger_balance(pg, refs[product], refs["loc_a"])
