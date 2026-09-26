from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.user import User
from app.utils.notifications import deliver_password_reset

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = security.decode_access_token(settings, credentials.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise unauthorized
    return user


def get_reset_notifier() -> Callable[[Settings, str, str], None]:
    """Injectable so tests (and a future email sender) can replace delivery."""
    return deliver_password_reset


CurrentUser = Annotated[User, Depends(get_current_user)]
ResetNotifier = Annotated[
    Callable[[Settings, str, str], None], Depends(get_reset_notifier)
]
