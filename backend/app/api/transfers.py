from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, get_current_user
from app.api.operation_errors import CONFLICT, INVALID_REFERENCE, NOT_FOUND, operation_errors
from app.api.responses import UNAUTHORIZED
from app.models.transfer import TransferStatus
from app.schemas.transfer import TransferCreate, TransferRead, TransferUpdate
from app.services import transfer_service

router = APIRouter(
    prefix="/api/transfers",
    tags=["transfers"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[TransferRead])
def list_transfers(
    db: DbSession,
    search: Annotated[str | None, Query(description="Part of the reference")] = None,
    status: Annotated[TransferStatus | None, Query(description="Only this status")] = None,
):
    """Newest first."""
    return transfer_service.list_transfers(db, search, status)


@router.post(
    "",
    response_model=TransferRead,
    status_code=status.HTTP_201_CREATED,
    responses=INVALID_REFERENCE,
)
def create_transfer(data: TransferCreate, db: DbSession):
    """Creates a DRAFT with a backend-generated WH/INT reference."""
    with operation_errors():
        return transfer_service.create_transfer(db, data)


@router.get("/{transfer_id}", response_model=TransferRead, responses=NOT_FOUND)
def get_transfer(transfer_id: int, db: DbSession):
    with operation_errors():
        return transfer_service.get_transfer(db, transfer_id)


@router.put(
    "/{transfer_id}",
    response_model=TransferRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def update_transfer(transfer_id: int, data: TransferUpdate, db: DbSession):
    """DRAFT only. Sent fields replace stored ones; `lines` replaces all lines."""
    with operation_errors():
        return transfer_service.update_transfer(db, transfer_id, data)


@router.post(
    "/{transfer_id}/todo",
    response_model=TransferRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def mark_transfer_todo(transfer_id: int, db: DbSession):
    """DRAFT -> READY."""
    with operation_errors():
        return transfer_service.mark_transfer_todo(db, transfer_id)


@router.post(
    "/{transfer_id}/validate",
    response_model=TransferRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def validate_transfer(transfer_id: int, db: DbSession, user: CurrentUser):
    """On a DRAFT: confirms it (-> READY), no stock moves. On a READY transfer:
    moves every line from the source to the destination (one TRANSFER stock
    movement per line, performed by the current user) and -> DONE. All or
    nothing; insufficient free stock at the source is a 409."""
    with operation_errors():
        return transfer_service.validate_transfer(db, transfer_id, user.id)


@router.post(
    "/{transfer_id}/cancel", response_model=TransferRead, responses=NOT_FOUND | CONFLICT
)
def cancel_transfer(transfer_id: int, db: DbSession):
    """DRAFT/READY -> CANCELED. Stock is not touched; a DONE transfer cannot be canceled."""
    with operation_errors():
        return transfer_service.cancel_transfer(db, transfer_id)
