from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.schemas.category import CategoryRead, CategoryWrite
from app.services import category_service
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(
    prefix="/api/categories",
    tags=["categories"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[CategoryRead])
def list_categories(db: DbSession):
    return category_service.list_categories(db)


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    responses=errors(409),
)
def create_category(data: CategoryWrite, db: DbSession):
    try:
        return category_service.create_category(db, data)
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.put("/{category_id}", response_model=CategoryRead, responses=errors(404, 409))
def update_category(category_id: int, data: CategoryWrite, db: DbSession):
    try:
        return category_service.update_category(db, category_id, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
