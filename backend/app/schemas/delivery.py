from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.models.delivery import DeliveryStatus
from app.schemas.operation import OperationLineRead, OperationLines, RecordId

# Blank addresses are stored as null (see the service).
DeliveryAddress = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]

# Required on create; may be omitted on update but never set to null.
_NOT_NULLABLE = ("warehouse_id", "source_location_id", "schedule_date", "lines")


class DeliveryCreate(BaseModel):
    """reference, status and timestamps are backend-owned and therefore absent;
    sending them is a 422."""

    model_config = ConfigDict(extra="forbid")

    customer_id: RecordId | None = None
    warehouse_id: RecordId
    source_location_id: RecordId
    delivery_address: DeliveryAddress | None = None
    schedule_date: date
    responsible_user_id: RecordId | None = None
    lines: OperationLines


class DeliveryUpdate(BaseModel):
    """Only while DRAFT. Fields that are sent replace the stored ones; `lines`, when
    sent, replaces all lines. customer_id / delivery_address / responsible_user_id
    may be null."""

    model_config = ConfigDict(extra="forbid")

    customer_id: RecordId | None = None
    warehouse_id: RecordId | None = None
    source_location_id: RecordId | None = None
    delivery_address: DeliveryAddress | None = None
    schedule_date: date | None = None
    responsible_user_id: RecordId | None = None
    lines: OperationLines | None = None

    @model_validator(mode="after")
    def no_null_required_fields(self) -> "DeliveryUpdate":
        nulls = [f for f in _NOT_NULLABLE if f in self.model_fields_set and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(nulls)}")
        return self


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    status: DeliveryStatus
    customer_id: int | None
    warehouse_id: int
    source_location_id: int
    delivery_address: str | None
    schedule_date: date
    responsible_user_id: int | None
    created_at: datetime
    updated_at: datetime
    lines: list[OperationLineRead]
