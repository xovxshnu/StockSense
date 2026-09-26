from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.location import Location
from app.models.warehouse import Warehouse
from app.schemas.location import LocationCreate, LocationUpdate
from app.services.errors import ConflictError, InvalidReferenceError, NotFoundError


def list_locations(
    db: Session, warehouse_id: int | None = None, include_inactive: bool = False
) -> list[Location]:
    query = select(Location).order_by(Location.warehouse_id, Location.name, Location.id)
    if warehouse_id is not None:
        query = query.where(Location.warehouse_id == warehouse_id)
    if not include_inactive:
        query = query.where(Location.active.is_(True))
    return list(db.scalars(query))


def get_location(db: Session, location_id: int) -> Location:
    location = db.get(Location, location_id)
    if location is None:
        raise NotFoundError("Location not found")
    return location


def _check_warehouse_exists(db: Session, warehouse_id: int) -> None:
    if db.get(Warehouse, warehouse_id) is None:
        raise InvalidReferenceError("warehouse_id does not exist")


def _check_short_code_free(
    db: Session, warehouse_id: int, short_code: str, exclude_id: int | None = None
) -> None:
    query = select(Location.id).where(
        Location.warehouse_id == warehouse_id, Location.short_code == short_code
    )
    if exclude_id is not None:
        query = query.where(Location.id != exclude_id)
    if db.scalar(query) is not None:
        raise ConflictError("Location short_code already exists in this warehouse")


def _commit(db: Session, warehouse_id: int, short_code: str, exclude_id: int | None = None) -> None:
    """Commit, translating a lost race on the DB constraints into domain errors."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _check_warehouse_exists(db, warehouse_id)
        _check_short_code_free(db, warehouse_id, short_code, exclude_id)
        raise


def create_location(db: Session, data: LocationCreate) -> Location:
    _check_warehouse_exists(db, data.warehouse_id)
    _check_short_code_free(db, data.warehouse_id, data.short_code)
    location = Location(**data.model_dump())
    db.add(location)
    _commit(db, data.warehouse_id, data.short_code)
    db.refresh(location)
    return location


def update_location(db: Session, location_id: int, data: LocationUpdate) -> Location:
    location = get_location(db, location_id)
    changes = data.model_dump(exclude_unset=True)
    if "short_code" in changes:
        _check_short_code_free(
            db, location.warehouse_id, changes["short_code"], exclude_id=location.id
        )
    for field, value in changes.items():
        setattr(location, field, value)
    _commit(db, location.warehouse_id, location.short_code, exclude_id=location.id)
    db.refresh(location)
    return location
