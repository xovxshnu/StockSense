"""Inventory Engine tests (app.services.inventory_service).

Behavior tests run on SQLite and, when TEST_POSTGRES_URL is set, on a migrated
PostgreSQL database (fixtures shared with test_stock_models). The concurrency
tests only run on PostgreSQL: SQLite serializes all writers and ignores
FOR UPDATE, so it proves nothing about row locking.
"""

import ast
import threading
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app
from app.models import Location, MovementType, Product, Stock, StockMovement
from app.services import inventory_service
from app.services.errors import InvalidReferenceError
from app.services.inventory_service import (
    InsufficientStockError,
    InvalidQuantityError,
    InvalidSourceError,
    SameLocationError,
    StockNotFoundError,
    adjust,
    deliver,
    receive,
    transfer,
)
from app.services.sequence_service import generate_reference
from tests.test_stock_models import pg_engine, refs, session  # noqa: F401 (fixtures)

APP_DIR = Path(app.__file__).resolve().parent


def source(refs: dict[str, int], reference: str = "WH/IN/0001", **overrides) -> dict:
    return {
        "reference": reference,
        "source_type": "test",
        "source_id": 1,
        "performed_by": refs["user"],
    } | overrides


def stock_at(db: Session, product_id: int, location_id: int) -> Stock | None:
    db.expire_all()  # read what the database holds, not the identity map
    return db.scalar(
        select(Stock).where(Stock.product_id == product_id, Stock.location_id == location_id)
    )


def movements(db: Session) -> list[StockMovement]:
    return list(db.scalars(select(StockMovement).order_by(StockMovement.id)))


def seed(db: Session, refs: dict[str, int], location: str, quantity: str, reserved: str = "0"):
    """Stock set up through the engine, then reservations set directly: nothing
    in the engine reserves stock yet, and these tests only need the state."""
    receive(
        db, product_id=refs["product"], location_id=refs[location],
        quantity=Decimal(quantity), **source(refs, "WH/IN/SEED"),
    )
    if reserved != "0":
        stock = stock_at(db, refs["product"], refs[location])
        stock.reserved_quantity = Decimal(reserved)
    db.commit()


def archive(db: Session, model, record_id: int) -> None:
    db.get(model, record_id).active = False
    db.commit()


# --- Receive (IN) -----------------------------------------------------------


def test_receive_into_empty_location(session: Session, refs) -> None:
    stock = receive(
        session, product_id=refs["product"], location_id=refs["loc_a"],
        quantity=Decimal("100"), **source(refs),
    )
    session.commit()
    assert stock.quantity == Decimal("100") and stock.reserved_quantity == 0
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("100")


