"""Inventory adjustments: a physical count at one location. DRAFT -> DONE only.

Each line carries the counted quantity (the only user input). Validation sets the
stock to that count, in one transaction:

    system     = current stock, read with SELECT ... FOR UPDATE (0 if no row)
    difference = counted - system
    inventory_service.adjust(quantity=difference)   -> one ADJUSTMENT movement

A frontend-supplied system quantity or difference is never accepted (the schema
rejects them). The values stored on a DRAFT line are a snapshot taken when the
draft was saved, for display only; validation overwrites them with the values
actually applied.

A line whose count equals the stock has difference 0: no engine call and no
movement (StockMovement forbids a zero quantity), but the line still records the
count. The engine refuses a count below the reserved quantity; the counted
quantity is never negative, so stock can never go negative either. If any line
fails nothing is kept and the adjustment stays DRAFT.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.adjustment import Adjustment, AdjustmentLine, AdjustmentStatus
from app.models.location import Location
from app.models.stock import Stock
from app.schemas.adjustment import AdjustmentCreate, AdjustmentLineIn, AdjustmentUpdate
from app.services import delivery_service, inventory_service
from app.services.errors import InvalidReferenceError, NotFoundError
from app.services.inventory_service import InventoryError
from app.services.operation_common import (
    by_product,
    check_products,
    check_user,
    escape_like,
    lock_document,
    require_status,
)
from app.services.sequence_service import generate_reference

REFERENCE_PREFIX = "WH/ADJ"
SOURCE_TYPE = "adjustment"  # StockMovement.source_type for movements an adjustment creates
LABEL = "Adjustment"


class StockChangedError(InventoryError):
    """The stock row appeared while the count was being applied; retry."""


def list_adjustments(
    db: Session, search: str | None = None, status: AdjustmentStatus | None = None
) -> list[Adjustment]:
    query = (
        select(Adjustment).options(selectinload(Adjustment.lines)).order_by(Adjustment.id.desc())
    )
    if status is not None:
        query = query.where(Adjustment.status == status)
    if search and search.strip():
        query = query.where(
            Adjustment.reference.ilike(f"%{escape_like(search.strip())}%", escape="\\")
        )
    return list(db.scalars(query))


def get_adjustment(db: Session, adjustment_id: int) -> Adjustment:
    adjustment = db.get(Adjustment, adjustment_id)
    if adjustment is None:
        raise NotFoundError("Adjustment not found")
    return adjustment


def _system_quantity(db: Session, product_id: int, location_id: int, *, lock: bool) -> Decimal:
    """Current on-hand quantity (read only; the engine alone changes stock)."""
    query = select(Stock.quantity).where(
        Stock.product_id == product_id, Stock.location_id == location_id
    )
    if lock:
        query = query.with_for_update()
    quantity = db.scalar(query)
    return Decimal(str(quantity)) if quantity is not None else Decimal("0")


def _snapshot(db: Session, adjustment: Adjustment) -> None:
    """Refresh the display values of existing draft lines: stock as of now, not locked."""
    for line in adjustment.lines:
        line.system_quantity = _system_quantity(
            db, line.product_id, adjustment.location_id, lock=False
        )
        line.difference = line.counted_quantity - line.system_quantity


def _new_lines(
    db: Session, location_id: int, lines: list[AdjustmentLineIn]
) -> list[AdjustmentLine]:
    """New lines with their display snapshot already set (never flushed without it)."""
    new = []
    for line in lines:
        system = _system_quantity(db, line.product_id, location_id, lock=False)
        new.append(AdjustmentLine(
            product_id=line.product_id,
            counted_quantity=line.counted_quantity,
            system_quantity=system,
            difference=line.counted_quantity - system,
        ))
    return new


def _check_references(db: Session, adjustment: Adjustment) -> None:
    location = db.get(Location, adjustment.location_id)
    if location is None:
        raise InvalidReferenceError("location_id does not exist")
    if not location.active:
        raise InvalidReferenceError("location_id is archived")
    check_user(db, adjustment.responsible_user_id, "responsible_user_id")
    check_products(db, (line.product_id for line in adjustment.lines))


def _blank_reason_to_null(adjustment: Adjustment) -> None:
    if adjustment.reason is not None and not adjustment.reason.strip():
        adjustment.reason = None


def _commit(db: Session, adjustment: Adjustment) -> Adjustment:
    try:
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(adjustment)  # server-side timestamps
    return adjustment


def create_adjustment(db: Session, data: AdjustmentCreate) -> Adjustment:
    adjustment = Adjustment(
        **data.model_dump(exclude={"lines"}),
        lines=_new_lines(db, data.location_id, data.lines),
    )
    _blank_reason_to_null(adjustment)
    try:
        _check_references(db, adjustment)
        # Same transaction as the insert: a failed create does not use up a number.
        adjustment.reference = generate_reference(db, REFERENCE_PREFIX)
        db.add(adjustment)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, adjustment)


def update_adjustment(db: Session, adjustment_id: int, data: AdjustmentUpdate) -> Adjustment:
    try:
        adjustment = lock_document(db, Adjustment, adjustment_id, LABEL)
        require_status(adjustment, {AdjustmentStatus.DRAFT}, "edit", LABEL)
        for field, value in data.model_dump(exclude_unset=True, exclude={"lines"}).items():
            setattr(adjustment, field, value)
        _blank_reason_to_null(adjustment)
        if data.lines is not None:
            # Old lines first (flush), so a kept product does not collide with
            # the one-line-per-product rule.
            adjustment.lines.clear()
            db.flush()
            adjustment.lines.extend(_new_lines(db, adjustment.location_id, data.lines))
        else:
            _snapshot(db, adjustment)  # the location may have changed
        _check_references(db, adjustment)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, adjustment)


def validate_adjustment(db: Session, adjustment_id: int, performed_by: int) -> Adjustment:
    """DRAFT -> DONE: set each product's stock at the location to its count."""
    try:
        adjustment = lock_document(db, Adjustment, adjustment_id, LABEL)
        require_status(adjustment, {AdjustmentStatus.DRAFT}, "validate", LABEL)
        _check_references(db, adjustment)
        increased = False
        for line in by_product(adjustment.lines):
            system = _system_quantity(db, line.product_id, adjustment.location_id, lock=True)
            difference = line.counted_quantity - system
            line.system_quantity, line.difference = system, difference
            if difference == 0:
                continue  # already matches: nothing to change, no movement
            stock = inventory_service.adjust(
                db,
                product_id=line.product_id,
                location_id=adjustment.location_id,
                quantity=difference,
                reference=adjustment.reference,
                source_type=SOURCE_TYPE,
                source_id=adjustment.id,
                performed_by=performed_by,
            )
            if stock.quantity != line.counted_quantity:
                # Only possible when there was no stock row to lock above and a
                # concurrent transaction created one before the engine locked it.
                raise StockChangedError(
                    "Stock changed while the count was being applied; validate again"
                )
            increased = increased or difference > 0
        adjustment.status = AdjustmentStatus.DONE
        if increased:
            delivery_service.promote_waiting_deliveries(db, adjustment.location_id)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, adjustment)
