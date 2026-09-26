import enum

from sqlalchemy import CheckConstraint, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class ContactType(str, enum.Enum):
    SUPPLIER = "supplier"
    CUSTOMER = "customer"


class Contact(IdMixin, Base):
    """A supplier or a customer, distinguished by `type` (single table).

    Future Receipt.supplier_id / Delivery.customer_id will reference Contact.id
    and must check type == supplier / customer respectively. Names are not
    unique: different parties may share a name.
    """

    __tablename__ = "contacts"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)

    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[ContactType] = mapped_column(
        # create_constraint adds a CHECK where PostgreSQL's native enum type
        # isn't available (e.g. SQLite in tests).
        Enum(
            ContactType,
            name="contact_type",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=True,
        )
    )
    address: Mapped[str | None] = mapped_column(Text)
