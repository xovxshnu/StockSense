import enum
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin
from app.models.stock import QUANTITY_TYPE


class MovementType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"


class StockMovement(IdMixin, CreatedAtMixin, Base):
    """The authoritative stock ledger: one row per stock change, written only by
    the Inventory Engine. Move History reads this table; there is no second store.

    Location shape per type (enforced by CHECK constraints):
      IN          -> to_location only
      OUT         -> from_location only
      TRANSFER    -> both, and they differ
      ADJUSTMENT  -> to_location only (the adjusted location)

    `quantity` is positive, except ADJUSTMENT where it is the signed difference
    (counted - system); it is never zero. `source_type`/`source_id` point at the
    originating document (receipt, delivery, ...) and are polymorphic, so no FK.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type != 'IN' OR (from_location_id IS NULL AND to_location_id IS NOT NULL)",
            name="in_locations",
        ),
        CheckConstraint(
            "movement_type != 'OUT' OR (from_location_id IS NOT NULL AND to_location_id IS NULL)",
            name="out_locations",
        ),
        CheckConstraint(
            "movement_type != 'TRANSFER' OR (from_location_id IS NOT NULL"
            " AND to_location_id IS NOT NULL AND from_location_id != to_location_id)",
            name="transfer_locations",
        ),
        CheckConstraint(
            "movement_type != 'ADJUSTMENT'"
            " OR (from_location_id IS NULL AND to_location_id IS NOT NULL)",
            name="adjustment_locations",
        ),
        CheckConstraint("quantity != 0", name="quantity_not_zero"),
        CheckConstraint(
            "movement_type = 'ADJUSTMENT' OR quantity > 0",
            name="quantity_positive_unless_adjustment",
        ),
        CheckConstraint("length(trim(reference)) > 0", name="reference_not_blank"),
        CheckConstraint("length(trim(source_type)) > 0", name="source_type_not_blank"),
        Index("ix_stock_movements_created_at", "created_at"),
    )

    reference: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(
            MovementType,
            name="movement_type",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=True,
        ),
        index=True,
    )
    from_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    to_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[int]
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
