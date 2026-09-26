from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED
from app.schemas.dashboard import DashboardRead
from app.services import dashboard_service

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=DashboardRead)
def get_dashboard(
    db: DbSession,
    warehouse_id: Annotated[int | None, Query(description="Scope to this warehouse")] = None,
    location_id: Annotated[int | None, Query(description="Scope to this location")] = None,
    category_id: Annotated[int | None, Query(description="Scope to this product category")] = None,
):
    """KPIs from current database state (Stock and the operation documents)."""
    return dashboard_service.get_dashboard(
        db, warehouse_id=warehouse_id, location_id=location_id, category_id=category_id
    )
