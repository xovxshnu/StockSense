"""GET /api/dashboard, shaped after the blueprint's conceptual response (section 8)."""

from pydantic import BaseModel


class InventoryKpis(BaseModel):
    total_products: int  # active products
    in_stock: int  # ... with quantity on hand above their reorder level
    low_stock: int  # ... with 0 < on hand <= reorder level
    out_of_stock: int  # ... with nothing on hand (including never stocked)


class ReceiptKpis(BaseModel):
    pending: int  # READY: confirmed, waiting to be received
    late: int  # open (DRAFT/READY) with schedule_date before today
    operations: int  # open: DRAFT + READY


class DeliveryKpis(BaseModel):
    pending: int  # READY: stock available, waiting to be delivered
    waiting: int  # WAITING: stock not available
    late: int  # open (DRAFT/WAITING/READY) with schedule_date before today
    operations: int  # open: DRAFT + WAITING + READY


class TransferKpis(BaseModel):
    scheduled: int  # READY: confirmed, waiting to be executed


class DashboardRead(BaseModel):
    inventory: InventoryKpis
    receipts: ReceiptKpis
    deliveries: DeliveryKpis
    transfers: TransferKpis
