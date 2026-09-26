from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field


class StockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    location_id: int
    quantity: Decimal
    reserved_quantity: Decimal

    # Derived on read, never stored or accepted as input.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def free_to_use(self) -> Decimal:
        return self.quantity - self.reserved_quantity
