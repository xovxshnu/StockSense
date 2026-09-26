from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, IdMixin
from app.models.product import Product


class ReorderRule(IdMixin, CreatedAtMixin, Base):
    """How much to reorder of a product. Holds no stock and no threshold: the
    low-stock threshold is Product.reorder_level (single source of truth) and the
    quantity on hand lives in the future Stock model, per location."""

    __tablename__ = "reorder_rules"
    __table_args__ = (CheckConstraint("reorder_quantity > 0", name="reorder_quantity_positive"),)

    # UNIQUE makes this a 0..1 relationship from the Product side. Immutable
    # after creation (enforced in the API).
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), unique=True
    )
    reorder_quantity: Mapped[int]

    product: Mapped[Product] = relationship(back_populates="reorder_rule")
