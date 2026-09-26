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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, IdMixin
from app.models.product import Product
from app.models.stock import QUANTITY_TYPE


class DeliveryStatus(str, enum.Enum):
    """DRAFT -> WAITING/READY -> DONE; DRAFT, WAITING or READY -> CANCELED.
    WAITING means the free stock at the source location does not cover every line."""

    DRAFT = "DRAFT"
    WAITING = "WAITING"
    READY = "READY"
    DONE = "DONE"
    CANCELED = "CANCELED"


class Delivery(IdMixin, CreatedAtMixin, Base):
    """Outgoing goods from one location. Validating it (READY -> DONE) is the only
    step that changes stock, and it does so through the Inventory Engine."""

    __tablename__ = "deliveries"

    # Backend-generated (sequence_service, prefix WH/OUT) when the draft is created.
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    # Optional: the operations UI has no customer field yet. When set it must be a
    # Contact of type customer (checked in the service).
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT"), index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    source_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    delivery_address: Mapped[str | None] = mapped_column(Text)
    schedule_date: Mapped[date] = mapped_column(Date)
    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            name="delivery_status",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=True,
        ),
        default=DeliveryStatus.DRAFT,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list["DeliveryLine"]] = relationship(
        back_populates="delivery",
        cascade="all, delete-orphan",
        order_by="DeliveryLine.id",
        passive_deletes=True,
    )


class DeliveryLine(IdMixin, Base):
    __tablename__ = "delivery_lines"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", "product_id", name="uq_delivery_lines_delivery_id_product_id"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)

    delivery: Mapped[Delivery] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")
