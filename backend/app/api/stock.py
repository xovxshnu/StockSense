from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.schemas.inventory import ProductStockRead, StockLevelRead
from app.services import stock_service
from app.services.errors import NotFoundError

# Read only. Stock changes only through operation documents (Inventory Engine);
# a stock-page correction is an adjustment (POST /api/adjustments).
router = APIRouter(
    prefix="/api/stock",
    tags=["stock"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[StockLevelRead])
def list_stock(
    db: DbSession,
    warehouse_id: Annotated[int | None, Query(description="Only this warehouse")] = None,
    location_id: Annotated[int | None, Query(description="Only this location")] = None,
    category_id: Annotated[int | None, Query(description="Only this product category")] = None,
    search: Annotated[
        str | None, Query(max_length=100, description="Case-insensitive match on SKU or name")
    ] = None,
    low_stock: Annotated[bool, Query(description="Only rows with status LOW_STOCK")] = False,
    out_of_stock: Annotated[
        bool, Query(description="Only rows with status OUT_OF_STOCK (with low_stock: either)")
    ] = False,
    include_inactive: Annotated[
        bool, Query(description="Include archived products, locations and warehouses")
    ] = False,
):
    """One row per product and location, ordered by SKU, warehouse, location.
    `status` compares that row's quantity with the product's reorder_level."""
    return stock_service.list_stock(
        db,
        warehouse_id=warehouse_id,
        location_id=location_id,
        category_id=category_id,
        search=search,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        include_inactive=include_inactive,
    )


@router.get("/{product_id}", response_model=ProductStockRead, responses=errors(404))
def get_product_stock(
    product_id: int,
    db: DbSession,
    include_inactive: Annotated[
        bool, Query(description="Also list archived locations and warehouses")
    ] = False,
):
    """The product's stock at each location, with its totals and status over all
    active locations (the definition the dashboard uses)."""
    try:
        return stock_service.get_product_stock(db, product_id, include_inactive)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
