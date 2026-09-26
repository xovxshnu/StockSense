from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.models.contact import ContactType
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.services import contact_service
from app.services.errors import NotFoundError

router = APIRouter(
    prefix="/api/contacts",
    tags=["contacts"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[ContactRead])
def list_contacts(
    db: DbSession,
    type: Annotated[ContactType | None, Query(description="supplier or customer")] = None,
):
    return contact_service.list_contacts(db, type)


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(data: ContactCreate, db: DbSession):
    return contact_service.create_contact(db, data)


@router.get("/{contact_id}", response_model=ContactRead, responses=errors(404))
def get_contact(contact_id: int, db: DbSession):
    try:
        return contact_service.get_contact(db, contact_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.put("/{contact_id}", response_model=ContactRead, responses=errors(404))
def update_contact(contact_id: int, data: ContactUpdate, db: DbSession):
    try:
        return contact_service.update_contact(db, contact_id, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
