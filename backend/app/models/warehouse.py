from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin

if TYPE_CHECKING:
    from app.models.location import Location


class Warehouse(IdMixin, Base):
    """A physical site. Holds no stock itself: stock is per Location."""

    __tablename__ = "warehouses"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(short_code)) > 0", name="short_code_not_blank"),
    )

    name: Mapped[str] = mapped_column(String(100))
    # Stored normalized (trimmed, uppercase); see schemas/warehouse.py.
    short_code: Mapped[str] = mapped_column(String(20), unique=True)
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    # No ORM cascade: the FK is ON DELETE RESTRICT, so a warehouse that still has
    # locations can never be deleted.
    locations: Mapped[list["Location"]] = relationship(
        back_populates="warehouse", passive_deletes="all"
    )
