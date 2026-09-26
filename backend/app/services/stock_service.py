"""Read-only stock queries (the Stock page). Stock is authoritative: nothing here
reads StockMovement, and nothing here writes anything.

Status is computed in SQL from the quantity on hand and Product.reorder_level
(the single low-stock threshold; ReorderRule only carries the replenishment
quantity):

    OUT_OF_STOCK  on hand <= 0
    LOW_STOCK     0 < on hand <= reorder_level
    IN_STOCK      otherwise

For a stock row the "on hand" is that row's quantity (status at that location).
For a product (detail totals, dashboard) it is the sum over active locations.
"""

from sqlalchemy import ColumnElement, Select, and_, case, func, select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.location import Location
from app.models.product import Product
from app.models.stock import Stock
from app.models.warehouse import Warehouse
from app.schemas.inventory import ProductStockRead, StockLevelRead, StockStatus
from app.services.errors import NotFoundError
from app.services.operation_common import escape_like


def status_expression(on_hand, reorder_level) -> ColumnElement[str]:
    return case(
        (on_hand <= 0, StockStatus.OUT_OF_STOCK.value),
        (on_hand <= reorder_level, StockStatus.LOW_STOCK.value),
        else_=StockStatus.IN_STOCK.value,
    )


def active_location_clause() -> ColumnElement[bool]:
    """A location whose stock is usable: it and its warehouse are active."""
    return and_(Location.active.is_(True), Warehouse.active.is_(True))


def _stock_rows() -> Select:
    return (
        select(
            Stock.id,
            Stock.product_id,
            Product.sku.label("product_sku"),
            Product.name.label("product_name"),
            Product.uom,
            Product.reorder_level,
            Product.category_id,
            Category.name.label("category_name"),
            Location.warehouse_id,
            Warehouse.short_code.label("warehouse_code"),
            Warehouse.name.label("warehouse_name"),
            Stock.location_id,
            Location.short_code.label("location_code"),
            Location.name.label("location_name"),
            Stock.quantity,
            Stock.reserved_quantity,
            status_expression(Stock.quantity, Product.reorder_level).label("status"),
            Stock.updated_at,
        )
        .join(Product, Product.id == Stock.product_id)
        .join(Category, Category.id == Product.category_id)
        .join(Location, Location.id == Stock.location_id)
        .join(Warehouse, Warehouse.id == Location.warehouse_id)
        .order_by(Product.sku, Warehouse.short_code, Location.short_code, Stock.id)
    )


def list_stock(
    db: Session,
    *,
    warehouse_id: int | None = None,
    location_id: int | None = None,
    category_id: int | None = None,
    search: str | None = None,
    low_stock: bool = False,
    out_of_stock: bool = False,
    include_inactive: bool = False,
) -> list[StockLevelRead]:
    """Stock rows, one per product and location. `low_stock` / `out_of_stock`
    keep rows with that status (both: either status). Archived products,
    locations and warehouses are hidden unless `include_inactive`."""
    query = _stock_rows()
    if not include_inactive:
        query = query.where(Product.active.is_(True), active_location_clause())
    if warehouse_id is not None:
        query = query.where(Location.warehouse_id == warehouse_id)
    if location_id is not None:
        query = query.where(Stock.location_id == location_id)
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.where(
            Product.sku.ilike(pattern, escape="\\") | Product.name.ilike(pattern, escape="\\")
        )
    wanted = [
        status.value
        for status, on in ((StockStatus.LOW_STOCK, low_stock), (StockStatus.OUT_OF_STOCK, out_of_stock))
        if on
    ]
    if wanted:
        query = query.where(status_expression(Stock.quantity, Product.reorder_level).in_(wanted))
    return [StockLevelRead.model_validate(row._mapping) for row in db.execute(query)]


def product_totals(
    *, warehouse_id: int | None = None, location_id: int | None = None
):
    """Subquery: per product, SUM of quantity / reserved over active locations
    (optionally one warehouse or location). Aggregated by the database."""
    query = (
        select(
            Stock.product_id,
            func.sum(Stock.quantity).label("quantity"),
            func.sum(Stock.reserved_quantity).label("reserved_quantity"),
        )
        .join(Location, Location.id == Stock.location_id)
        .join(Warehouse, Warehouse.id == Location.warehouse_id)
        .where(active_location_clause())
        .group_by(Stock.product_id)
    )
    if warehouse_id is not None:
        query = query.where(Location.warehouse_id == warehouse_id)
    if location_id is not None:
        query = query.where(Stock.location_id == location_id)
    return query.subquery("product_totals")


def get_product_stock(
    db: Session, product_id: int, include_inactive: bool = False
) -> ProductStockRead:
    """Every location's stock for one product (archived products included: the
    product is asked for by id) and its totals over active locations."""
    totals = product_totals()
    on_hand = func.coalesce(totals.c.quantity, 0)
    row = db.execute(
        select(
            Product.id.label("product_id"),
            Product.sku.label("product_sku"),
            Product.name.label("product_name"),
            Product.uom,
            Product.reorder_level,
            Product.category_id,
            Category.name.label("category_name"),
            Product.active,
            on_hand.label("quantity"),
            func.coalesce(totals.c.reserved_quantity, 0).label("reserved_quantity"),
            status_expression(on_hand, Product.reorder_level).label("status"),
        )
        .join(Category, Category.id == Product.category_id)
        .outerjoin(totals, totals.c.product_id == Product.id)
        .where(Product.id == product_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("Product not found")

    rows = _stock_rows().where(Stock.product_id == product_id)
    if not include_inactive:
        rows = rows.where(active_location_clause())
    locations = [StockLevelRead.model_validate(r._mapping) for r in db.execute(rows)]
    return ProductStockRead.model_validate({**row._mapping, "locations": locations})
