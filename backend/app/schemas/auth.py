import re
from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.models.user import UserRole

_LOGIN_ID_RE = re.compile(r"^[a-z0-9._-]{3,50}$")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class SignupRequest(BaseModel):
    login_id: str
    email: NormalizedEmail
    password: Password

    @field_validator("login_id")
    @classmethod
    def normalize_login_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not _LOGIN_ID_RE.fullmatch(value):
            raise ValueError(
                "login_id must be 3-50 characters: letters, digits, '.', '_' or '-'"
            )
        return value


class LoginRequest(BaseModel):
    """`identifier` is either the login_id or the email (case-insensitive)."""

    identifier: Annotated[str, Field(min_length=1, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login_id: str
    email: str
    role: UserRole
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    token: Annotated[str, Field(min_length=1)]
    new_password: Password


class MessageResponse(BaseModel):
    message: str
