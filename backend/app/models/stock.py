from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin

# Shared by Stock and StockMovement so quantities are always comparable.
QUANTITY_TYPE = Numeric(14, 3)


class Stock(IdMixin, CreatedAtMixin, Base):
    """Current on-hand quantity of one product at one location.

    Only the Inventory Engine may change `quantity` / `reserved_quantity`; every
    change there is paired with a StockMovement, which is the ledger. The free
    quantity (`quantity - reserved_quantity`) is derived, never stored.
    """

    __tablename__ = "stock"
    __table_args__ = (
        UniqueConstraint("product_id", "location_id", name="uq_stock_product_id_location_id"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_quantity_non_negative"),
        CheckConstraint("reserved_quantity <= quantity", name="reserved_not_above_quantity"),
    )

    # The unique constraint's leading product_id column serves product lookups,
    # so only location_id gets its own index.
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        QUANTITY_TYPE, default=Decimal("0"), server_default="0"
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        QUANTITY_TYPE, default=Decimal("0"), server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def free_to_use(self) -> Decimal:
        return self.quantity - self.reserved_quantity
