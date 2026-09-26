from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.transfer import TransferStatus
from app.schemas.operation import OperationLineRead, OperationLines, RecordId

# Required on create; may be omitted on update but never set to null.
_NOT_NULLABLE = ("from_location_id", "to_location_id", "schedule_date", "lines")


class TransferCreate(BaseModel):
    """reference, status and timestamps are backend-owned and therefore absent;
    sending them is a 422."""

    model_config = ConfigDict(extra="forbid")

    from_location_id: RecordId
    to_location_id: RecordId
    schedule_date: date
    responsible_user_id: RecordId | None = None
    lines: OperationLines

    @model_validator(mode="after")
    def locations_differ(self) -> "TransferCreate":
        if self.from_location_id == self.to_location_id:
            raise ValueError("from_location_id and to_location_id must differ")
        return self


class TransferUpdate(BaseModel):
    """Only while DRAFT. Fields that are sent replace the stored ones; `lines`, when
    sent, replaces all lines. responsible_user_id may be null."""

    model_config = ConfigDict(extra="forbid")

    from_location_id: RecordId | None = None
    to_location_id: RecordId | None = None
    schedule_date: date | None = None
    responsible_user_id: RecordId | None = None
    lines: OperationLines | None = None

    @model_validator(mode="after")
    def no_null_required_fields(self) -> "TransferUpdate":
        nulls = [f for f in _NOT_NULLABLE if f in self.model_fields_set and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(nulls)}")
        return self


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    status: TransferStatus
    from_location_id: int
    to_location_id: int
    schedule_date: date
    responsible_user_id: int | None
    created_at: datetime
    updated_at: datetime
    lines: list[OperationLineRead]
