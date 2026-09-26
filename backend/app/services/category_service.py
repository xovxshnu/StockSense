from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.schemas.category import CategoryWrite
from app.services.errors import ConflictError, NotFoundError


def _name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = select(Category.id).where(func.lower(Category.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return db.scalar(query) is not None


def list_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(func.lower(Category.name), Category.id)))


def get_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise NotFoundError("Category not found")
    return category


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:  # concurrent request won the race on the unique index
        db.rollback()
        raise ConflictError("Category name already exists") from None


def create_category(db: Session, data: CategoryWrite) -> Category:
    if _name_taken(db, data.name):
        raise ConflictError("Category name already exists")
    category = Category(name=data.name)
    db.add(category)
    _commit(db)
    db.refresh(category)
    return category


def update_category(db: Session, category_id: int, data: CategoryWrite) -> Category:
    category = get_category(db, category_id)
    if _name_taken(db, data.name, exclude_id=category.id):
        raise ConflictError("Category name already exists")
    category.name = data.name
    _commit(db)
    db.refresh(category)
    return category
