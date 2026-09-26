"""Read-only Move History: a view over StockMovement (the ledger), newest first.
There is no second movement store and nothing here writes anything."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from app.models.location import Location
from app.models.product import Product
from app.models.stock_movement import MovementType, StockMovement
from app.models.user import User
from app.schemas.inventory import MovementHistoryRead
from app.services.operation_common import escape_like

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


def list_movements(
    db: Session,
    *,
    product_id: int | None = None,
    movement_type: MovementType | None = None,
    reference: str | None = None,
    from_location_id: int | None = None,
    to_location_id: int | None = None,
    location_id: int | None = None,
    warehouse_id: int | None = None,
    category_id: int | None = None,
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[MovementHistoryRead]:
    """`location_id` / `warehouse_id` match either side of a movement; `reference`
    is a case-insensitive substring; `search` matches SKU, product name or
    reference. Filtering, ordering and paging happen in the database."""
    source = aliased(Location, name="source_location")
    destination = aliased(Location, name="destination_location")
    query = (
        select(
            StockMovement.id,
            StockMovement.reference,
            StockMovement.product_id,
            Product.sku.label("product_sku"),
            Product.name.label("product_name"),
            StockMovement.movement_type,
            StockMovement.from_location_id,
            source.name.label("from_location_name"),
            StockMovement.to_location_id,
            destination.name.label("to_location_name"),
            StockMovement.quantity,
            StockMovement.source_type,
            StockMovement.source_id,
            StockMovement.performed_by,
            User.login_id.label("performed_by_login"),
            StockMovement.created_at,
        )
        .join(Product, Product.id == StockMovement.product_id)
        .join(User, User.id == StockMovement.performed_by)
        .outerjoin(source, source.id == StockMovement.from_location_id)
        .outerjoin(destination, destination.id == StockMovement.to_location_id)
        # created_at is the transaction time, so movements of one document tie;
        # id breaks the tie in insertion order.
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if product_id is not None:
        query = query.where(StockMovement.product_id == product_id)
    if movement_type is not None:
        query = query.where(StockMovement.movement_type == movement_type)
    if reference and reference.strip():
        query = query.where(
            StockMovement.reference.ilike(f"%{escape_like(reference.strip())}%", escape="\\")
        )
    if from_location_id is not None:
        query = query.where(StockMovement.from_location_id == from_location_id)
    if to_location_id is not None:
        query = query.where(StockMovement.to_location_id == to_location_id)
    if location_id is not None:
        query = query.where(
            or_(
                StockMovement.from_location_id == location_id,
                StockMovement.to_location_id == location_id,
            )
        )
    if warehouse_id is not None:
        query = query.where(
            or_(source.warehouse_id == warehouse_id, destination.warehouse_id == warehouse_id)
        )
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.where(
            Product.sku.ilike(pattern, escape="\\")
            | Product.name.ilike(pattern, escape="\\")
            | StockMovement.reference.ilike(pattern, escape="\\")
        )
    return [MovementHistoryRead.model_validate(row._mapping) for row in db.execute(query)]
