from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import DbSession, get_current_user
from app.api.responses import UNAUTHORIZED, errors
from app.schemas.reorder_rule import ReorderRuleCreate, ReorderRuleRead, ReorderRuleUpdate
from app.services import reorder_rule_service
from app.services.errors import ConflictError, InvalidReferenceError, NotFoundError

router = APIRouter(
    prefix="/api/reorder-rules",
    tags=["reorder-rules"],
    dependencies=[Depends(get_current_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=list[ReorderRuleRead])
def list_rules(db: DbSession):
    return reorder_rule_service.list_rules(db)


@router.post(
    "",
    response_model=ReorderRuleRead,
    status_code=status.HTTP_201_CREATED,
    responses=errors(404, 409, invalid_reference=True),
)
def create_rule(data: ReorderRuleCreate, db: DbSession):
    try:
        return reorder_rule_service.create_rule(db, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.get("/{rule_id}", response_model=ReorderRuleRead, responses=errors(404))
def get_rule(rule_id: int, db: DbSession):
    try:
        return reorder_rule_service.get_rule(db, rule_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.put("/{rule_id}", response_model=ReorderRuleRead, responses=errors(404))
def update_rule(rule_id: int, data: ReorderRuleUpdate, db: DbSession):
    """Update reorder_quantity. product_id is immutable."""
    try:
        return reorder_rule_service.update_rule(db, rule_id, data)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, responses=errors(404))
def delete_rule(rule_id: int, db: DbSession) -> Response:
    """Physically deletes the rule (it has no active flag)."""
    try:
        reorder_rule_service.delete_rule(db, rule_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
