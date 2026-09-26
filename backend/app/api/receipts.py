from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, get_current_user
from app.api.operation_errors import CONFLICT, INVALID_REFERENCE, NOT_FOUND, operation_errors
from app.api.responses import UNAUTHORIZED
from app.models.receipt import ReceiptStatus
from app.schemas.receipt import ReceiptCreate, ReceiptRead, ReceiptUpdate
from app.services import receipt_service

router = APIRouter(
    prefix="/api/receipts",
    tags=["receipts"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[ReceiptRead])
def list_receipts(
    db: DbSession,
    search: Annotated[str | None, Query(description="Part of the reference")] = None,
    status: Annotated[ReceiptStatus | None, Query(description="Only this status")] = None,
):
    """Newest first."""
    return receipt_service.list_receipts(db, search, status)


@router.post(
    "",
    response_model=ReceiptRead,
    status_code=status.HTTP_201_CREATED,
    responses=INVALID_REFERENCE,
)
def create_receipt(data: ReceiptCreate, db: DbSession):
    """Creates a DRAFT with a backend-generated WH/IN reference."""
    with operation_errors():
        return receipt_service.create_receipt(db, data)


@router.get("/{receipt_id}", response_model=ReceiptRead, responses=NOT_FOUND)
def get_receipt(receipt_id: int, db: DbSession):
    with operation_errors():
        return receipt_service.get_receipt(db, receipt_id)


@router.put(
    "/{receipt_id}",
    response_model=ReceiptRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def update_receipt(receipt_id: int, data: ReceiptUpdate, db: DbSession):
    """DRAFT only. Sent fields replace stored ones; `lines` replaces all lines."""
    with operation_errors():
        return receipt_service.update_receipt(db, receipt_id, data)


@router.post(
    "/{receipt_id}/todo",
    response_model=ReceiptRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def mark_receipt_todo(receipt_id: int, db: DbSession):
    """DRAFT -> READY."""
    with operation_errors():
        return receipt_service.mark_receipt_todo(db, receipt_id)


@router.post(
    "/{receipt_id}/validate",
    response_model=ReceiptRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def validate_receipt(receipt_id: int, db: DbSession, user: CurrentUser):
    """READY -> DONE: every line is received into the destination location (one
    IN stock movement per line, performed by the current user). All or nothing."""
    with operation_errors():
        return receipt_service.validate_receipt(db, receipt_id, user.id)


@router.post(
    "/{receipt_id}/cancel", response_model=ReceiptRead, responses=NOT_FOUND | CONFLICT
)
def cancel_receipt(receipt_id: int, db: DbSession):
    """DRAFT/READY -> CANCELED. Stock is not touched; a DONE receipt cannot be canceled."""
    with operation_errors():
        return receipt_service.cancel_receipt(db, receipt_id)
