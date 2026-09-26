from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.reorder_rule import ReorderRule
from app.schemas.reorder_rule import ReorderRuleCreate, ReorderRuleUpdate
from app.services.errors import ConflictError, InvalidReferenceError, NotFoundError


def list_rules(db: Session) -> list[ReorderRule]:
    return list(db.scalars(select(ReorderRule).order_by(ReorderRule.id)))


def get_rule(db: Session, rule_id: int) -> ReorderRule:
    rule = db.get(ReorderRule, rule_id)
    if rule is None:
        raise NotFoundError("Reorder rule not found")
    return rule


def _check_product(db: Session, product_id: int) -> None:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")
    if not product.active:
        raise InvalidReferenceError("Product is archived")


def _check_no_rule(db: Session, product_id: int) -> None:
    if db.scalar(select(ReorderRule.id).where(ReorderRule.product_id == product_id)) is not None:
        raise ConflictError("Product already has a reorder rule")


def create_rule(db: Session, data: ReorderRuleCreate) -> ReorderRule:
    _check_product(db, data.product_id)
    _check_no_rule(db, data.product_id)
    rule = ReorderRule(**data.model_dump())
    db.add(rule)
    try:
        db.commit()
    except IntegrityError:  # lost a race on the unique product_id
        db.rollback()
        _check_product(db, data.product_id)
        _check_no_rule(db, data.product_id)
        raise
    db.refresh(rule)
    return rule


def update_rule(db: Session, rule_id: int, data: ReorderRuleUpdate) -> ReorderRule:
    rule = get_rule(db, rule_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = get_rule(db, rule_id)
    db.delete(rule)
    db.commit()
