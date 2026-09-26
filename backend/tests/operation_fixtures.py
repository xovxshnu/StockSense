"""Fixtures and helpers shared by the receipt / delivery / operation-flow tests.

Import the fixtures you need into the test module (pytest registers imported
fixtures): `from tests.operation_fixtures import api, md  # noqa: F401`.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    Contact,
    ContactType,
    Location,
    Product,
    Stock,
    StockMovement,
    User,
    Warehouse,
)
from app.services import inventory_service


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def md(db: Session, api: TestClient) -> SimpleNamespace:
    """Master data (committed). `user` is the authenticated API user."""
    category = Category(name="Tools")
    p1 = Product(name="Widget", sku="W1", category=category)
    p2 = Product(name="Bolt", sku="B1", category=category)
    archived_product = Product(name="Old", sku="OLD", category=category, active=False)
    wh = Warehouse(name="Main", short_code="WH")
    other_wh = Warehouse(name="Second", short_code="WH2")
    loc_a = Location(warehouse=wh, name="Stock A", short_code="A")
    loc_b = Location(warehouse=wh, name="Stock B", short_code="B")
    archived_loc = Location(warehouse=wh, name="Closed", short_code="X", active=False)
    other_loc = Location(warehouse=other_wh, name="Elsewhere", short_code="E")
    supplier = Contact(name="Acme Supplies", type=ContactType.SUPPLIER)
    customer = Contact(name="Big Customer", type=ContactType.CUSTOMER)
    db.add_all([p1, p2, archived_product, loc_a, loc_b, archived_loc, other_loc, supplier, customer])
    db.commit()
    user_id = db.scalar(select(User.id).where(User.login_id == "tester"))
    return SimpleNamespace(
        p1=p1.id, p2=p2.id, archived_product=archived_product.id,
        wh=wh.id, other_wh=other_wh.id,
        loc_a=loc_a.id, loc_b=loc_b.id, archived_loc=archived_loc.id, other_loc=other_loc.id,
        supplier=supplier.id, customer=customer.id, user=user_id,
    )


def receipt_body(md: SimpleNamespace, lines=None, **overrides) -> dict:
    return {
        "supplier_id": md.supplier,
        "warehouse_id": md.wh,
        "destination_location_id": md.loc_a,
        "schedule_date": "2026-10-01",
        "lines": lines if lines is not None else [{"product_id": md.p1, "quantity": 100}],
    } | overrides


def delivery_body(md: SimpleNamespace, lines=None, **overrides) -> dict:
    return {
        "customer_id": md.customer,
        "warehouse_id": md.wh,
        "source_location_id": md.loc_a,
        "delivery_address": "1 Main Street",
        "schedule_date": "2026-10-02",
        "lines": lines if lines is not None else [{"product_id": md.p1, "quantity": 20}],
    } | overrides


def stock_qty(db: Session, product_id: int, location_id: int) -> Decimal | None:
    db.expire_all()
    return db.scalar(
        select(Stock.quantity).where(
            Stock.product_id == product_id, Stock.location_id == location_id
        )
    )


def movements(db: Session) -> list[StockMovement]:
    db.expire_all()
    return list(db.scalars(select(StockMovement).order_by(StockMovement.id)))


def put_stock(
    db: Session, md: SimpleNamespace, product_id: int, location_id: int, quantity, reserved=0
) -> None:
    """Test setup: stock through the engine (reference WH/IN/SEED), then an optional
    reservation set directly (nothing in the app reserves stock yet)."""
    inventory_service.receive(
        db, product_id=product_id, location_id=location_id, quantity=Decimal(str(quantity)),
        reference="WH/IN/SEED", source_type="seed", source_id=0, performed_by=md.user,
    )
    if reserved:
        stock = db.scalar(select(Stock).where(
            Stock.product_id == product_id, Stock.location_id == location_id))
        stock.reserved_quantity = Decimal(str(reserved))
    db.commit()


def archive(db: Session, model, record_id: int) -> None:
    db.get(model, record_id).active = False
    db.commit()
