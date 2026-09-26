from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.warehouse import Warehouse
from app.schemas.warehouse import WarehouseCreate, WarehouseUpdate
from app.services.errors import ConflictError, NotFoundError


def list_warehouses(db: Session, include_inactive: bool = False) -> list[Warehouse]:
    query = select(Warehouse).order_by(Warehouse.name, Warehouse.id)
    if not include_inactive:
        query = query.where(Warehouse.active.is_(True))
    return list(db.scalars(query))


def get_warehouse(db: Session, warehouse_id: int) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise NotFoundError("Warehouse not found")
    return warehouse


def _check_short_code_free(db: Session, short_code: str, exclude_id: int | None = None) -> None:
    query = select(Warehouse.id).where(Warehouse.short_code == short_code)
    if exclude_id is not None:
        query = query.where(Warehouse.id != exclude_id)
    if db.scalar(query) is not None:
        raise ConflictError("Warehouse short_code already exists")


def _commit(db: Session, short_code: str, exclude_id: int | None = None) -> None:
    """Commit, translating a lost race on the unique constraint into a ConflictError."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _check_short_code_free(db, short_code, exclude_id)
        raise


def create_warehouse(db: Session, data: WarehouseCreate) -> Warehouse:
    _check_short_code_free(db, data.short_code)
    warehouse = Warehouse(**data.model_dump())
    db.add(warehouse)
    _commit(db, data.short_code)
    db.refresh(warehouse)
    return warehouse


def update_warehouse(db: Session, warehouse_id: int, data: WarehouseUpdate) -> Warehouse:
    warehouse = get_warehouse(db, warehouse_id)
    changes = data.model_dump(exclude_unset=True)
    if "short_code" in changes:
        _check_short_code_free(db, changes["short_code"], exclude_id=warehouse.id)
    for field, value in changes.items():
        setattr(warehouse, field, value)
    _commit(db, warehouse.short_code, exclude_id=warehouse.id)
    db.refresh(warehouse)
    return warehouse
