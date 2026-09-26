from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

WarehouseName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
# Trimmed and uppercased: "chn", " CHN " and "Chn" are all "CHN".
ShortCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20),
]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WarehouseName
    short_code: ShortCode
    address: str | None = None
    active: bool = True

    _clean_address = field_validator("address")(_blank_to_none)


class WarehouseUpdate(BaseModel):
    """Partial update: only the fields that are sent are changed.
    `address` may be null (clears it); the other fields may not."""

    model_config = ConfigDict(extra="forbid")

    name: WarehouseName | None = None
    short_code: ShortCode | None = None
    address: str | None = None
    active: bool | None = None

    _clean_address = field_validator("address")(_blank_to_none)

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "WarehouseUpdate":
        nulls = [
            f for f in self.model_fields_set if f != "address" and getattr(self, f) is None
        ]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_code: str
    address: str | None
    active: bool
