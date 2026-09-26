"""Deliveries: outgoing goods.

    DRAFT --todo--> READY    (the free stock at the source covers every line)
    DRAFT --todo--> WAITING  (it does not)
    WAITING --todo--> READY / WAITING   (re-check on request)
    WAITING -> READY         (automatically, when a receipt adds stock at the source)
    READY --validate--> DONE     (stock removed via inventory_service.deliver)
    READY --validate--> WAITING  (stock no longer sufficient: nothing is removed)
    DRAFT / WAITING / READY --cancel--> CANCELED   (no stock is touched)

Availability is advisory until validation: nothing is reserved, so READY does not
guarantee the stock; validation re-checks it under row locks in the engine. Only
free stock (quantity - reserved_quantity) is ever delivered. A DONE delivery can
be neither edited nor cancelled (reversal is not defined by the blueprint).
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.contact import ContactType
from app.models.delivery import Delivery, DeliveryLine, DeliveryStatus
from app.models.stock import Stock
from app.schemas.delivery import DeliveryCreate, DeliveryUpdate
from app.services import inventory_service
from app.services.errors import NotFoundError
from app.services.inventory_service import InsufficientStockError, StockNotFoundError
from app.services.operation_common import (
    by_product,
    check_contact,
    check_products,
    check_user,
    check_warehouse_location,
    escape_like,
    lock_document,
    replace_lines,
    require_status,
)
from app.services.sequence_service import generate_reference

REFERENCE_PREFIX = "WH/OUT"
SOURCE_TYPE = "delivery"  # StockMovement.source_type for movements a delivery creates
LABEL = "Delivery"

_OPEN = {DeliveryStatus.DRAFT, DeliveryStatus.WAITING, DeliveryStatus.READY}


def list_deliveries(
    db: Session, search: str | None = None, status: DeliveryStatus | None = None
) -> list[Delivery]:
    query = select(Delivery).options(selectinload(Delivery.lines)).order_by(Delivery.id.desc())
    if status is not None:
        query = query.where(Delivery.status == status)
    if search and search.strip():
        query = query.where(
            Delivery.reference.ilike(f"%{escape_like(search.strip())}%", escape="\\")
        )
    return list(db.scalars(query))


def get_delivery(db: Session, delivery_id: int) -> Delivery:
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise NotFoundError("Delivery not found")
    return delivery


def _check_references(db: Session, delivery: Delivery) -> None:
    check_contact(db, delivery.customer_id, ContactType.CUSTOMER, "customer_id")
    check_warehouse_location(
        db, delivery.warehouse_id, delivery.source_location_id, "source_location_id"
    )
    check_user(db, delivery.responsible_user_id, "responsible_user_id")
    check_products(db, (line.product_id for line in delivery.lines))


def _free_to_use(db: Session, product_id: int, location_id: int) -> Decimal:
    """Read-only availability check; stock is only ever changed by the engine."""
    free = db.scalar(
        select(Stock.quantity - Stock.reserved_quantity).where(
            Stock.product_id == product_id, Stock.location_id == location_id
        )
    )
    return Decimal(str(free)) if free is not None else Decimal("0")


def _stock_covers(db: Session, delivery: Delivery) -> bool:
    return all(
        line.quantity <= _free_to_use(db, line.product_id, delivery.source_location_id)
        for line in delivery.lines
    )


def _commit(db: Session, delivery: Delivery) -> Delivery:
    try:
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(delivery)  # server-side timestamps
    return delivery


def _blank_address_to_null(delivery: Delivery) -> None:
    if delivery.delivery_address is not None and not delivery.delivery_address.strip():
        delivery.delivery_address = None


def create_delivery(db: Session, data: DeliveryCreate) -> Delivery:
    fields = data.model_dump(exclude={"lines"})
    delivery = Delivery(
        **fields,
        lines=[DeliveryLine(product_id=l.product_id, quantity=l.quantity) for l in data.lines],
    )
    _blank_address_to_null(delivery)
    try:
        _check_references(db, delivery)
        # Same transaction as the insert: a failed create does not use up a number.
        delivery.reference = generate_reference(db, REFERENCE_PREFIX)
        db.add(delivery)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, delivery)


def update_delivery(db: Session, delivery_id: int, data: DeliveryUpdate) -> Delivery:
    try:
        delivery = lock_document(db, Delivery, delivery_id, LABEL)
        require_status(delivery, {DeliveryStatus.DRAFT}, "edit", LABEL)
        changes = data.model_dump(exclude_unset=True, exclude={"lines"})
        for field, value in changes.items():
            setattr(delivery, field, value)
        _blank_address_to_null(delivery)
        if data.lines is not None:
            replace_lines(db, delivery, DeliveryLine, data.lines)
        _check_references(db, delivery)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, delivery)


def mark_delivery_todo(db: Session, delivery_id: int) -> Delivery:
    """DRAFT or WAITING -> READY if free stock covers every line, else WAITING."""
    try:
        delivery = lock_document(db, Delivery, delivery_id, LABEL)
        require_status(
            delivery, {DeliveryStatus.DRAFT, DeliveryStatus.WAITING}, "mark as to do", LABEL
        )
        _check_references(db, delivery)
        delivery.status = (
            DeliveryStatus.READY if _stock_covers(db, delivery) else DeliveryStatus.WAITING
        )
    except BaseException:
        db.rollback()
        raise
    return _commit(db, delivery)


def validate_delivery(db: Session, delivery_id: int, performed_by: int) -> Delivery:
    """READY -> DONE, delivering every line from the source location in one
    transaction. If any line is short, everything is rolled back and the delivery
    becomes WAITING instead (blueprint section 6); no stock is removed."""
    try:
        delivery = lock_document(db, Delivery, delivery_id, LABEL)
        require_status(delivery, {DeliveryStatus.READY}, "validate", LABEL)
        _check_references(db, delivery)
        try:
            for line in by_product(delivery.lines):
                inventory_service.deliver(
                    db,
                    product_id=line.product_id,
                    location_id=delivery.source_location_id,
                    quantity=line.quantity,
                    reference=delivery.reference,
                    source_type=SOURCE_TYPE,
                    source_id=delivery.id,
                    performed_by=performed_by,
                )
        except (InsufficientStockError, StockNotFoundError):
            db.rollback()  # undo the lines already delivered
            delivery = lock_document(db, Delivery, delivery_id, LABEL)
            if delivery.status is DeliveryStatus.READY:  # unless changed meanwhile
                delivery.status = DeliveryStatus.WAITING
        else:
            delivery.status = DeliveryStatus.DONE
    except BaseException:
        db.rollback()
        raise
    return _commit(db, delivery)


def cancel_delivery(db: Session, delivery_id: int) -> Delivery:
    """DRAFT/WAITING/READY -> CANCELED. No stock is touched."""
    try:
        delivery = lock_document(db, Delivery, delivery_id, LABEL)
        require_status(delivery, _OPEN, "cancel", LABEL)
        delivery.status = DeliveryStatus.CANCELED
    except BaseException:
        db.rollback()
        raise
    return _commit(db, delivery)


def promote_waiting_deliveries(db: Session, location_id: int) -> list[Delivery]:
    """WAITING -> READY for deliveries from `location_id` that free stock now
    covers. Runs inside the caller's transaction (e.g. a receipt validation) and
    does not commit. Deliveries are considered oldest first, but since nothing is
    reserved several may become READY for the same stock; validation decides."""
    waiting = db.scalars(
        select(Delivery)
        .where(
            Delivery.source_location_id == location_id,
            Delivery.status == DeliveryStatus.WAITING,
        )
        .order_by(Delivery.id)
        .with_for_update()
        .options(selectinload(Delivery.lines))
        .execution_options(populate_existing=True)
    )
    promoted = []
    for delivery in waiting:
        if _stock_covers(db, delivery):
            delivery.status = DeliveryStatus.READY
            promoted.append(delivery)
    return promoted
