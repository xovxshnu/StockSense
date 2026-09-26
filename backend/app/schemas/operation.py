"""Shapes shared by operation documents (receipts, deliveries, ...)."""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_MAX_INT = 2**31 - 1  # PostgreSQL INTEGER

RecordId = Annotated[int, Field(ge=1, le=_MAX_INT)]
# Matches Stock/StockMovement NUMERIC(14, 3); an operation line is always positive.
LineQuantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]


class OperationLineIn(BaseModel):
    """A line as the operations UI sends it: product and quantity only."""

    model_config = ConfigDict(extra="forbid")

    product_id: RecordId
    quantity: LineQuantity


def _unique_products(lines: list[OperationLineIn]) -> list[OperationLineIn]:
    seen: set[int] = set()
    for line in lines:
        if line.product_id in seen:
            raise ValueError(f"product {line.product_id} appears on more than one line")
        seen.add(line.product_id)
    return lines


# At least one line, one line per product (the UI refuses duplicates as well).
OperationLines = Annotated[
    list[OperationLineIn], Field(min_length=1), AfterValidator(_unique_products)
]


class ProductSummary(BaseModel):
    """Display fields for a line's product (the line's product_id is the authority)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    uom: str


class OperationLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: Decimal
    product: ProductSummary
