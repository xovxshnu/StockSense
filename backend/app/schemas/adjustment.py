from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models.adjustment import AdjustmentStatus
from app.schemas.operation import ProductSummary, RecordId, _unique_products

# A physical count: zero is meaningful ("none left"), negative is not.
CountedQuantity = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
# Free text (a textarea in the UI). Blank reasons are stored as null (see the service).
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class AdjustmentLineIn(BaseModel):
    """What the UI sends: product and counted quantity. system_quantity and
    difference are backend-owned; sending them is a 422."""

    model_config = ConfigDict(extra="forbid")

    product_id: RecordId
    counted_quantity: CountedQuantity


AdjustmentLines = Annotated[
    list[AdjustmentLineIn], Field(min_length=1), AfterValidator(_unique_products)
]


class AdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: RecordId
    reason: Reason | None = None
    responsible_user_id: RecordId | None = None
    lines: AdjustmentLines


class AdjustmentUpdate(BaseModel):
    """Only while DRAFT. Fields that are sent replace the stored ones; `lines`, when
    sent, replaces all lines. reason / responsible_user_id may be null."""

    model_config = ConfigDict(extra="forbid")

    location_id: RecordId | None = None
    reason: Reason | None = None
    responsible_user_id: RecordId | None = None
    lines: AdjustmentLines | None = None

    @model_validator(mode="after")
    def no_null_required_fields(self) -> "AdjustmentUpdate":
        nulls = [
            f for f in ("location_id", "lines")
            if f in self.model_fields_set and getattr(self, f) is None
        ]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(nulls)}")
        return self


class AdjustmentLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product: ProductSummary
    counted_quantity: Decimal
    # DRAFT: stock when the draft was last saved (display only).
    # DONE: the stock the adjustment was actually applied against.
    system_quantity: Decimal
    difference: Decimal


class AdjustmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    status: AdjustmentStatus
    location_id: int
    reason: str | None
    responsible_user_id: int | None
    created_at: datetime
    updated_at: datetime
    lines: list[AdjustmentLineRead]
