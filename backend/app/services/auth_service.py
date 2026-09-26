from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.models.user import User, UserRole
from app.schemas.auth import SignupRequest

# Verified against when the account doesn't exist, so login timing doesn't
# reveal which identifiers are registered.
_DUMMY_HASH = security.hash_password("stocksense-dummy-password")


class DuplicateUserError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(f"{field} already registered")
        self.field = field


def signup(db: Session, data: SignupRequest) -> User:
    if db.scalar(select(User.id).where(User.login_id == data.login_id)):
        raise DuplicateUserError("login_id")
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise DuplicateUserError("email")

    user = User(
        login_id=data.login_id,
        email=data.email,
        password_hash=security.hash_password(data.password),
        role=UserRole.STAFF,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # concurrent signup won the race
        db.rollback()
        raise DuplicateUserError("login_id or email") from None
    db.refresh(user)
    return user


def authenticate(db: Session, identifier: str, password: str) -> User | None:
    identifier = identifier.strip().lower()
    user = db.scalar(
        select(User).where(or_(User.login_id == identifier, User.email == identifier))
    )
    if user is None:
        security.verify_password(password, _DUMMY_HASH)
        return None
    return user if security.verify_password(password, user.password_hash) else None


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def reset_password(
    db: Session, settings: Settings, token: str, new_password: str
) -> bool:
    decoded = security.decode_reset_token(settings, token)
    if decoded is None:
        return False
    user_id, fingerprint = decoded
    user = db.get(User, user_id)
    if user is None or not security.reset_token_matches(fingerprint, user.password_hash):
        return False
    user.password_hash = security.hash_password(new_password)
    db.commit()
    return True
