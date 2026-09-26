import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, IdMixin
from app.models.product import Product
from app.models.stock import QUANTITY_TYPE


class AdjustmentStatus(str, enum.Enum):
    """DRAFT -> DONE (no other transitions)."""

    DRAFT = "DRAFT"
    DONE = "DONE"


class Adjustment(IdMixin, CreatedAtMixin, Base):
    """A physical count at one location. Validating it (DRAFT -> DONE) sets each
    counted product's stock to the counted quantity, through the Inventory Engine
    (one ADJUSTMENT movement per line whose difference is not zero)."""

    __tablename__ = "adjustments"

    # Backend-generated (sequence_service, prefix WH/ADJ) when the draft is created.
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    # Free text in the operations UI (a textarea), optional.
    reason: Mapped[str | None] = mapped_column(Text)
    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[AdjustmentStatus] = mapped_column(
        Enum(
            AdjustmentStatus,
            name="adjustment_status",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=True,
        ),
        default=AdjustmentStatus.DRAFT,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list["AdjustmentLine"]] = relationship(
        back_populates="adjustment",
        cascade="all, delete-orphan",
        order_by="AdjustmentLine.id",
        passive_deletes=True,
    )


class AdjustmentLine(IdMixin, Base):
    """`counted_quantity` is the only user input. `system_quantity` and
    `difference` are backend-owned: a snapshot of the stock when the draft was
    saved, overwritten at validation with the values actually applied."""

    __tablename__ = "adjustment_lines"
    __table_args__ = (
        UniqueConstraint(
            "adjustment_id", "product_id", name="uq_adjustment_lines_adjustment_id_product_id"
        ),
        CheckConstraint("counted_quantity >= 0", name="counted_quantity_non_negative"),
        CheckConstraint("system_quantity >= 0", name="system_quantity_non_negative"),
        CheckConstraint(
            "difference = counted_quantity - system_quantity", name="difference_consistent"
        ),
    )

    adjustment_id: Mapped[int] = mapped_column(
        ForeignKey("adjustments.id", ondelete="CASCADE")
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    counted_quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)
    system_quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)
    difference: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)

    adjustment: Mapped[Adjustment] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")
