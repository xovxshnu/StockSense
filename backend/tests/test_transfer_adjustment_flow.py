"""Transfers and adjustments end to end, at service level.

Runs on SQLite and, with TEST_POSTGRES_URL, on migrated PostgreSQL. The
concurrency tests only run on PostgreSQL.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app
from app.models import (
    AdjustmentStatus,
    DeliveryStatus,
    MovementType,
    StockMovement,
    TransferStatus,
)
from app.schemas.adjustment import AdjustmentCreate
from app.schemas.transfer import TransferCreate
from app.services import (
    adjustment_service,
    delivery_service,
    inventory_service,
    receipt_service,
    transfer_service,
)
from app.services.adjustment_service import StockChangedError
from app.services.inventory_service import InsufficientStockError
from app.services.operation_common import InvalidTransitionError
from tests.test_inventory_service import run_concurrently, stock_mutations
from tests.test_operation_flow import ledger_balance, new_delivery, new_receipt, qty
from tests.test_stock_models import pg_engine, refs, session  # noqa: F401 (fixtures)

SERVICES = Path(app.__file__).resolve().parent / "services"


def new_transfer(db: Session, refs, lines, from_loc="loc_a", to_loc="loc_b"):
    transfer = transfer_service.create_transfer(db, TransferCreate(
        from_location_id=refs[from_loc], to_location_id=refs[to_loc],
        schedule_date="2026-10-03",
        lines=[{"product_id": refs[p], "quantity": q} for p, q in lines],
    ))
    return transfer_service.mark_transfer_todo(db, transfer.id)


def new_adjustment(db: Session, refs, lines, location="loc_a"):
    return adjustment_service.create_adjustment(db, AdjustmentCreate(
        location_id=refs[location],
        lines=[{"product_id": refs[p], "counted_quantity": q} for p, q in lines],
    ))


def receive(db: Session, refs, lines, location="loc_a") -> None:
    receipt = new_receipt(db, refs, lines, location)
    receipt_service.validate_receipt(db, receipt.id, refs["user"])


def history(db: Session) -> list[tuple]:
    """Move History as the blueprint shows it: reference, type, signed quantity."""
    db.expire_all()
    return [
        (m.reference, m.movement_type.value, m.quantity)
        for m in db.scalars(select(StockMovement).order_by(StockMovement.id))
    ]


def assert_adjustments_saw_the_real_stock(db: Session) -> None:
    """For every applied adjustment line: the system quantity it recorded equals
    the ledger balance just before its own movement, i.e. the difference was
    computed from the stock it actually changed, never from a stale read."""
    db.expire_all()
    ordered = list(db.scalars(select(StockMovement).order_by(StockMovement.id)))
    for movement in ordered:
        if movement.movement_type is not MovementType.ADJUSTMENT:
            continue
        before = Decimal("0")
        for earlier in ordered:
            if earlier.id >= movement.id or earlier.product_id != movement.product_id:
                continue
            if earlier.to_location_id == movement.to_location_id:
                before += earlier.quantity
            if earlier.from_location_id == movement.to_location_id:
                before -= earlier.quantity
        [line] = [
            l for l in adjustment_service.get_adjustment(db, movement.source_id).lines
            if l.product_id == movement.product_id
        ]
        assert line.system_quantity == before, (movement.reference, line.system_quantity, before)
        assert line.difference == movement.quantity


def assert_ledger_matches_stock(db: Session, refs) -> None:
    for product in ("product", "other_product"):
        for location in ("loc_a", "loc_b"):
            on_hand = qty(db, refs, product, location) or Decimal("0")
            assert on_hand >= 0
            assert ledger_balance(db, refs[product], refs[location]) == on_hand, (product, location)


# --- Flows ------------------------------------------------------------------


def test_blueprint_core_flow(session: Session, refs) -> None:
    """Blueprint section 14: receive 100 -> transfer 30 -> deliver 20 -> adjust -3."""
    user = refs["user"]
    receive(session, refs, [("product", 100)])
    assert qty(session, refs) == 100

    transfer = new_transfer(session, refs, [("product", 30)])
    transfer_service.validate_transfer(session, transfer.id, user)
    assert (qty(session, refs, location="loc_a"), qty(session, refs, location="loc_b")) == (70, 30)

    delivery = new_delivery(session, refs, [("product", 20)], location="loc_b")
    delivery_service.validate_delivery(session, delivery.id, user)
    assert qty(session, refs, location="loc_b") == 10

    adjustment = new_adjustment(session, refs, [("product", 7)], location="loc_b")
    done = adjustment_service.validate_adjustment(session, adjustment.id, user)
    assert done.status is AdjustmentStatus.DONE
    assert (done.lines[0].system_quantity, done.lines[0].difference) == (10, -3)

    assert qty(session, refs, location="loc_a") == 70
    assert qty(session, refs, location="loc_b") == 7
    assert history(session) == [
        ("WH/IN/0001", "IN", 100),
        ("WH/INT/0001", "TRANSFER", 30),
        ("WH/OUT/0001", "OUT", 20),
        ("WH/ADJ/0001", "ADJUSTMENT", -3),
    ]
    assert_ledger_matches_stock(session, refs)


def test_receipt_transfer_delivery(session: Session, refs) -> None:
    receive(session, refs, [("product", 40), ("other_product", 10)])
    transfer = new_transfer(session, refs, [("product", 15), ("other_product", 10)])
    transfer_service.validate_transfer(session, transfer.id, refs["user"])
    delivery = new_delivery(session, refs, [("product", 15), ("other_product", 10)], "loc_b")
    assert delivery.status is DeliveryStatus.READY
    delivery_service.validate_delivery(session, delivery.id, refs["user"])

    assert qty(session, refs, location="loc_a") == 25
    assert qty(session, refs, location="loc_b") == 0
    assert qty(session, refs, "other_product", "loc_b") == 0
    assert [t for _, t, _ in history(session)].count("TRANSFER") == 2
    assert_ledger_matches_stock(session, refs)


def test_receipt_then_adjustment(session: Session, refs) -> None:
    receive(session, refs, [("product", 50)])
    adjustment = new_adjustment(session, refs, [("product", 48), ("other_product", 3)])
    adjustment_service.validate_adjustment(session, adjustment.id, refs["user"])
    assert qty(session, refs) == 48 and qty(session, refs, "other_product") == 3
    assert sorted(q for _, t, q in history(session) if t == "ADJUSTMENT") == [-2, 3]
    assert_ledger_matches_stock(session, refs)


def test_transfer_then_adjustment(session: Session, refs) -> None:
    receive(session, refs, [("product", 20)])
    transfer = new_transfer(session, refs, [("product", 12)])
    transfer_service.validate_transfer(session, transfer.id, refs["user"])
    adjustment = new_adjustment(session, refs, [("product", 11)], location="loc_b")
    adjustment_service.validate_adjustment(session, adjustment.id, refs["user"])
    assert (qty(session, refs, location="loc_a"), qty(session, refs, location="loc_b")) == (8, 11)
    assert history(session)[-1][1:] == ("ADJUSTMENT", -1)
    assert_ledger_matches_stock(session, refs)


def test_multi_line_transfer_is_atomic(session: Session, refs) -> None:
    receive(session, refs, [("product", 50), ("other_product", 2)])
    transfer = new_transfer(session, refs, [("product", 30), ("other_product", 5)])
    with pytest.raises(InsufficientStockError):
        transfer_service.validate_transfer(session, transfer.id, refs["user"])
    assert qty(session, refs) == 50 and qty(session, refs, location="loc_b") is None
    assert transfer_service.get_transfer(session, transfer.id).status is TransferStatus.READY
    assert [t for _, t, _ in history(session)] == ["IN", "IN"]


def test_multi_line_adjustment_is_atomic(
    session: Session, refs, monkeypatch: pytest.MonkeyPatch
) -> None:
    receive(session, refs, [("product", 10), ("other_product", 10)])
    adjustment = new_adjustment(session, refs, [("product", 4), ("other_product", 6)])
    real_adjust = inventory_service.adjust
    calls = []

    def fail_on_second_line(db, **kwargs):
        calls.append(kwargs["product_id"])
        if len(calls) == 2:
            raise RuntimeError("simulated crash on line 2")
        return real_adjust(db, **kwargs)

    monkeypatch.setattr(inventory_service, "adjust", fail_on_second_line)
    with pytest.raises(RuntimeError):
        adjustment_service.validate_adjustment(session, adjustment.id, refs["user"])
    assert len(calls) == 2
    assert qty(session, refs) == 10 and qty(session, refs, "other_product") == 10
    assert [t for _, t, _ in history(session)] == ["IN", "IN"]
    assert adjustment_service.get_adjustment(session, adjustment.id).status is AdjustmentStatus.DRAFT


# --- Architecture guard -----------------------------------------------------


@pytest.mark.parametrize("module", ["transfer_service.py", "adjustment_service.py"])
def test_services_never_write_stock(module: str) -> None:
    assert stock_mutations(SERVICES / module) == []


# --- Concurrency (PostgreSQL only) ------------------------------------------


@pytest.fixture
def pg(session: Session) -> Session:
    if session.get_bind().dialect.name != "postgresql":
        pytest.skip("row locking can only be demonstrated on PostgreSQL")
    return session


def validator(service, document_id: int, user: int):
    return lambda db: service(db, document_id, user)


def test_concurrent_opposite_multi_line_transfers(pg: Session, refs) -> None:
    receive(pg, refs, [("product", 50), ("other_product", 50)], "loc_a")
    receive(pg, refs, [("product", 50), ("other_product", 50)], "loc_b")
    lines = [("product", 4), ("other_product", 3)]
    transfers = [new_transfer(pg, refs, lines, "loc_a", "loc_b") for _ in range(6)]
    transfers += [new_transfer(pg, refs, lines, "loc_b", "loc_a") for _ in range(6)]

    errors = run_concurrently(pg.get_bind(), [
        validator(transfer_service.validate_transfer, t.id, refs["user"]) for t in transfers
    ])
    assert errors == []  # in particular no DeadlockDetected
    for product in ("product", "other_product"):  # conservation per product
        total = qty(pg, refs, product, "loc_a") + qty(pg, refs, product, "loc_b")
        assert total == 100
    assert qty(pg, refs, location="loc_a") == 50  # 6 out, 6 back
    assert_ledger_matches_stock(pg, refs)


def test_concurrent_validation_of_one_transfer_moves_once(pg: Session, refs) -> None:
    receive(pg, refs, [("product", 100)])
    transfer = new_transfer(pg, refs, [("product", 30)])
    errors = run_concurrently(pg.get_bind(), [
        validator(transfer_service.validate_transfer, transfer.id, refs["user"])
    ] * 8)
    assert len(errors) == 7 and all(isinstance(e, InvalidTransitionError) for e in errors), errors
    assert (qty(pg, refs, location="loc_a"), qty(pg, refs, location="loc_b")) == (70, 30)
    assert [t for _, t, _ in history(pg)].count("TRANSFER") == 1


def test_transfers_competing_for_stock(pg: Session, refs) -> None:
    receive(pg, refs, [("product", 10)])
    transfers = [new_transfer(pg, refs, [("product", 4)]) for _ in range(4)]
    errors = run_concurrently(pg.get_bind(), [
        validator(transfer_service.validate_transfer, t.id, refs["user"]) for t in transfers
    ])
    assert len(errors) == 2 and all(isinstance(e, InsufficientStockError) for e in errors), errors
    pg.expire_all()
    statuses = sorted(transfer_service.get_transfer(pg, t.id).status.value for t in transfers)
    assert statuses == ["DONE", "DONE", "READY", "READY"]
    assert (qty(pg, refs, location="loc_a"), qty(pg, refs, location="loc_b")) == (2, 8)
    assert_ledger_matches_stock(pg, refs)


def test_concurrent_adjustments_and_deliveries(pg: Session, refs) -> None:
    receive(pg, refs, [("product", 20)])
    deliveries = [new_delivery(pg, refs, [("product", 3)]) for _ in range(4)]
    adjustments = [new_adjustment(pg, refs, [("product", c)]) for c in (12, 9)]
    work = [validator(delivery_service.validate_delivery, d.id, refs["user"]) for d in deliveries]
    work += [validator(adjustment_service.validate_adjustment, a.id, refs["user"])
             for a in adjustments]

    assert run_concurrently(pg.get_bind(), work) == []
    pg.expire_all()
    for delivery in deliveries:
        # A short delivery becomes WAITING, and a later positive adjustment may
        # promote it back to READY; either way only a DONE delivery moved stock.
        status = delivery_service.get_delivery(pg, delivery.id).status
        assert status in {DeliveryStatus.DONE, DeliveryStatus.WAITING, DeliveryStatus.READY}
        outs = pg.scalars(select(StockMovement).where(
            StockMovement.source_type == "delivery", StockMovement.source_id == delivery.id)).all()
        assert len(outs) == (1 if status is DeliveryStatus.DONE else 0)
    movements = {m.source_id: m for m in pg.scalars(select(StockMovement).where(
        StockMovement.movement_type == MovementType.ADJUSTMENT))}
    for adjustment in adjustments:
        done = adjustment_service.get_adjustment(pg, adjustment.id)
        assert done.status is AdjustmentStatus.DONE
        [line] = done.lines
        # Each recorded difference is exactly what was applied, against the stock
        # the adjustment actually saw under its lock.
        assert line.difference == line.counted_quantity - line.system_quantity
        if line.difference:
            assert movements[adjustment.id].quantity == line.difference
    assert_adjustments_saw_the_real_stock(pg)
    assert_ledger_matches_stock(pg, refs)


def test_adjustment_racing_first_receipt_on_a_missing_row(pg: Session, refs) -> None:
    """No stock row exists, so there is nothing to lock when the count is read: a
    concurrent receipt may create the row first. The adjustment then either
    applies correctly or refuses (StockChangedError); it never applies a stale
    difference."""
    for _ in range(5):
        adjustment = new_adjustment(pg, refs, [("other_product", 5)], location="loc_b")
        receipt = new_receipt(pg, refs, [("other_product", 3)], location="loc_b")
        errors = run_concurrently(pg.get_bind(), [
            validator(adjustment_service.validate_adjustment, adjustment.id, refs["user"]),
            validator(receipt_service.validate_receipt, receipt.id, refs["user"]),
        ])
        assert all(isinstance(e, StockChangedError) for e in errors), errors
        assert_adjustments_saw_the_real_stock(pg)
        assert_ledger_matches_stock(pg, refs)


def test_row_created_inside_the_window_is_detected(
    pg: Session, refs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic version of the race above: a receipt creates and commits the
    stock row exactly between the adjustment's read (no row -> 0) and the engine's
    lock. The adjustment must refuse instead of adding its +5 on top of the 3."""
    adjustment = new_adjustment(pg, refs, [("other_product", 5)], location="loc_b")
    receipt = new_receipt(pg, refs, [("other_product", 3)], location="loc_b")
    real_read = adjustment_service._system_quantity

    def read_then_let_a_receipt_commit(db, product_id, location_id, *, lock):
        seen = real_read(db, product_id, location_id, lock=lock)
        if lock:
            with sessionmaker(bind=pg.get_bind())() as other:
                receipt_service.validate_receipt(other, receipt.id, refs["user"])
        return seen

    monkeypatch.setattr(adjustment_service, "_system_quantity", read_then_let_a_receipt_commit)
    with sessionmaker(bind=pg.get_bind())() as db:
        with pytest.raises(StockChangedError):
            adjustment_service.validate_adjustment(db, adjustment.id, refs["user"])

    assert qty(pg, refs, "other_product", "loc_b") == 3  # the receipt only
    assert [t for _, t, _ in history(pg)] == ["IN"]
    assert adjustment_service.get_adjustment(pg, adjustment.id).status is AdjustmentStatus.DRAFT
