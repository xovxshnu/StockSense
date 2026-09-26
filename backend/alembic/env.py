from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.core.database import Base
# Feature branches: import model modules here so autogenerate sees them.

target_metadata = Base.metadata


def run_migrations_online():
    url = get_settings().DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    with create_engine(url).connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline():
    context.configure(url=get_settings().DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
