"""Import every model module here so Alembic autogenerate sees it."""

from app.models.base import Base
from app.models.category import Category
from app.models.contact import Contact, ContactType
from app.models.document_sequence import DocumentSequence
from app.models.location import Location
from app.models.product import Product
from app.models.reorder_rule import ReorderRule
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse

__all__ = [
    "Base",
    "Category",
    "Contact",
    "ContactType",
    "DocumentSequence",
    "Location",
    "Product",
    "ReorderRule",
    "User",
    "UserRole",
    "Warehouse",
]
