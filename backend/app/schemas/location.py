from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.warehouse import ShortCode

_MAX_INT = 2**31 - 1  # PostgreSQL INTEGER

LocationName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
WarehouseId = Annotated[int, Field(ge=1, le=_MAX_INT)]


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: WarehouseId
    name: LocationName
    short_code: ShortCode
    active: bool = True


class LocationUpdate(BaseModel):
    """Partial update. `warehouse_id` is deliberately absent and, because extra
    fields are forbidden, sending it is a 422: a location never changes warehouse.
    Future Stock rows hang off Location.id, so re-parenting would silently move
    stock between warehouses. Create a new location instead."""

    model_config = ConfigDict(extra="forbid")

    name: LocationName | None = None
    short_code: ShortCode | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "LocationUpdate":
        nulls = [f for f in self.model_fields_set if getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    name: str
    short_code: str
    active: bool
