"""HTTP translation of the domain errors raised by operation document services."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException, status

from app.api.responses import ErrorResponse
from app.services.errors import InvalidReferenceError, NotFoundError
from app.services.inventory_service import InventoryError
from app.services.operation_common import InvalidTransitionError

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Document not found"},
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": "Not allowed in the document's current status, or an inventory rule "
        "would be broken",
    },
}
INVALID_REFERENCE: dict[int | str, dict[str, Any]] = {
    422: {"description": "Validation error, or a referenced record does not exist / is archived"},
}


@contextmanager
def operation_errors() -> Iterator[None]:
    try:
        yield
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except (InvalidTransitionError, InventoryError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
