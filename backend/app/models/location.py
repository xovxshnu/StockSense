from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin
from app.models.warehouse import Warehouse


class Location(IdMixin, Base):
    """A storage place inside a warehouse. Location.id is what the future
    Stock(product_id, location_id, ...) rows will reference; this model itself
    holds no quantities."""

    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(short_code)) > 0", name="short_code_not_blank"),
        # short_code is unique per warehouse, not globally. The leading
        # warehouse_id column also serves FK lookups, so no separate index.
        UniqueConstraint("warehouse_id", "short_code", name="uq_locations_warehouse_id_short_code"),
    )

    # Immutable after creation (enforced in the API): see schemas/location.py.
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    short_code: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    warehouse: Mapped[Warehouse] = relationship(back_populates="locations")
