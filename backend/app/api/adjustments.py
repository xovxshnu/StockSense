from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, get_current_user
from app.api.operation_errors import CONFLICT, INVALID_REFERENCE, NOT_FOUND, operation_errors
from app.api.responses import UNAUTHORIZED
from app.models.adjustment import AdjustmentStatus
from app.schemas.adjustment import AdjustmentCreate, AdjustmentRead, AdjustmentUpdate
from app.services import adjustment_service

# No /todo and no /cancel: the blueprint and the operations UI define only
# DRAFT -> DONE for adjustments.
router = APIRouter(
    prefix="/api/adjustments",
    tags=["adjustments"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[AdjustmentRead])
def list_adjustments(
    db: DbSession,
    search: Annotated[str | None, Query(description="Part of the reference")] = None,
    status: Annotated[AdjustmentStatus | None, Query(description="Only this status")] = None,
):
    """Newest first."""
    return adjustment_service.list_adjustments(db, search, status)


@router.post(
    "",
    response_model=AdjustmentRead,
    status_code=status.HTTP_201_CREATED,
    responses=INVALID_REFERENCE,
)
def create_adjustment(data: AdjustmentCreate, db: DbSession):
    """Creates a DRAFT with a backend-generated WH/ADJ reference. Lines carry only
    counted_quantity; system_quantity/difference are computed by the backend."""
    with operation_errors():
        return adjustment_service.create_adjustment(db, data)


@router.get("/{adjustment_id}", response_model=AdjustmentRead, responses=NOT_FOUND)
def get_adjustment(adjustment_id: int, db: DbSession):
    with operation_errors():
        return adjustment_service.get_adjustment(db, adjustment_id)


@router.put(
    "/{adjustment_id}",
    response_model=AdjustmentRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def update_adjustment(adjustment_id: int, data: AdjustmentUpdate, db: DbSession):
    """DRAFT only. Sent fields replace stored ones; `lines` replaces all lines."""
    with operation_errors():
        return adjustment_service.update_adjustment(db, adjustment_id, data)


@router.post(
    "/{adjustment_id}/validate",
    response_model=AdjustmentRead,
    responses=NOT_FOUND | CONFLICT | INVALID_REFERENCE,
)
def validate_adjustment(adjustment_id: int, db: DbSession, user: CurrentUser):
    """DRAFT -> DONE: each product's stock at the location becomes its counted
    quantity. The difference is computed from the current (locked) stock; one
    ADJUSTMENT stock movement per line whose difference is not zero. A count
    below the reserved quantity is a 409. All or nothing."""
    with operation_errors():
        return adjustment_service.validate_adjustment(db, adjustment_id, user.id)
