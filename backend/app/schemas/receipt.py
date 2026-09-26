from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.receipt import ReceiptStatus
from app.schemas.operation import OperationLineRead, OperationLines, RecordId

# Required on create; may be omitted on update but never set to null.
_NOT_NULLABLE = ("warehouse_id", "destination_location_id", "schedule_date", "lines")


class ReceiptCreate(BaseModel):
    """reference, status and timestamps are backend-owned and therefore absent;
    sending them is a 422."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: RecordId | None = None
    warehouse_id: RecordId
    destination_location_id: RecordId
    schedule_date: date
    responsible_user_id: RecordId | None = None
    lines: OperationLines


class ReceiptUpdate(BaseModel):
    """Only while DRAFT. Fields that are sent replace the stored ones; `lines`, when
    sent, replaces all lines. supplier_id / responsible_user_id may be null."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: RecordId | None = None
    warehouse_id: RecordId | None = None
    destination_location_id: RecordId | None = None
    schedule_date: date | None = None
    responsible_user_id: RecordId | None = None
    lines: OperationLines | None = None

    @model_validator(mode="after")
    def no_null_required_fields(self) -> "ReceiptUpdate":
        nulls = [f for f in _NOT_NULLABLE if f in self.model_fields_set and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(nulls)}")
        return self


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    status: ReceiptStatus
    supplier_id: int | None
    warehouse_id: int
    destination_location_id: int
    schedule_date: date
    responsible_user_id: int | None
    created_at: datetime
    updated_at: datetime
    lines: list[OperationLineRead]