def test_receive_into_existing_stock(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100", reserved="10")
    stock = receive(
        session, product_id=refs["product"], location_id=refs["loc_a"],
        quantity=Decimal("50"), **source(refs),
    )
    session.commit()
    stored = stock_at(session, refs["product"], refs["loc_a"])
    assert stock.id == stored.id and stored.quantity == Decimal("150")
    assert stored.reserved_quantity == Decimal("10")  # reservations untouched
    assert session.scalar(select(func.count(Stock.id))) == 1


def test_receive_creates_in_movement(session: Session, refs) -> None:
    reference = generate_reference(session, "WH/IN")
    receive(
        session, product_id=refs["product"], location_id=refs["loc_a"], quantity=Decimal("2.5"),
        reference=reference, source_type="receipt", source_id=7, performed_by=refs["user"],
    )
    session.commit()
    [movement] = movements(session)
    assert movement.movement_type is MovementType.IN
    assert (movement.from_location_id, movement.to_location_id) == (None, refs["loc_a"])
    assert movement.quantity == Decimal("2.5") and movement.reference == "WH/IN/0001"
    assert (movement.source_type, movement.source_id) == ("receipt", 7)
    assert movement.performed_by == refs["user"] and movement.product_id == refs["product"]


def test_receive_rejects_inactive_product(session: Session, refs) -> None:
    archive(session, Product, refs["product"])
    with pytest.raises(InvalidReferenceError, match="Product is archived"):
        receive(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=1, **source(refs))
    assert movements(session) == [] and stock_at(session, refs["product"], refs["loc_a"]) is None


def test_receive_rejects_inactive_location(session: Session, refs) -> None:
    archive(session, Location, refs["loc_a"])
    with pytest.raises(InvalidReferenceError, match="Location is archived"):
        receive(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=1, **source(refs))
    assert movements(session) == []


@pytest.mark.parametrize(
    "field, message", [("product_id", "Product not found"), ("location_id", "Location not found"),
                       ("performed_by", "user not found")],
)
def test_receive_rejects_missing_references(session: Session, refs, field, message) -> None:
    args = {"product_id": refs["product"], "location_id": refs["loc_a"], "quantity": 1,
            **source(refs), field: 999_999}
    with pytest.raises(InvalidReferenceError, match=message):
        receive(session, **args)
    assert movements(session) == []


@pytest.mark.parametrize(
    "quantity",
    [0, -1, Decimal("0"), Decimal("-0.001"), Decimal("1.0001"), Decimal("NaN"),
     Decimal("Infinity"), 1.5, True, "5", None],
)
def test_receive_rejects_invalid_quantity(session: Session, refs, quantity) -> None:
    with pytest.raises(InvalidQuantityError):
        receive(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=quantity, **source(refs))
    assert movements(session) == []


@pytest.mark.parametrize("field", ["reference", "source_type"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_movement_source_is_required(session: Session, refs, field, value) -> None:
    with pytest.raises(InvalidSourceError):
        receive(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=1, **source(refs, **{field: value}))


def test_int_quantities_are_accepted(session: Session, refs) -> None:
    stock = receive(session, product_id=refs["product"], location_id=refs["loc_a"],
                    quantity=3, **source(refs))
    assert stock.quantity == Decimal("3")


# --- Deliver (OUT) ----------------------------------------------------------


def test_successful_delivery(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    stock = deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                    quantity=Decimal("20"), **source(refs, "WH/OUT/0001"))
    session.commit()
    assert stock.quantity == Decimal("80")
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("80")


def test_delivery_creates_out_movement(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
            quantity=Decimal("20"), **source(refs, "WH/OUT/0001", source_type="delivery"))
    session.commit()
    out = movements(session)[-1]
    assert out.movement_type is MovementType.OUT and out.quantity == Decimal("20")
    assert (out.from_location_id, out.to_location_id) == (refs["loc_a"], None)
    assert out.reference == "WH/OUT/0001" and out.source_type == "delivery"


def test_delivery_rejects_missing_stock(session: Session, refs) -> None:
    with pytest.raises(StockNotFoundError):
        deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=1, **source(refs))
    assert movements(session) == []


def test_delivery_rejects_insufficient_stock(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    with pytest.raises(InsufficientStockError):
        deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=Decimal("10.001"), **source(refs))
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("10")
    assert len(movements(session)) == 1  # only the seed


def test_delivery_cannot_use_reserved_stock(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10", reserved="4")
    with pytest.raises(InsufficientStockError, match="free 6"):
        deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=7, **source(refs))
    stock = stock_at(session, refs["product"], refs["loc_a"])
    assert (stock.quantity, stock.reserved_quantity) == (Decimal("10"), Decimal("4"))


def test_delivery_may_use_exactly_the_free_stock(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10", reserved="4")
    stock = deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                    quantity=6, **source(refs))
    session.commit()
    assert (stock.quantity, stock.reserved_quantity, stock.free_to_use) == (4, 4, 0)


@pytest.mark.parametrize("model, key, message", [(Product, "product", "Product is archived"),
                                                 (Location, "loc_a", "Location is archived")])
def test_delivery_rejects_inactive_product_or_location(
    session: Session, refs, model, key, message
) -> None:
    seed(session, refs, "loc_a", "10")
    archive(session, model, refs[key])
    with pytest.raises(InvalidReferenceError, match=message):
        deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=1, **source(refs))
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("10")


# --- Transfer ---------------------------------------------------------------


def do_transfer(session: Session, refs, quantity, from_loc="loc_a", to_loc="loc_b"):
    return transfer(
        session, product_id=refs["product"], from_location_id=refs[from_loc],
        to_location_id=refs[to_loc], quantity=quantity, **source(refs, "WH/INT/0001"),
    )


def test_successful_transfer_into_new_destination(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    src, dst = do_transfer(session, refs, Decimal("30"))
    session.commit()
    assert (src.location_id, dst.location_id) == (refs["loc_a"], refs["loc_b"])
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("70")
    assert stock_at(session, refs["product"], refs["loc_b"]).quantity == Decimal("30")


def test_transfer_into_existing_destination(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    seed(session, refs, "loc_b", "5", reserved="5")
    do_transfer(session, refs, 30)
    session.commit()
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("70")
    destination = stock_at(session, refs["product"], refs["loc_b"])
    assert (destination.quantity, destination.reserved_quantity) == (35, 5)


def test_transfer_in_either_direction_order(session: Session, refs) -> None:
    """Covers both lock orders: source id below and above destination id."""
    seed(session, refs, "loc_a", "100")
    do_transfer(session, refs, 30)  # a -> b
    do_transfer(session, refs, 10, "loc_b", "loc_a")  # b -> a
    session.commit()
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("80")
    assert stock_at(session, refs["product"], refs["loc_b"]).quantity == Decimal("20")


def test_transfer_creates_one_transfer_movement(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    do_transfer(session, refs, 30)
    session.commit()
    [_, moved] = movements(session)
    assert moved.movement_type is MovementType.TRANSFER and moved.quantity == Decimal("30")
    assert (moved.from_location_id, moved.to_location_id) == (refs["loc_a"], refs["loc_b"])
    total = session.scalar(select(func.sum(Stock.quantity)).where(
        Stock.product_id == refs["product"]))
    assert total == Decimal("100")  # company-wide stock unchanged


def test_transfer_rejects_same_location(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    with pytest.raises(SameLocationError):
        do_transfer(session, refs, 1, "loc_a", "loc_a")
    assert len(movements(session)) == 1


def test_transfer_rejects_insufficient_free_stock(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10", reserved="8")
    with pytest.raises(InsufficientStockError):
        do_transfer(session, refs, 3)
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("10")
    # The destination row is not created for a transfer that cannot happen.
    assert stock_at(session, refs["product"], refs["loc_b"]) is None
    assert len(movements(session)) == 1


def test_transfer_rejects_missing_source_stock(session: Session, refs) -> None:
    with pytest.raises(StockNotFoundError):
        do_transfer(session, refs, 1)
    assert session.scalar(select(func.count(Stock.id))) == 0


@pytest.mark.parametrize("key, message", [("loc_a", "Source location is archived"),
                                          ("loc_b", "Destination location is archived")])
def test_transfer_rejects_inactive_location(session: Session, refs, key, message) -> None:
    seed(session, refs, "loc_a", "10")
    archive(session, Location, refs[key])
    with pytest.raises(InvalidReferenceError, match=message):
        do_transfer(session, refs, 1)
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("10")


def test_failed_transfer_leaves_both_stocks_unchanged(
    session: Session, refs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure AFTER both rows were changed in the session (while recording the
    movement): the caller's rollback must undo source, destination and movement."""
    seed(session, refs, "loc_a", "100")
    seed(session, refs, "loc_b", "5")

    def fail(*_args, **_kwargs):
        raise RuntimeError("simulated failure while recording the movement")

    monkeypatch.setattr(inventory_service, "_record", fail)
    with pytest.raises(RuntimeError):
        do_transfer(session, refs, 30)
    session.rollback()

    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("100")
    assert stock_at(session, refs["product"], refs["loc_b"]).quantity == Decimal("5")
    assert [m.movement_type for m in movements(session)] == [MovementType.IN, MovementType.IN]


# --- Adjust -----------------------------------------------------------------


def do_adjust(session: Session, refs, quantity, location="loc_a"):
    return adjust(session, product_id=refs["product"], location_id=refs[location],
                  quantity=quantity, **source(refs, "WH/ADJ/0001", source_type="adjustment"))


def test_positive_adjustment(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    stock = do_adjust(session, refs, Decimal("4"))
    session.commit()
    assert stock.quantity == Decimal("14")


def test_negative_adjustment(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    stock = do_adjust(session, refs, Decimal("-3"))
    session.commit()
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("7")
    assert stock.quantity == Decimal("7")


def test_adjustment_creates_signed_movement(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    do_adjust(session, refs, Decimal("-3"))
    session.commit()
    adjustment = movements(session)[-1]
    assert adjustment.movement_type is MovementType.ADJUSTMENT
    assert adjustment.quantity == Decimal("-3")
    assert (adjustment.from_location_id, adjustment.to_location_id) == (None, refs["loc_a"])


def test_negative_adjustment_cannot_make_stock_negative(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    with pytest.raises(InsufficientStockError, match="negative"):
        do_adjust(session, refs, Decimal("-10.5"))
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("10")
    assert len(movements(session)) == 1


def test_negative_adjustment_may_empty_the_stock(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    assert do_adjust(session, refs, -10).quantity == 0


def test_negative_adjustment_cannot_go_below_reserved(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10", reserved="8")
    with pytest.raises(InsufficientStockError, match="below the reserved 8"):
        do_adjust(session, refs, Decimal("-3"))
    stock = stock_at(session, refs["product"], refs["loc_a"])
    assert (stock.quantity, stock.reserved_quantity) == (Decimal("10"), Decimal("8"))


def test_negative_adjustment_requires_existing_stock(session: Session, refs) -> None:
    with pytest.raises(StockNotFoundError):
        do_adjust(session, refs, -1)
    assert session.scalar(select(func.count(Stock.id))) == 0


def test_positive_adjustment_creates_missing_stock(session: Session, refs) -> None:
    stock = do_adjust(session, refs, Decimal("5"), location="loc_b")
    session.commit()
    assert stock_at(session, refs["product"], refs["loc_b"]).quantity == Decimal("5")
    assert stock.reserved_quantity == 0


def test_zero_adjustment_rejected(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    with pytest.raises(InvalidQuantityError):
        do_adjust(session, refs, 0)


def test_adjustment_rejects_inactive_product(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "10")
    archive(session, Product, refs["product"])
    with pytest.raises(InvalidReferenceError, match="Product is archived"):
        do_adjust(session, refs, 1)


# --- Transactions -----------------------------------------------------------


def test_engine_does_not_commit(session: Session, refs) -> None:
    receive(session, product_id=refs["product"], location_id=refs["loc_a"],
            quantity=5, **source(refs))
    assert session.in_transaction()
    session.rollback()
    assert stock_at(session, refs["product"], refs["loc_a"]) is None
    assert movements(session) == []


def test_stock_and_movement_roll_back_together(session: Session, refs) -> None:
    seed(session, refs, "loc_a", "100")
    deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
            quantity=20, **source(refs))
    do_adjust(session, refs, -3)
    session.rollback()  # e.g. the operation document failed to save afterwards
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("100")
    assert [m.movement_type for m in movements(session)] == [MovementType.IN]


def test_failed_step_rolls_back_earlier_steps_of_the_same_document(
    session: Session, refs
) -> None:
    """A two-line document: line 1 succeeds, line 2 is refused, caller rolls back."""
    seed(session, refs, "loc_a", "10")
    deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
            quantity=6, **source(refs))
    with pytest.raises(InsufficientStockError):
        deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=6, **source(refs))
    session.rollback()
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("10")
    assert len(movements(session)) == 1


def test_several_changes_in_one_transaction_accumulate(session: Session, refs) -> None:
    """Each call flushes, so the next call's locked re-read sees the change."""
    for _ in range(3):
        receive(session, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=10, **source(refs))
    deliver(session, product_id=refs["product"], location_id=refs["loc_a"],
            quantity=25, **source(refs))
    session.commit()
    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == Decimal("5")
    assert len(movements(session)) == 4


def test_blueprint_core_flow(session: Session, refs) -> None:
    """Blueprint section 14, engine level: receive 100, transfer 30, deliver 20, adjust -3."""
    common = {"product_id": refs["product"], "performed_by": refs["user"]}
    receive(session, location_id=refs["loc_a"], quantity=100,
            reference=generate_reference(session, "WH/IN"), source_type="receipt",
            source_id=1, **common)
    transfer(session, from_location_id=refs["loc_a"], to_location_id=refs["loc_b"],
             quantity=30, reference=generate_reference(session, "WH/INT"),
             source_type="transfer", source_id=1, **common)
    deliver(session, location_id=refs["loc_b"], quantity=20,
            reference=generate_reference(session, "WH/OUT"), source_type="delivery",
            source_id=1, **common)
    adjust(session, location_id=refs["loc_b"], quantity=-3,
           reference=generate_reference(session, "WH/ADJ"), source_type="adjustment",
           source_id=1, **common)
    session.commit()

    assert stock_at(session, refs["product"], refs["loc_a"]).quantity == 70
    assert stock_at(session, refs["product"], refs["loc_b"]).quantity == 7
    assert [(m.reference, m.movement_type.value, m.quantity) for m in movements(session)] == [
        ("WH/IN/0001", "IN", 100),
        ("WH/INT/0001", "TRANSFER", 30),
        ("WH/OUT/0001", "OUT", 20),
        ("WH/ADJ/0001", "ADJUSTMENT", -3),
    ]


# --- Architecture guard -----------------------------------------------------


STOCK_FIELDS = {"quantity", "reserved_quantity"}
ENGINE = APP_DIR / "services" / "inventory_service.py"


def stock_mutations(path: Path) -> list[str]:
    """In a module that imports Stock: writes to Stock quantities or rows."""
    tree = ast.parse(path.read_text())
    imports_stock = any(
        isinstance(node, ast.ImportFrom) and any(a.name == "Stock" for a in node.names)
        for node in ast.walk(tree)
    )
    if not imports_stock:
        return []
    found = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr in STOCK_FIELDS:
                found.append(f"{path.name}:{node.lineno} assigns .{target.attr}")
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            first = node.args[0] if node.args else None
            if name == "Stock":
                found.append(f"{path.name}:{node.lineno} constructs Stock")
            if name in {"insert", "update", "delete"} and getattr(first, "id", None) == "Stock":
                found.append(f"{path.name}:{node.lineno} {name}(Stock)")
    return found


def test_only_the_engine_mutates_stock() -> None:
    offenders = [
        hit
        for path in APP_DIR.rglob("*.py")
        if path != ENGINE and path.parent.name != "models"
        for hit in stock_mutations(path)
    ]
    assert offenders == []


def test_guard_detects_mutations() -> None:
    assert len(stock_mutations(ENGINE)) >= 4  # the engine itself is flagged


# --- Concurrency (PostgreSQL only) ------------------------------------------


def run_concurrently(engine, workers: list[Callable[[Session], None]]) -> list[BaseException]:
    """Start all workers at once, each in its own session/transaction."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    barrier = threading.Barrier(len(workers))
    errors: list[BaseException] = []
    lock = threading.Lock()

    def run(work) -> None:
        with factory() as db:
            try:
                barrier.wait()
                work(db)
            except BaseException as exc:  # noqa: BLE001 - reported to the test
                db.rollback()
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=run, args=(w,)) for w in workers]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert not any(t.is_alive() for t in threads), "worker hung (deadlock?)"
    return errors


@pytest.fixture
def pg(session: Session) -> Session:
    if session.get_bind().dialect.name != "postgresql":
        pytest.skip("row locking can only be demonstrated on PostgreSQL")
    return session


def test_concurrent_deliveries_cannot_oversell(pg: Session, refs) -> None:
    seed(pg, refs, "loc_a", "10")

    def deliver_three(db: Session) -> None:
        deliver(db, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=3, **source(refs, "WH/OUT/C"))
        db.commit()

    errors = run_concurrently(pg.get_bind(), [deliver_three] * 8)

    assert all(isinstance(e, InsufficientStockError) for e in errors), errors
    assert len(errors) == 5  # exactly 3 x 3 = 9 of the 10 could be delivered
    assert stock_at(pg, refs["product"], refs["loc_a"]).quantity == Decimal("1")
    assert len([m for m in movements(pg) if m.movement_type is MovementType.OUT]) == 3


def test_concurrent_opposite_transfers_do_not_deadlock_or_corrupt(pg: Session, refs) -> None:
    seed(pg, refs, "loc_a", "50")
    seed(pg, refs, "loc_b", "50")

    def mover(from_loc: str, to_loc: str):
        def work(db: Session) -> None:
            for _ in range(15):
                try:
                    transfer(db, product_id=refs["product"], from_location_id=refs[from_loc],
                             to_location_id=refs[to_loc], quantity=Decimal("4"),
                             **source(refs, "WH/INT/C"))
                    db.commit()
                except InsufficientStockError:
                    db.rollback()
        return work

    workers = [mover("loc_a", "loc_b"), mover("loc_b", "loc_a")] * 4
    errors = run_concurrently(pg.get_bind(), workers)
    assert errors == []  # in particular no DeadlockDetected

    a = stock_at(pg, refs["product"], refs["loc_a"]).quantity
    b = stock_at(pg, refs["product"], refs["loc_b"]).quantity
    assert a >= 0 and b >= 0 and a + b == Decimal("100")
    # The ledger explains the final state exactly.
    for loc, final in (("loc_a", a), ("loc_b", b)):
        net = sum(
            (m.quantity if m.to_location_id == refs[loc] else -m.quantity)
            for m in movements(pg)
            if refs[loc] in (m.from_location_id, m.to_location_id)
        )
        assert net == final


def test_concurrent_receipts_create_one_stock_row(pg: Session, refs) -> None:
    def receive_five(db: Session) -> None:
        receive(db, product_id=refs["product"], location_id=refs["loc_b"],
                quantity=5, **source(refs, "WH/IN/C"))
        db.commit()

    assert run_concurrently(pg.get_bind(), [receive_five] * 8) == []
    assert stock_at(pg, refs["product"], refs["loc_b"]).quantity == Decimal("40")
    assert pg.scalar(select(func.count(Stock.id))) == 1
    assert len(movements(pg)) == 8


def test_archive_waits_for_in_flight_stock_change(pg: Session, refs) -> None:
    """FOR SHARE on the product: archiving it blocks until the receipt commits."""
    factory = sessionmaker(bind=pg.get_bind())
    with factory() as receiving, factory() as archiving:
        receive(receiving, product_id=refs["product"], location_id=refs["loc_a"],
                quantity=1, **source(refs))
        archiving.execute(select(func.set_config("lock_timeout", "200ms", True)))
        with pytest.raises(Exception, match="lock timeout"):
            archiving.get(Product, refs["product"]).active = False
            archiving.flush()
        archiving.rollback()
        receiving.commit()
