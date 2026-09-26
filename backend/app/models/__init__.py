"""Import every model module here so Alembic autogenerate sees it."""

from app.models.adjustment import Adjustment, AdjustmentLine, AdjustmentStatus
from app.models.base import Base
from app.models.category import Category
from app.models.contact import Contact, ContactType
from app.models.delivery import Delivery, DeliveryLine, DeliveryStatus
from app.models.document_sequence import DocumentSequence
from app.models.location import Location
from app.models.product import Product
from app.models.receipt import Receipt, ReceiptLine, ReceiptStatus
from app.models.reorder_rule import ReorderRule
from app.models.stock import Stock
from app.models.stock_movement import MovementType, StockMovement
from app.models.transfer import Transfer, TransferLine, TransferStatus
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse

__all__ = [
    "Adjustment",
    "AdjustmentLine",
    "AdjustmentStatus",
    "Base",
    "Category",
    "Contact",
    "ContactType",
    "Delivery",
    "DeliveryLine",
    "DeliveryStatus",
    "DocumentSequence",
    "Location",
    "MovementType",
    "Product",
    "Receipt",
    "ReceiptLine",
    "ReceiptStatus",
    "ReorderRule",
    "Stock",
    "StockMovement",
    "Transfer",
    "TransferLine",
    "TransferStatus",
    "User",
    "UserRole",
    "Warehouse",
]
