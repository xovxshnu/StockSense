"""The Inventory Engine: the ONLY code that changes Stock.

Every public function here performs exactly one stock change and writes exactly
one StockMovement for it, in the caller's transaction:

    receive   -> IN          (+quantity at the destination)
    deliver   -> OUT         (-quantity at the source, never from reserved stock)
    transfer  -> TRANSFER    (-quantity at the source, +quantity at the destination)
    adjust    -> ADJUSTMENT  (signed quantity at one location)

Operation services (receipts, deliveries, ...) call these; nothing else may
assign Stock.quantity / Stock.reserved_quantity (tests/test_inventory_service.py
checks this).

Transactions
------------
The engine never commits or rolls back; it only flushes, so constraint errors
surface inside the call and later reads in the same transaction see the change.
The caller generates the reference (sequence_service), creates its document and
calls the engine in ONE transaction, then commits:

    reference = generate_reference(db, "WH/IN")
    receive(db, product_id=..., location_id=..., quantity=..., reference=reference, ...)
    db.commit()

Domain errors are raised before anything is written, so the session is still
usable after one. After any other exception the caller must roll back, which
undoes the stock change and its movement together.

Locking (PostgreSQL)
--------------------
* Stock rows are read with SELECT ... FOR UPDATE and changed in Python while
  locked, so concurrent operations on the same product/location are serialized
  and none of them works from a stale quantity.
* A missing row is created with INSERT ... ON CONFLICT DO NOTHING and then
  locked, so two transactions creating the same row cannot both insert it.
* Product and location rows are read FOR SHARE: they cannot be archived until the
  stock change commits, while other stock changes are not blocked.
* A transfer locks its two stock rows in ascending location_id order, so
  opposite-direction transfers of the same product cannot deadlock. Callers
  changing several rows in one transaction (multi-line documents) should also
  process lines in a stable order, e.g. by (product_id, location_id).
SQLite (unit tests) ignores FOR UPDATE / FOR SHARE and serializes writers.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.location import Location
from app.models.product import Product
from app.models.stock import Stock
from app.models.stock_movement import MovementType, StockMovement
from app.models.user import User
from app.services.errors import InvalidReferenceError

QUANTITY_SCALE = 3  # Stock/StockMovement quantities are NUMERIC(14, 3)


class InventoryError(Exception):
    """A requested stock change breaks an inventory rule. Nothing was written."""


class InvalidQuantityError(InventoryError, ValueError):
    """Zero, negative (where not allowed), non-decimal or over-precise quantity."""


class SameLocationError(InventoryError, ValueError):
    """A transfer whose source and destination are the same location."""


class InvalidSourceError(InventoryError, ValueError):
    """A movement without a reference or source_type (the document it records)."""


class StockNotFoundError(InventoryError):
    """No stock row exists for the product at the location being drawn from."""


class InsufficientStockError(InventoryError):
    """The change would use reserved stock or make the quantity negative."""


# --- Validation -------------------------------------------------------------


def _check_quantity(quantity: Decimal | int, *, signed: bool = False) -> Decimal:
    # bool is an int subclass and float is inexact: both are refused outright.
    if isinstance(quantity, bool) or not isinstance(quantity, (Decimal, int)):
        raise InvalidQuantityError("Quantity must be a Decimal or an int")
    value = Decimal(quantity)
    if not value.is_finite():
        raise InvalidQuantityError("Quantity must be a finite number")
    if value.as_tuple().exponent < -QUANTITY_SCALE:
        raise InvalidQuantityError(
            f"Quantity cannot have more than {QUANTITY_SCALE} decimal places"
        )
    if value == 0:
        raise InvalidQuantityError("Quantity cannot be zero")
    if value < 0 and not signed:
        raise InvalidQuantityError("Quantity must be positive")
    return value


def _check_source(reference: str, source_type: str) -> None:
    for name, value in (("reference", reference), ("source_type", source_type)):
        if not isinstance(value, str) or not value.strip():
            raise InvalidSourceError(f"Movement {name} is required")


def _active_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise InvalidReferenceError("Product not found")
    if not product.active:
        raise InvalidReferenceError("Product is archived")
    return product


def _active_location(db: Session, location_id: int, role: str = "Location") -> Location:
    location = db.scalar(
        select(Location)
        .where(Location.id == location_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if location is None:
        raise InvalidReferenceError(f"{role} not found")
    if not location.active:
        raise InvalidReferenceError(f"{role} is archived")
    return location


def _check_user(db: Session, user_id: int) -> None:
    if db.get(User, user_id) is None:
        raise InvalidReferenceError("performed_by user not found")


# --- Stock rows -------------------------------------------------------------


def _lock_stock(db: Session, product_id: int, location_id: int) -> Stock | None:
    """SELECT ... FOR UPDATE, refreshing any copy already in the session."""
    return db.scalar(
        select(Stock)
        .where(Stock.product_id == product_id, Stock.location_id == location_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _dialect_insert(db: Session):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":  # used by the unit tests
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError(f"Unsupported database dialect for stock: {dialect}")
    return insert


def _lock_or_create_stock(db: Session, product_id: int, location_id: int) -> Stock:
    stock = _lock_stock(db, product_id, location_id)
    if stock is not None:
        return stock
    # A concurrent transaction may be creating the same row: ON CONFLICT waits
    # for it and then does nothing, and the SELECT below locks whichever row won.
    insert = _dialect_insert(db)
    db.execute(
        insert(Stock)
        .values(product_id=product_id, location_id=location_id)
        .on_conflict_do_nothing(index_elements=[Stock.product_id, Stock.location_id])
    )
    stock = _lock_stock(db, product_id, location_id)
    if stock is None:  # impossible: the row was just inserted or already existed
        raise RuntimeError("Stock row vanished after upsert")
    return stock


def _record(
    db: Session,
    *,
    movement_type: MovementType,
    product_id: int,
    quantity: Decimal,
    reference: str,
    source_type: str,
    source_id: int,
    performed_by: int,
    from_location_id: int | None = None,
    to_location_id: int | None = None,
) -> StockMovement:
    movement = StockMovement(
        reference=reference,
        product_id=product_id,
        movement_type=movement_type,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        quantity=quantity,
        source_type=source_type,
        source_id=source_id,
        performed_by=performed_by,
    )
    db.add(movement)
    return movement


def _require_free(stock: Stock, quantity: Decimal, where: str) -> None:
    if quantity > stock.free_to_use:
        raise InsufficientStockError(
            f"Insufficient free stock at {where}: requested {quantity}, "
            f"free {stock.free_to_use} (on hand {stock.quantity}, "
            f"reserved {stock.reserved_quantity})"
        )


# --- Engine operations ------------------------------------------------------


def receive(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    quantity: Decimal | int,
    reference: str,
    source_type: str,
    source_id: int,
    performed_by: int,
) -> Stock:
    """Add `quantity` at `location_id` and record an IN movement."""
    amount = _check_quantity(quantity)
    _check_source(reference, source_type)
    _active_product(db, product_id)
    _active_location(db, location_id)
    _check_user(db, performed_by)

    stock = _lock_or_create_stock(db, product_id, location_id)
    stock.quantity += amount
    _record(
        db,
        movement_type=MovementType.IN,
        product_id=product_id,
        to_location_id=location_id,
        quantity=amount,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        performed_by=performed_by,
    )
    db.flush()
    return stock


def deliver(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    quantity: Decimal | int,
    reference: str,
    source_type: str,
    source_id: int,
    performed_by: int,
) -> Stock:
    """Remove `quantity` from the free stock at `location_id` and record an OUT
    movement. Reserved stock is never used."""
    amount = _check_quantity(quantity)
    _check_source(reference, source_type)
    _active_product(db, product_id)
    _active_location(db, location_id)
    _check_user(db, performed_by)

    stock = _lock_stock(db, product_id, location_id)
    if stock is None:
        raise StockNotFoundError("No stock of this product at the source location")
    _require_free(stock, amount, "the source location")

    stock.quantity -= amount
    _record(
        db,
        movement_type=MovementType.OUT,
        product_id=product_id,
        from_location_id=location_id,
        quantity=amount,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        performed_by=performed_by,
    )
    db.flush()
    return stock


def transfer(
    db: Session,
    *,
    product_id: int,
    from_location_id: int,
    to_location_id: int,
    quantity: Decimal | int,
    reference: str,
    source_type: str,
    source_id: int,
    performed_by: int,
) -> tuple[Stock, Stock]:
    """Move `quantity` of free stock between two locations and record ONE
    TRANSFER movement. Returns (source stock, destination stock)."""
    amount = _check_quantity(quantity)
    if from_location_id == to_location_id:
        raise SameLocationError("Source and destination locations must differ")
    _check_source(reference, source_type)
    _active_product(db, product_id)
    _active_location(db, from_location_id, "Source location")
    _active_location(db, to_location_id, "Destination location")
    _check_user(db, performed_by)

    # Lock existing rows in ascending location_id order (deadlock avoidance).
    locked = {
        location_id: _lock_stock(db, product_id, location_id)
        for location_id in sorted((from_location_id, to_location_id))
    }
    source = locked[from_location_id]
    if source is None:
        raise StockNotFoundError("No stock of this product at the source location")
    _require_free(source, amount, "the source location")
    # Created only once the transfer is known to be possible.
    destination = locked[to_location_id] or _lock_or_create_stock(
        db, product_id, to_location_id
    )

    source.quantity -= amount
    destination.quantity += amount
    _record(
        db,
        movement_type=MovementType.TRANSFER,
        product_id=product_id,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        quantity=amount,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        performed_by=performed_by,
    )
    db.flush()
    return source, destination


def adjust(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    quantity: Decimal | int,
    reference: str,
    source_type: str,
    source_id: int,
    performed_by: int,
) -> Stock:
    """Apply a signed correction at `location_id` and record an ADJUSTMENT
    movement carrying the same signed quantity. A decrease may not take the
    quantity below zero or below the reserved quantity."""
    amount = _check_quantity(quantity, signed=True)
    _check_source(reference, source_type)
    _active_product(db, product_id)
    _active_location(db, location_id)
    _check_user(db, performed_by)

    if amount > 0:
        stock = _lock_or_create_stock(db, product_id, location_id)
    else:
        stock = _lock_stock(db, product_id, location_id)
        if stock is None:
            raise StockNotFoundError("No stock of this product at the location to decrease")
        new_quantity = stock.quantity + amount
        if new_quantity < 0:
            raise InsufficientStockError(
                f"Adjustment of {amount} would make stock negative (on hand {stock.quantity})"
            )
        if new_quantity < stock.reserved_quantity:
            raise InsufficientStockError(
                f"Adjustment of {amount} would leave {new_quantity} on hand, "
                f"below the reserved {stock.reserved_quantity}"
            )

    stock.quantity += amount
    _record(
        db,
        movement_type=MovementType.ADJUSTMENT,
        product_id=product_id,
        to_location_id=location_id,
        quantity=amount,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        performed_by=performed_by,
    )
    db.flush()
    return stock
