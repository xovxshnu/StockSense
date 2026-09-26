"""Receipts: incoming goods. DRAFT -> READY -> DONE, and DRAFT/READY -> CANCELED.

Only `validate_receipt` changes stock, via inventory_service.receive (one IN
movement per line), all in one transaction: if any line fails, nothing is kept
and the receipt stays READY. Cancelling never touches stock, and a DONE receipt
can be neither edited nor cancelled (reversal is not defined by the blueprint).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.contact import ContactType
from app.models.receipt import Receipt, ReceiptLine, ReceiptStatus
from app.schemas.receipt import ReceiptCreate, ReceiptUpdate
from app.services import delivery_service, inventory_service
from app.services.errors import NotFoundError
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

REFERENCE_PREFIX = "WH/IN"
SOURCE_TYPE = "receipt"  # StockMovement.source_type for movements a receipt creates
LABEL = "Receipt"


def list_receipts(
    db: Session, search: str | None = None, status: ReceiptStatus | None = None
) -> list[Receipt]:
    query = select(Receipt).options(selectinload(Receipt.lines)).order_by(Receipt.id.desc())
    if status is not None:
        query = query.where(Receipt.status == status)
    if search and search.strip():
        query = query.where(
            Receipt.reference.ilike(f"%{escape_like(search.strip())}%", escape="\\")
        )
    return list(db.scalars(query))


def get_receipt(db: Session, receipt_id: int) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise NotFoundError("Receipt not found")
    return receipt


def _check_references(db: Session, receipt: Receipt) -> None:
    check_contact(db, receipt.supplier_id, ContactType.SUPPLIER, "supplier_id")
    check_warehouse_location(
        db, receipt.warehouse_id, receipt.destination_location_id, "destination_location_id"
    )
    check_user(db, receipt.responsible_user_id, "responsible_user_id")
    check_products(db, (line.product_id for line in receipt.lines))


def _commit(db: Session, receipt: Receipt) -> Receipt:
    try:
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(receipt)  # server-side timestamps
    return receipt


def create_receipt(db: Session, data: ReceiptCreate) -> Receipt:
    fields = data.model_dump(exclude={"lines"})
    receipt = Receipt(
        **fields,
        lines=[ReceiptLine(product_id=l.product_id, quantity=l.quantity) for l in data.lines],
    )
    try:
        _check_references(db, receipt)
        # Same transaction as the insert: a failed create does not use up a number.
        receipt.reference = generate_reference(db, REFERENCE_PREFIX)
        db.add(receipt)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, receipt)


def update_receipt(db: Session, receipt_id: int, data: ReceiptUpdate) -> Receipt:
    try:
        receipt = lock_document(db, Receipt, receipt_id, LABEL)
        require_status(receipt, {ReceiptStatus.DRAFT}, "edit", LABEL)
        changes = data.model_dump(exclude_unset=True, exclude={"lines"})
        for field, value in changes.items():
            setattr(receipt, field, value)
        if data.lines is not None:
            replace_lines(db, receipt, ReceiptLine, data.lines)
        _check_references(db, receipt)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, receipt)


def mark_receipt_todo(db: Session, receipt_id: int) -> Receipt:
    """DRAFT -> READY. References are re-checked (products may have been archived)."""
    try:
        receipt = lock_document(db, Receipt, receipt_id, LABEL)
        require_status(receipt, {ReceiptStatus.DRAFT}, "mark as to do", LABEL)
        _check_references(db, receipt)
        receipt.status = ReceiptStatus.READY
    except BaseException:
        db.rollback()
        raise
    return _commit(db, receipt)


def validate_receipt(db: Session, receipt_id: int, performed_by: int) -> Receipt:
    """READY -> DONE: receive every line into the destination location."""
    try:
        receipt = lock_document(db, Receipt, receipt_id, LABEL)
        require_status(receipt, {ReceiptStatus.READY}, "validate", LABEL)
        _check_references(db, receipt)
        for line in by_product(receipt.lines):
            inventory_service.receive(
                db,
                product_id=line.product_id,
                location_id=receipt.destination_location_id,
                quantity=line.quantity,
                reference=receipt.reference,
                source_type=SOURCE_TYPE,
                source_id=receipt.id,
                performed_by=performed_by,
            )
        receipt.status = ReceiptStatus.DONE
        # New stock may cover deliveries that were waiting on this location.
        delivery_service.promote_waiting_deliveries(db, receipt.destination_location_id)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, receipt)


def cancel_receipt(db: Session, receipt_id: int) -> Receipt:
    """DRAFT/READY -> CANCELED. No stock is touched."""
    try:
        receipt = lock_document(db, Receipt, receipt_id, LABEL)
        require_status(receipt, {ReceiptStatus.DRAFT, ReceiptStatus.READY}, "cancel", LABEL)
        receipt.status = ReceiptStatus.CANCELED
    except BaseException:
        db.rollback()
        raise
    return _commit(db, receipt)
