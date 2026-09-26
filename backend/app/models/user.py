import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin


class UserRole(str, enum.Enum):
    """Minimal MVP roles. ADMIN is reserved for future privileged endpoints;
    signup always creates STAFF."""

    ADMIN = "admin"
    STAFF = "staff"


class User(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    # Both are stored normalized (lowercase, trimmed); see schemas/auth.py.
    login_id: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=UserRole.STAFF,
    )
