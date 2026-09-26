from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, String, func, literal_column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin

if TYPE_CHECKING:
    from app.models.product import Product


class Category(IdMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        # Names are unique case-insensitively ("Tools" == "tools"); the original
        # casing is kept for display.
        Index("uq_categories_name_lower", func.lower(literal_column("name")), unique=True),
    )

    name: Mapped[str] = mapped_column(String(100))

    # No ORM cascade: the FK is ON DELETE RESTRICT, so a category that still has
    # products can never be deleted.
    products: Mapped[list["Product"]] = relationship(
        back_populates="category", passive_deletes="all"
    )
