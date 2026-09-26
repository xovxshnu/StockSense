"""Helpers shared by the operation document services (receipts, deliveries, ...).

Operation services own the transaction: they lock the document row, call the
Inventory Engine (which never commits) and commit once. They never touch Stock
quantities themselves.
"""

from collections.abc import Iterable
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.contact import Contact, ContactType
from app.models.location import Location
from app.models.product import Product
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.operation import OperationLineIn
from app.services.errors import InvalidReferenceError, NotFoundError

Document = TypeVar("Document")


class InvalidTransitionError(Exception):
    """The document's current status does not allow the requested action."""


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def lock_document(db: Session, model: type[Document], document_id: int, label: str) -> Document:
    """SELECT ... FOR UPDATE on the document row, with fresh values and lines.

    Every status change goes through this lock, so two requests can never both
    act on the same document (e.g. validate it twice, or validate and cancel)."""
    document = db.scalar(
        select(model)
        .where(model.id == document_id)
        .with_for_update()
        .options(selectinload(model.lines))
        .execution_options(populate_existing=True)
    )
    if document is None:
        raise NotFoundError(f"{label} not found")
    return document


def require_status(document, allowed: Iterable, action: str, label: str) -> None:
    if document.status not in allowed:
        raise InvalidTransitionError(
            f"Cannot {action} a {label.lower()} in status {document.status.value}"
        )


def check_warehouse_location(
    db: Session, warehouse_id: int, location_id: int, field: str
) -> None:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise InvalidReferenceError("warehouse_id does not exist")
    if not warehouse.active:
        raise InvalidReferenceError("Warehouse is archived")
    location = db.get(Location, location_id)
    if location is None:
        raise InvalidReferenceError(f"{field} does not exist")
    if not location.active:
        raise InvalidReferenceError(f"{field} is archived")
    if location.warehouse_id != warehouse_id:
        raise InvalidReferenceError(f"{field} does not belong to the selected warehouse")


def check_contact(db: Session, contact_id: int | None, type_: ContactType, field: str) -> None:
    if contact_id is None:
        return
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise InvalidReferenceError(f"{field} does not exist")
    if contact.type is not type_:
        raise InvalidReferenceError(f"{field} must be a {type_.value} contact")


def check_user(db: Session, user_id: int | None, field: str) -> None:
    if user_id is not None and db.get(User, user_id) is None:
        raise InvalidReferenceError(f"{field} does not exist")


def check_products(db: Session, product_ids: Iterable[int]) -> None:
    ids = set(product_ids)
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    for product_id in sorted(ids):
        product = products.get(product_id)
        if product is None:
            raise InvalidReferenceError(f"Product {product_id} does not exist")
        if not product.active:
            raise InvalidReferenceError(f"Product {product_id} is archived")


def replace_lines(db: Session, document, line_model, lines: list[OperationLineIn]) -> None:
    """Replace every line. The old lines are deleted first (flush) so a product
    kept across the edit does not collide with the one-line-per-product rule."""
    document.lines.clear()
    db.flush()
    document.lines.extend(
        line_model(product_id=line.product_id, quantity=line.quantity) for line in lines
    )


def by_product(lines: list) -> list:
    """Stable processing order for multi-line documents, so two documents touching
    the same stock rows lock them in the same order (deadlock avoidance)."""
    return sorted(lines, key=lambda line: line.product_id)
