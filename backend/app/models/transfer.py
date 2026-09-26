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


class TransferStatus(str, enum.Enum):
    """DRAFT -> READY -> DONE; DRAFT or READY -> CANCELED."""

    DRAFT = "DRAFT"
    READY = "READY"
    DONE = "DONE"
    CANCELED = "CANCELED"


class Transfer(IdMixin, CreatedAtMixin, Base):
    """Moves stock between two locations (possibly in different warehouses: the
    operations UI has no warehouse field for transfers). Validating it
    (READY -> DONE) is the only step that changes stock, through the Inventory
    Engine: one TRANSFER movement per line."""

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("from_location_id != to_location_id", name="locations_differ"),
    )

    # Backend-generated (sequence_service, prefix WH/INT) when the draft is created.
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    from_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    to_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    schedule_date: Mapped[date] = mapped_column(Date)
    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(
            TransferStatus,
            name="transfer_status",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=True,
        ),
        default=TransferStatus.DRAFT,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list["TransferLine"]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
        order_by="TransferLine.id",
        passive_deletes=True,
    )


class TransferLine(IdMixin, Base):
    __tablename__ = "transfer_lines"
    __table_args__ = (
        UniqueConstraint(
            "transfer_id", "product_id", name="uq_transfer_lines_transfer_id_product_id"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfers.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)

    transfer: Mapped[Transfer] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")
