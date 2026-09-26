"""GET /api/dashboard: KPIs aggregated by the database from current state.

Inventory figures come from Stock (never from replaying StockMovement);
operation figures come from the document tables and their workflow status.
Each group is ONE aggregate query (COUNT/SUM over CASE), whatever the data size.

"Open" = not DONE and not CANCELED. "Late" = open with schedule_date before
today (UTC). Optional filters scope everything to a warehouse, a location
and/or a product category.
"""

from datetime import UTC, date, datetime

from sqlalchemy import ColumnElement, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery, DeliveryLine, DeliveryStatus
from app.models.location import Location
from app.models.product import Product
from app.models.receipt import Receipt, ReceiptLine, ReceiptStatus
from app.models.transfer import Transfer, TransferLine, TransferStatus
from app.schemas.dashboard import (
    DashboardRead,
    DeliveryKpis,
    InventoryKpis,
    ReceiptKpis,
    TransferKpis,
)
from app.schemas.inventory import StockStatus
from app.services.stock_service import product_totals, status_expression


def _count(condition) -> ColumnElement[int]:
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _has_line_in_category(line_model, document_fk, document_id, category_id: int):
    return exists(
        select(line_model.id)
        .join(Product, Product.id == line_model.product_id)
        .where(document_fk == document_id, Product.category_id == category_id)
    )


def _inventory(db: Session, warehouse_id, location_id, category_id) -> InventoryKpis:
    totals = product_totals(warehouse_id=warehouse_id, location_id=location_id)
    status = status_expression(func.coalesce(totals.c.quantity, 0), Product.reorder_level)
    query = (
        select(
            func.count(Product.id).label("total_products"),
            _count(status == StockStatus.IN_STOCK.value).label("in_stock"),
            _count(status == StockStatus.LOW_STOCK.value).label("low_stock"),
            _count(status == StockStatus.OUT_OF_STOCK.value).label("out_of_stock"),
        )
        .select_from(Product)
        .outerjoin(totals, totals.c.product_id == Product.id)
        .where(Product.active.is_(True))
    )
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    return InventoryKpis.model_validate(db.execute(query).one()._mapping)


def _receipts(db: Session, today: date, warehouse_id, location_id, category_id) -> ReceiptKpis:
    open_ = Receipt.status.in_([ReceiptStatus.DRAFT, ReceiptStatus.READY])
    query = select(
        _count(Receipt.status == ReceiptStatus.READY).label("pending"),
        _count(and_(open_, Receipt.schedule_date < today)).label("late"),
        _count(open_).label("operations"),
    )
    if warehouse_id is not None:
        query = query.where(Receipt.warehouse_id == warehouse_id)
    if location_id is not None:
        query = query.where(Receipt.destination_location_id == location_id)
    if category_id is not None:
        query = query.where(
            _has_line_in_category(ReceiptLine, ReceiptLine.receipt_id, Receipt.id, category_id)
        )
    return ReceiptKpis.model_validate(db.execute(query).one()._mapping)


def _deliveries(db: Session, today: date, warehouse_id, location_id, category_id) -> DeliveryKpis:
    open_ = Delivery.status.in_(
        [DeliveryStatus.DRAFT, DeliveryStatus.WAITING, DeliveryStatus.READY]
    )
    query = select(
        _count(Delivery.status == DeliveryStatus.READY).label("pending"),
        _count(Delivery.status == DeliveryStatus.WAITING).label("waiting"),
        _count(and_(open_, Delivery.schedule_date < today)).label("late"),
        _count(open_).label("operations"),
    )
    if warehouse_id is not None:
        query = query.where(Delivery.warehouse_id == warehouse_id)
    if location_id is not None:
        query = query.where(Delivery.source_location_id == location_id)
    if category_id is not None:
        query = query.where(
            _has_line_in_category(DeliveryLine, DeliveryLine.delivery_id, Delivery.id, category_id)
        )
    return DeliveryKpis.model_validate(db.execute(query).one()._mapping)


def _transfers(db: Session, warehouse_id, location_id, category_id) -> TransferKpis:
    query = select(_count(Transfer.status == TransferStatus.READY).label("scheduled"))
    if warehouse_id is not None:
        in_warehouse = select(Location.id).where(Location.warehouse_id == warehouse_id)
        query = query.where(
            or_(Transfer.from_location_id.in_(in_warehouse), Transfer.to_location_id.in_(in_warehouse))
        )
    if location_id is not None:
        query = query.where(
            or_(Transfer.from_location_id == location_id, Transfer.to_location_id == location_id)
        )
    if category_id is not None:
        query = query.where(
            _has_line_in_category(TransferLine, TransferLine.transfer_id, Transfer.id, category_id)
        )
    return TransferKpis.model_validate(db.execute(query).one()._mapping)


def get_dashboard(
    db: Session,
    *,
    warehouse_id: int | None = None,
    location_id: int | None = None,
    category_id: int | None = None,
    today: date | None = None,
) -> DashboardRead:
    today = today or datetime.now(UTC).date()
    return DashboardRead(
        inventory=_inventory(db, warehouse_id, location_id, category_id),
        receipts=_receipts(db, today, warehouse_id, location_id, category_id),
        deliveries=_deliveries(db, today, warehouse_id, location_id, category_id),
        transfers=_transfers(db, warehouse_id, location_id, category_id),
    )
