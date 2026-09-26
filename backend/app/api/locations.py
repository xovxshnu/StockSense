from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate
from app.services import location_service
from app.services.errors import ConflictError, InvalidReferenceError, NotFoundError

router = APIRouter(
    prefix="/api/locations",
    tags=["locations"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[LocationRead])
def list_locations(
    db: DbSession,
    warehouse_id: Annotated[int | None, Query(description="Only this warehouse's locations")] = None,
    include_inactive: Annotated[bool, Query(description="Include archived locations")] = False,
):
    return location_service.list_locations(db, warehouse_id, include_inactive)


@router.post(
    "",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
    responses=errors(409, invalid_reference=True),
)
def create_location(data: LocationCreate, db: DbSession):
    try:
        return location_service.create_location(db, data)
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.get("/{location_id}", response_model=LocationRead, responses=errors(404))
def get_location(location_id: int, db: DbSession):
    try:
        return location_service.get_location(db, location_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.put("/{location_id}", response_model=LocationRead, responses=errors(404, 409))
def update_location(location_id: int, data: LocationUpdate, db: DbSession):
    """Partial update of name/short_code/active. warehouse_id cannot be changed.
    Archive a location with {"active": false}."""
    try:
        return location_service.update_location(db, location_id, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
