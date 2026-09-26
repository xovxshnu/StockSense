from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, IdMixin
from app.models.category import Category

if TYPE_CHECKING:
    from app.models.reorder_rule import ReorderRule


class Product(IdMixin, CreatedAtMixin, Base):
    """Catalogue entry. Deliberately holds NO stock quantity: stock is
    location-specific and lives in the future Stock(product_id, location_id)."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(sku)) > 0", name="sku_not_blank"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint("reorder_level >= 0", name="reorder_level_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(200))
    # Stored normalized (trimmed, uppercase); see schemas/product.py.
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    uom: Mapped[str] = mapped_column(String(20), default="Unit", server_default="Unit")
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0"
    )
    reorder_level: Mapped[int] = mapped_column(default=0, server_default="0")
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    category: Mapped[Category] = relationship(back_populates="products")
    # 0..1 rule. No ORM cascade: the FK is ON DELETE RESTRICT, so a product that
    # has a rule can never be deleted out from under it.
    reorder_rule: Mapped["ReorderRule | None"] = relationship(
        back_populates="product", uselist=False, passive_deletes="all"
    )
