"""Internal transfers: stock moved from one location to another.

    DRAFT --todo--> READY
    DRAFT --validate--> READY      (confirm only: no stock moves; see below)
    READY --validate--> DONE       (stock moved via inventory_service.transfer)
    DRAFT / READY --cancel--> CANCELED   (no stock is touched)

The operations UI offers only Validate and Cancel for transfers (no To Do), and
its contract leaves open what Validate does on a DRAFT. The blueprint's state
machine has no DRAFT -> DONE edge, so validating a DRAFT confirms it (READY) and
validating a READY transfer executes it.

Execution is all or nothing: every line goes through inventory_service.transfer
(one TRANSFER movement per line, source and destination locked by the engine) in
one transaction; if any line fails nothing is kept and the transfer stays READY.
A DONE transfer can be neither edited nor cancelled (reversal is not defined).
Source and destination may be in different warehouses: the UI has no warehouse
field for transfers and lists every location.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.location import Location
from app.models.transfer import Transfer, TransferLine, TransferStatus
from app.schemas.transfer import TransferCreate, TransferUpdate
from app.services import delivery_service, inventory_service
from app.services.errors import InvalidReferenceError, NotFoundError
from app.services.operation_common import (
    by_product,
    check_products,
    check_user,
    escape_like,
    lock_document,
    replace_lines,
    require_status,
)
from app.services.sequence_service import generate_reference

REFERENCE_PREFIX = "WH/INT"
SOURCE_TYPE = "transfer"  # StockMovement.source_type for movements a transfer creates
LABEL = "Transfer"


def list_transfers(
    db: Session, search: str | None = None, status: TransferStatus | None = None
) -> list[Transfer]:
    query = select(Transfer).options(selectinload(Transfer.lines)).order_by(Transfer.id.desc())
    if status is not None:
        query = query.where(Transfer.status == status)
    if search and search.strip():
        query = query.where(
            Transfer.reference.ilike(f"%{escape_like(search.strip())}%", escape="\\")
        )
    return list(db.scalars(query))


def get_transfer(db: Session, transfer_id: int) -> Transfer:
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise NotFoundError("Transfer not found")
    return transfer


def _check_location(db: Session, location_id: int, field: str) -> None:
    location = db.get(Location, location_id)
    if location is None:
        raise InvalidReferenceError(f"{field} does not exist")
    if not location.active:
        raise InvalidReferenceError(f"{field} is archived")


def _check_references(db: Session, transfer: Transfer) -> None:
    if transfer.from_location_id == transfer.to_location_id:
        raise InvalidReferenceError("from_location_id and to_location_id must differ")
    _check_location(db, transfer.from_location_id, "from_location_id")
    _check_location(db, transfer.to_location_id, "to_location_id")
    check_user(db, transfer.responsible_user_id, "responsible_user_id")
    check_products(db, (line.product_id for line in transfer.lines))


def _commit(db: Session, transfer: Transfer) -> Transfer:
    try:
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(transfer)  # server-side timestamps
    return transfer


def create_transfer(db: Session, data: TransferCreate) -> Transfer:
    transfer = Transfer(
        **data.model_dump(exclude={"lines"}),
        lines=[TransferLine(product_id=l.product_id, quantity=l.quantity) for l in data.lines],
    )
    try:
        _check_references(db, transfer)
        # Same transaction as the insert: a failed create does not use up a number.
        transfer.reference = generate_reference(db, REFERENCE_PREFIX)
        db.add(transfer)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, transfer)


def update_transfer(db: Session, transfer_id: int, data: TransferUpdate) -> Transfer:
    try:
        transfer = lock_document(db, Transfer, transfer_id, LABEL)
        require_status(transfer, {TransferStatus.DRAFT}, "edit", LABEL)
        for field, value in data.model_dump(exclude_unset=True, exclude={"lines"}).items():
            setattr(transfer, field, value)
        if data.lines is not None:
            replace_lines(db, transfer, TransferLine, data.lines)
        _check_references(db, transfer)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, transfer)


def _confirm(db: Session, transfer: Transfer) -> None:
    _check_references(db, transfer)
    transfer.status = TransferStatus.READY


def mark_transfer_todo(db: Session, transfer_id: int) -> Transfer:
    """DRAFT -> READY. References are re-checked; stock is not."""
    try:
        transfer = lock_document(db, Transfer, transfer_id, LABEL)
        require_status(transfer, {TransferStatus.DRAFT}, "mark as to do", LABEL)
        _confirm(db, transfer)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, transfer)


def validate_transfer(db: Session, transfer_id: int, performed_by: int) -> Transfer:
    """DRAFT -> READY (confirm), or READY -> DONE (move every line)."""
    try:
        transfer = lock_document(db, Transfer, transfer_id, LABEL)
        require_status(transfer, {TransferStatus.DRAFT, TransferStatus.READY}, "validate", LABEL)
        if transfer.status is TransferStatus.DRAFT:
            _confirm(db, transfer)
        else:
            _check_references(db, transfer)
            # Product order across lines + the engine's location order within a
            # line = one global (product_id, location_id) lock order.
            for line in by_product(transfer.lines):
                inventory_service.transfer(
                    db,
                    product_id=line.product_id,
                    from_location_id=transfer.from_location_id,
                    to_location_id=transfer.to_location_id,
                    quantity=line.quantity,
                    reference=transfer.reference,
                    source_type=SOURCE_TYPE,
                    source_id=transfer.id,
                    performed_by=performed_by,
                )
            transfer.status = TransferStatus.DONE
            # Stock arrived at the destination: it may cover waiting deliveries.
            delivery_service.promote_waiting_deliveries(db, transfer.to_location_id)
    except BaseException:
        db.rollback()
        raise
    return _commit(db, transfer)


def cancel_transfer(db: Session, transfer_id: int) -> Transfer:
    """DRAFT/READY -> CANCELED. No stock is touched."""
    try:
        transfer = lock_document(db, Transfer, transfer_id, LABEL)
        require_status(transfer, {TransferStatus.DRAFT, TransferStatus.READY}, "cancel", LABEL)
        transfer.status = TransferStatus.CANCELED
    except BaseException:
        db.rollback()
        raise
    return _commit(db, transfer)
