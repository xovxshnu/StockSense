"""Automated migration round trip on SQLite.

This checks that the revision chain is linear and that every migration upgrades,
downgrades and re-upgrades cleanly, and that the result matches the ORM models
(`alembic check`). It does NOT prove PostgreSQL behavior: SQLite has no native
enums, cannot reflect expression indexes (uq_categories_name_lower is skipped by
`alembic check`), does not compare server defaults, and rebuilds tables for some
ALTERs. Live PostgreSQL migration runs remain unverified in this suite.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.filterwarnings(
    "ignore:Skipped unsupported reflection of expression-based index",
    "ignore:autogenerate skipping metadata-specified expression-based index",
)


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()  # env.py reads the URL through get_settings()
    yield Config(str(BACKEND / "alembic.ini")), url
    get_settings.cache_clear()


def tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_revision_chain_is_linear() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1
    revisions = list(script.walk_revisions())  # head -> base
    assert revisions[-1].down_revision is None
    for newer, older in zip(revisions, revisions[1:]):
        assert newer.down_revision == older.revision


def test_upgrade_check_downgrade_upgrade_round_trip(alembic_cfg) -> None:
    cfg, url = alembic_cfg
    expected = {
        "users", "categories", "products", "warehouses", "locations",
        "contacts", "reorder_rules", "document_sequences", "stock", "stock_movements",
    }

    command.upgrade(cfg, "head")
    assert tables(url) - {"alembic_version"} == expected
    command.check(cfg)  # raises if models and migrations have drifted

    command.downgrade(cfg, "base")
    assert tables(url) - {"alembic_version"} == set()

    command.upgrade(cfg, "head")
    assert tables(url) - {"alembic_version"} == expected
    command.check(cfg)


def test_every_migration_downgrades_and_reapplies_one_step_at_a_time(alembic_cfg) -> None:
    cfg, url = alembic_cfg
    revisions = list(ScriptDirectory.from_config(cfg).walk_revisions())  # head -> base
    command.upgrade(cfg, "head")
    for revision in revisions:
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, revision.revision)
        command.downgrade(cfg, "-1")
    assert tables(url) - {"alembic_version"} == set()
