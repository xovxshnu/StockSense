from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.database import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Liveness: does not touch the database."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    """Readiness: verifies connectivity to the configured PostgreSQL."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok", "database": "ok"}
