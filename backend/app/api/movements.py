from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED
from app.models.stock_movement import MovementType
from app.schemas.inventory import MovementHistoryRead
from app.services import movement_service
from app.services.movement_service import DEFAULT_LIMIT, MAX_LIMIT

# Move History: read only. There is deliberately no POST/PUT/DELETE; movements
# are written only by the Inventory Engine.
router = APIRouter(
    prefix="/api/movements",
    tags=["movements"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[MovementHistoryRead])
def list_movements(
    db: DbSession,
    product_id: Annotated[int | None, Query(description="Only this product")] = None,
    movement_type: Annotated[MovementType | None, Query(description="IN, OUT, TRANSFER or ADJUSTMENT")] = None,
    reference: Annotated[
        str | None, Query(max_length=64, description="Case-insensitive part of the reference")
    ] = None,
    from_location_id: Annotated[int | None, Query(description="Source location")] = None,
    to_location_id: Annotated[int | None, Query(description="Destination location")] = None,
    location_id: Annotated[int | None, Query(description="Either source or destination")] = None,
    warehouse_id: Annotated[
        int | None, Query(description="Source or destination in this warehouse")
    ] = None,
    category_id: Annotated[int | None, Query(description="Only this product category")] = None,
    search: Annotated[
        str | None, Query(max_length=100, description="SKU, product name or reference")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size")] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
):
    """Newest first. ADJUSTMENT quantities are signed; the others are positive."""
    return movement_service.list_movements(
        db,
        product_id=product_id,
        movement_type=movement_type,
        reference=reference,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        location_id=location_id,
        warehouse_id=warehouse_id,
        category_id=category_id,
        search=search,
        limit=limit,
        offset=offset,
    )
