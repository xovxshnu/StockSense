"""Shared OpenAPI response declarations.

These only DOCUMENT behavior the routes already have (via HTTPException); they do
not change runtime status codes. 422 (request validation) is added by FastAPI.
"""

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


_DESCRIPTIONS = {
    400: "Invalid or expired token",
    401: "Missing, invalid or expired credentials",
    404: "Resource not found",
    409: "Conflicts with an existing record (uniqueness)",
}


def errors(*codes: int, invalid_reference: bool = False) -> dict[int | str, dict[str, Any]]:
    """`invalid_reference` also documents the 422 the service layer raises for a
    foreign key that points at a missing/archived record (detail is a string)."""
    documented: dict[int | str, dict[str, Any]] = {
        code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in codes
    }
    if invalid_reference:
        documented[422] = {
            "description": "Validation error, or a referenced record does not exist / is archived"
        }
    return documented


# Applied at router level to every authenticated router.
UNAUTHORIZED = errors(401)
