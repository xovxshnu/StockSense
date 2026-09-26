from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base; feature branches define models on this."""


@lru_cache
def get_engine() -> Engine:
    url = get_settings().DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Lazy: no connection is made until first use. pre_ping survives
    # managed-DB idle disconnects (Neon/Supabase pause connections).
    return create_engine(url, pool_pre_ping=True)


def get_db():
    """FastAPI dependency yielding a session."""
    session = sessionmaker(bind=get_engine(), autoflush=False)()
    try:
        yield session
    finally:
        session.close()
