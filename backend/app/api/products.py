from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import product_service
from app.services.errors import ConflictError, InvalidReferenceError, NotFoundError

router = APIRouter(
    prefix="/api/products",
    tags=["products"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[ProductRead])
def list_products(
    db: DbSession,
    search: Annotated[
        str | None, Query(max_length=100, description="Case-insensitive match on SKU or name")
    ] = None,
    include_inactive: Annotated[bool, Query(description="Include archived products")] = False,
):
    return product_service.list_products(db, search, include_inactive)


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    responses=errors(409, invalid_reference=True),
)
def create_product(data: ProductCreate, db: DbSession):
    try:
        return product_service.create_product(db, data)
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.get("/{product_id}", response_model=ProductRead, responses=errors(404))
def get_product(product_id: int, db: DbSession):
    try:
        return product_service.get_product(db, product_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.put(
    "/{product_id}", response_model=ProductRead, responses=errors(404, 409, invalid_reference=True)
)
def update_product(product_id: int, data: ProductUpdate, db: DbSession):
    try:
        return product_service.update_product(db, product_id, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, responses=errors(404))
def archive_product(product_id: int, db: DbSession) -> Response:
    """Archives (deactivates) the product; it is never physically deleted."""
    try:
        product_service.archive_product(db, product_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
