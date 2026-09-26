import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, IdMixin
from app.models.product import Product
from app.models.stock import QUANTITY_TYPE


class ReceiptStatus(str, enum.Enum):
    """DRAFT -> READY -> DONE; DRAFT or READY -> CANCELED."""

    DRAFT = "DRAFT"
    READY = "READY"
    DONE = "DONE"
    CANCELED = "CANCELED"


class Receipt(IdMixin, CreatedAtMixin, Base):
    """Incoming goods into one location. Validating it (READY -> DONE) is the only
    step that changes stock, and it does so through the Inventory Engine."""

    __tablename__ = "receipts"

    # Backend-generated (sequence_service, prefix WH/IN) when the draft is created.
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    # Optional: the operations UI has no supplier field yet. When set it must be a
    # Contact of type supplier (checked in the service).
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT"), index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    destination_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    schedule_date: Mapped[date] = mapped_column(Date)
    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[ReceiptStatus] = mapped_column(
        Enum(
            ReceiptStatus,
            name="receipt_status",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=True,
        ),
        default=ReceiptStatus.DRAFT,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list["ReceiptLine"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptLine.id",
        passive_deletes=True,
    )


class ReceiptLine(IdMixin, Base):
    __tablename__ = "receipt_lines"
    __table_args__ = (
        # One line per product (the operations UI refuses duplicates too). The
        # leading receipt_id column also serves the FK lookup.
        UniqueConstraint("receipt_id", "product_id", name="uq_receipt_lines_receipt_id_product_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)

    receipt: Mapped[Receipt] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")
