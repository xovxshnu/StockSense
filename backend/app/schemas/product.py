from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

_MAX_INT = 2**31 - 1  # PostgreSQL INTEGER

ProductName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
# SKUs are trimmed and uppercased so "sku001" and " SKU001 " are the same SKU.
Sku = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=64),
]
Uom = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
CategoryId = Annotated[int, Field(ge=1, le=_MAX_INT)]
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
ReorderLevel = Annotated[int, Field(ge=0, le=_MAX_INT)]


class ProductCreate(BaseModel):
    # Unknown fields (e.g. "quantity") are rejected, not silently ignored.
    model_config = ConfigDict(extra="forbid")

    name: ProductName
    sku: Sku
    category_id: CategoryId
    uom: Uom = "Unit"
    unit_cost: UnitCost = Decimal("0")
    reorder_level: ReorderLevel = 0
    active: bool = True


class ProductUpdate(BaseModel):
    """Partial update: only the fields that are sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: ProductName | None = None
    sku: Sku | None = None
    category_id: CategoryId | None = None
    uom: Uom | None = None
    unit_cost: UnitCost | None = None
    reorder_level: ReorderLevel | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "ProductUpdate":
        nulls = [f for f in self.model_fields_set if getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sku: str
    category_id: int
    uom: str
    unit_cost: Decimal
    reorder_level: int
    active: bool
    created_at: datetime
