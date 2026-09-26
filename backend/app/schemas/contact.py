from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.models.contact import ContactType

ContactName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ContactName
    type: ContactType
    address: str | None = None

    _clean_address = field_validator("address")(_blank_to_none)


class ContactUpdate(BaseModel):
    """Partial update. `address` may be null (clears it); name and type may not."""

    model_config = ConfigDict(extra="forbid")

    name: ContactName | None = None
    type: ContactType | None = None
    address: str | None = None

    _clean_address = field_validator("address")(_blank_to_none)

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "ContactUpdate":
        nulls = [f for f in self.model_fields_set if f != "address" and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: ContactType
    address: str | None
