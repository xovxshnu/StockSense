from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contact import Contact, ContactType
from app.schemas.contact import ContactCreate, ContactUpdate
from app.services.errors import NotFoundError


def list_contacts(db: Session, type: ContactType | None = None) -> list[Contact]:
    query = select(Contact).order_by(Contact.name, Contact.id)
    if type is not None:
        query = query.where(Contact.type == type)
    return list(db.scalars(query))


def get_contact(db: Session, contact_id: int) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise NotFoundError("Contact not found")
    return contact


def create_contact(db: Session, data: ContactCreate) -> Contact:
    contact = Contact(**data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def update_contact(db: Session, contact_id: int, data: ContactUpdate) -> Contact:
    contact = get_contact(db, contact_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact
