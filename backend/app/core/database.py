from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# The one declarative Base lives in app.models.base (with the naming convention
# Alembic relies on). Re-exported here because the develop scaffold's convention
# is `from app.core.database import Base`.
from app.models.base import Base

__all__ = ["Base", "get_db", "get_engine", "get_session_factory"]


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding one session per request."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
