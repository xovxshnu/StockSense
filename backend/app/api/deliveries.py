from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, get_current_user
from app.api.operation_errors import CONFLICT, INVALID_REFERENCE, NOT_FOUND, operation_errors
from app.api.responses import UNAUTHORIZED
from app.models.delivery import DeliveryStatus
from app.schemas.delivery import DeliveryCreate, DeliveryRead, DeliveryUpdate
from app.services import delivery_service

router = APIRouter(
    prefix="/api/deliveries",
    tags=["deliveries"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[DeliveryRead])
def list_deliveries(
    db: DbSession,
    search: Annotated[str | None, Query(description="Part of the reference")] = None,
    status: Annotated[DeliveryStatus | None, Query(description="Only this status")] = None,
):
    """Newest first."""
    return delivery_service.list_deliveries(db, search, status)


@router.post(
    "",
    response_model=DeliveryRead,
    status_code=status.HTTP_201_CREATED,
    responses=INVALID_REFERENCE,
)
def create_delivery(data: DeliveryCreate, db: DbSession):
    """Creates a DRAFT with a backend-generated WH/OUT reference."""
    with operation_errors():
        return delivery_service.create_delivery(db, data)


@router.get("/{delivery_id}", response_model=DeliveryRead, responses=NOT_FOUND)
def get_delivery(delivery_id: int, db: DbSession):
    with operation_errors():
        return delivery_service.get_delivery(db, delivery_id)


@router.put(
    "/{delivery_id}",
    response_model=DeliveryRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def update_delivery(delivery_id: int, data: DeliveryUpdate, db: DbSession):
    """DRAFT only. Sent fields replace stored ones; `lines` replaces all lines."""
    with operation_errors():
        return delivery_service.update_delivery(db, delivery_id, data)


@router.post(
    "/{delivery_id}/todo",
    response_model=DeliveryRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def mark_delivery_todo(delivery_id: int, db: DbSession):
    """DRAFT or WAITING -> READY when the free stock at the source covers every
    line, otherwise WAITING."""
    with operation_errors():
        return delivery_service.mark_delivery_todo(db, delivery_id)


@router.post(
    "/{delivery_id}/validate",
    response_model=DeliveryRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def validate_delivery(delivery_id: int, db: DbSession, user: CurrentUser):
    """READY -> DONE: every line leaves the source location (one OUT stock
    movement per line, performed by the current user). If the free stock no
    longer covers every line, nothing is removed and the delivery is returned
    with status WAITING."""
    with operation_errors():
        return delivery_service.validate_delivery(db, delivery_id, user.id)


@router.post(
    "/{delivery_id}/cancel", response_model=DeliveryRead, responses=NOT_FOUND | CONFLICT
)
def cancel_delivery(delivery_id: int, db: DbSession):
    """DRAFT/WAITING/READY -> CANCELED. Stock is not touched; a DONE delivery
    cannot be canceled."""
    with operation_errors():
        return delivery_service.cancel_delivery(db, delivery_id)
