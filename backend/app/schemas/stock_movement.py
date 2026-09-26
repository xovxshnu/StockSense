from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.stock_movement import MovementType


class MovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    product_id: int
    movement_type: MovementType
    from_location_id: int | None
    to_location_id: int | None
    quantity: Decimal
    source_type: str
    source_id: int
    performed_by: int
    created_at: datetime
