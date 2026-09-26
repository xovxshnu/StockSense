from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class DocumentSequence(IdMixin, Base):
    """One counter per reference prefix (e.g. "WH/IN"). Only ever changed through
    app.services.sequence_service; it stores counters, not generated references."""

    __tablename__ = "document_sequences"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_non_negative"),)

    prefix: Mapped[str] = mapped_column(String(50), unique=True)
    last_number: Mapped[int] = mapped_column(default=0, server_default="0")
