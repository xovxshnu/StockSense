from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.errors import ConflictError, InvalidReferenceError, NotFoundError


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_products(
    db: Session, search: str | None = None, include_inactive: bool = False
) -> list[Product]:
    query = select(Product).order_by(Product.name, Product.id)
    if not include_inactive:
        query = query.where(Product.active.is_(True))
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.where(
            Product.sku.ilike(pattern, escape="\\") | Product.name.ilike(pattern, escape="\\")
        )
    return list(db.scalars(query))


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")
    return product


def _check_sku_free(db: Session, sku: str, exclude_id: int | None = None) -> None:
    query = select(Product.id).where(Product.sku == sku)
    if exclude_id is not None:
        query = query.where(Product.id != exclude_id)
    if db.scalar(query) is not None:
        raise ConflictError("SKU already exists")


def _check_category_exists(db: Session, category_id: int) -> None:
    if db.get(Category, category_id) is None:
        raise InvalidReferenceError("category_id does not exist")


def _commit(db: Session, sku: str, category_id: int) -> None:
    """Commit, translating a lost race on the DB constraints into domain errors."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _check_sku_free(db, sku)
        _check_category_exists(db, category_id)
        raise


def create_product(db: Session, data: ProductCreate) -> Product:
    _check_category_exists(db, data.category_id)
    _check_sku_free(db, data.sku)
    product = Product(**data.model_dump())
    db.add(product)
    _commit(db, data.sku, data.category_id)
    db.refresh(product)
    return product


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes:
        _check_category_exists(db, changes["category_id"])
    if "sku" in changes:
        _check_sku_free(db, changes["sku"], exclude_id=product.id)
    for field, value in changes.items():
        setattr(product, field, value)
    _commit(db, product.sku, product.category_id)
    db.refresh(product)
    return product


def archive_product(db: Session, product_id: int) -> None:
    """DELETE semantics: deactivate, never physically delete.

    Future Stock rows and movement history reference Product.id, so the row
    must stay. Archiving is idempotent.
    """
    product = get_product(db, product_id)
    if product.active:
        product.active = False
        db.commit()
