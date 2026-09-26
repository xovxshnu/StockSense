from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.schemas.warehouse import WarehouseCreate, WarehouseRead, WarehouseUpdate
from app.services import warehouse_service
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(
    prefix="/api/warehouses",
    tags=["warehouses"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[WarehouseRead])
def list_warehouses(
    db: DbSession,
    include_inactive: Annotated[bool, Query(description="Include archived warehouses")] = False,
):
    return warehouse_service.list_warehouses(db, include_inactive)


@router.post(
    "",
    response_model=WarehouseRead,
    status_code=status.HTTP_201_CREATED,
    responses=errors(409),
)
def create_warehouse(data: WarehouseCreate, db: DbSession):
    try:
        return warehouse_service.create_warehouse(db, data)
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.get("/{warehouse_id}", response_model=WarehouseRead, responses=errors(404))
def get_warehouse(warehouse_id: int, db: DbSession):
    try:
        return warehouse_service.get_warehouse(db, warehouse_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.put("/{warehouse_id}", response_model=WarehouseRead, responses=errors(404, 409))
def update_warehouse(warehouse_id: int, data: WarehouseUpdate, db: DbSession):
    """Partial update. Archive a warehouse with {"active": false}."""
    try:
        return warehouse_service.update_warehouse(db, warehouse_id, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
