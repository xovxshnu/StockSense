from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

_MAX_INT = 2**31 - 1  # PostgreSQL INTEGER

ProductId = Annotated[int, Field(ge=1, le=_MAX_INT)]
ReorderQuantity = Annotated[int, Field(ge=1, le=_MAX_INT)]


class ReorderRuleCreate(BaseModel):
    # Unknown fields (stock, location, warehouse, ...) are rejected.
    model_config = ConfigDict(extra="forbid")

    product_id: ProductId
    reorder_quantity: ReorderQuantity


class ReorderRuleUpdate(BaseModel):
    """Partial update of the reorder quantity only. `product_id` is absent and,
    because extra fields are forbidden, sending it is a 422."""

    model_config = ConfigDict(extra="forbid")

    reorder_quantity: ReorderQuantity | None = None

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "ReorderRuleUpdate":
        nulls = [f for f in self.model_fields_set if getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class ReorderRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    reorder_quantity: int
    created_at: datetime
