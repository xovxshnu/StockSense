"""Read-side shapes for the stock and move-history pages (flat rows, display
fields included so the UI needs no extra lookups)."""

import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field

from app.schemas.stock import StockRead
from app.schemas.stock_movement import MovementRead


class StockStatus(str, enum.Enum):
    """Compared against Product.reorder_level (the single low-stock threshold):

    OUT_OF_STOCK  quantity on hand <= 0
    LOW_STOCK     0 < quantity on hand <= reorder_level
    IN_STOCK      quantity on hand > reorder_level
    """

    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class StockLevelRead(StockRead):
    """One Stock row (product at one location). `status` is for this location."""

    product_sku: str
    product_name: str
    uom: str
    reorder_level: int
    category_id: int
    category_name: str
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    location_code: str
    location_name: str
    status: StockStatus
    updated_at: datetime


class ProductStockRead(BaseModel):
    """A product's stock at every location, plus its company-wide totals. The
    totals and `status` cover active locations only (the same definition the
    dashboard counts with)."""

    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_sku: str
    product_name: str
    uom: str
    reorder_level: int
    category_id: int
    category_name: str
    active: bool
    quantity: Decimal
    reserved_quantity: Decimal
    status: StockStatus
    locations: list[StockLevelRead]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def free_to_use(self) -> Decimal:
        return self.quantity - self.reserved_quantity


class MovementHistoryRead(MovementRead):
    """One ledger row with display names (Move History)."""

    product_sku: str
    product_name: str
    from_location_name: str | None
    to_location_name: str | None
    performed_by_login: str
