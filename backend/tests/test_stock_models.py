"""Persistence tests for Stock and StockMovement (Inventory Core, phase 1).

Every constraint test runs twice when possible:

* sqlite     - the shared in-memory `db` fixture (schema from Base.metadata).
               SQLite does enforce CHECK, UNIQUE and (with the PRAGMA in
               conftest) FOREIGN KEY constraints, but it stores NUMERIC as a
               float and has no native enum type.
* postgresql - only when TEST_POSTGRES_URL points at a DISPOSABLE, empty
               PostgreSQL database. The schema there is built by running the real
               Alembic migrations, so these runs also prove the migration DDL.
               The database is downgraded back to empty afterwards.
"""

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import (
    Category,
    Location,
    MovementType,
    Product,
    Stock,
    StockMovement,
    User,
    Warehouse,
)
from app.schemas.stock import StockRead
from app.schemas.stock_movement import MovementRead

BACKEND = Path(__file__).resolve().parent.parent
PG_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.filterwarnings(
    "ignore:Skipped unsupported reflection of expression-based index",
    "ignore:autogenerate skipping metadata-specified expression-based index",
)


def alembic_config(url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()  # env.py reads the URL through get_settings()
    return Config(str(BACKEND / "alembic.ini"))


@pytest.fixture(scope="module")
def pg_engine() -> Iterator:
    with pytest.MonkeyPatch.context() as monkeypatch:
        cfg = alembic_config(PG_URL, monkeypatch)
        command.upgrade(cfg, "head")
        engine = create_engine(get_settings().database_url)
        try:
            yield engine
        finally:
            engine.dispose()
            command.downgrade(cfg, "base")
            get_settings.cache_clear()


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(not PG_URL, reason="needs a disposable PostgreSQL database"),
        ),
    ]
)
def session(request: pytest.FixtureRequest) -> Iterator[Session]:
    if request.param == "sqlite":
        yield request.getfixturevalue("db")
        return
    engine = request.getfixturevalue("pg_engine")
    with sessionmaker(bind=engine, expire_on_commit=False)() as pg_session:
        yield pg_session
        pg_session.rollback()
    with engine.begin() as connection:
        tables = ", ".join(
            t for t in inspect(connection).get_table_names() if t != "alembic_version"
        )
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def refs(session: Session) -> dict[str, int]:
    """Committed master data the stock rows point at."""
    category = Category(name="Tools")
    product = Product(name="Widget", sku="W1", category=category)
    other_product = Product(name="Bolt", sku="B1", category=category)
    warehouse = Warehouse(name="Main", short_code="WH")
    stock_a = Location(warehouse=warehouse, name="Shelf A", short_code="A")
    stock_b = Location(warehouse=warehouse, name="Shelf B", short_code="B")
    user = User(login_id="vishnu", email="vishnu@example.com", password_hash="x")
    session.add_all([product, other_product, stock_a, stock_b, user])
    session.commit()
    return {
        "product": product.id,
        "other_product": other_product.id,
        "loc_a": stock_a.id,
        "loc_b": stock_b.id,
        "user": user.id,
    }


def assert_rejected(session: Session, obj: object) -> None:
    session.add(obj)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def movement(refs: dict[str, int], **overrides) -> StockMovement:
    values = {
        "reference": "WH/IN/0001",
        "product_id": refs["product"],
        "movement_type": MovementType.IN,
        "from_location_id": None,
        "to_location_id": refs["loc_a"],
        "quantity": Decimal("100"),
        "source_type": "receipt",
        "source_id": 1,
        "performed_by": refs["user"],
    } | overrides
    return StockMovement(**values)


# --- Stock ------------------------------------------------------------------


def test_stock_creation(session: Session, refs: dict[str, int]) -> None:
    stock = Stock(product_id=refs["product"], location_id=refs["loc_a"])
    session.add(stock)
    session.commit()
    session.expire_all()

    stored = session.get(Stock, stock.id)
    assert stored.quantity == Decimal("0") and stored.reserved_quantity == Decimal("0")
    assert isinstance(stored.quantity, Decimal)
    assert stored.created_at is not None and stored.updated_at is not None
    assert stored.free_to_use == Decimal("0")


def test_stock_keeps_decimal_quantities(session: Session, refs: dict[str, int]) -> None:
    stock = Stock(
        product_id=refs["product"],
        location_id=refs["loc_a"],
        quantity=Decimal("10.125"),
        reserved_quantity=Decimal("2.5"),
    )
    session.add(stock)
    session.commit()
    session.expire_all()

    stored = session.get(Stock, stock.id)
    assert stored.quantity == Decimal("10.125")
    assert stored.free_to_use == Decimal("7.625")


def test_same_product_may_be_stocked_at_several_locations(
    session: Session, refs: dict[str, int]
) -> None:
    session.add_all(
        [
            Stock(product_id=refs["product"], location_id=refs["loc_a"]),
            Stock(product_id=refs["product"], location_id=refs["loc_b"]),
            Stock(product_id=refs["other_product"], location_id=refs["loc_a"]),
        ]
    )
    session.commit()


def test_product_location_pair_is_unique(session: Session, refs: dict[str, int]) -> None:
    session.add(Stock(product_id=refs["product"], location_id=refs["loc_a"]))
    session.commit()
    assert_rejected(session, Stock(product_id=refs["product"], location_id=refs["loc_a"]))


def test_quantity_cannot_be_negative(session: Session, refs: dict[str, int]) -> None:
    assert_rejected(
        session,
        Stock(product_id=refs["product"], location_id=refs["loc_a"], quantity=Decimal("-1")),
    )


def test_reserved_quantity_cannot_be_negative(session: Session, refs: dict[str, int]) -> None:
    assert_rejected(
        session,
        Stock(
            product_id=refs["product"],
            location_id=refs["loc_a"],
            quantity=Decimal("5"),
            reserved_quantity=Decimal("-1"),
        ),
    )


def test_reserved_quantity_cannot_exceed_quantity(session: Session, refs: dict[str, int]) -> None:
    assert_rejected(
        session,
        Stock(
            product_id=refs["product"],
            location_id=refs["loc_a"],
            quantity=Decimal("5"),
            reserved_quantity=Decimal("5.001"),
        ),
    )


def test_reserved_quantity_may_equal_quantity(session: Session, refs: dict[str, int]) -> None:
    stock = Stock(
        product_id=refs["product"],
        location_id=refs["loc_a"],
        quantity=Decimal("5"),
        reserved_quantity=Decimal("5"),
    )
    session.add(stock)
    session.commit()
    assert stock.free_to_use == Decimal("0")


@pytest.mark.parametrize("field", ["product_id", "location_id"])
def test_stock_foreign_keys(session: Session, refs: dict[str, int], field: str) -> None:
    values = {"product_id": refs["product"], "location_id": refs["loc_a"], field: 999_999}
    assert_rejected(session, Stock(**values))


def test_stock_foreign_keys_restrict_delete(session: Session, refs: dict[str, int]) -> None:
    session.add(Stock(product_id=refs["product"], location_id=refs["loc_a"]))
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(text("DELETE FROM locations WHERE id = :id"), {"id": refs["loc_a"]})
    session.rollback()


def test_stock_has_no_stored_free_to_use() -> None:
    columns = {c.key for c in inspect(Stock).columns}
    assert columns == {
        "id", "product_id", "location_id", "quantity", "reserved_quantity",
        "created_at", "updated_at",
    }


def test_product_still_has_no_stock_quantity() -> None:
    assert not {"quantity", "reserved_quantity"} & {c.key for c in inspect(Product).columns}


# --- StockMovement ----------------------------------------------------------


def test_movement_enum_values() -> None:
    assert [m.value for m in MovementType] == ["IN", "OUT", "TRANSFER", "ADJUSTMENT"]


def test_db_rejects_unknown_movement_type(session: Session, refs: dict[str, int]) -> None:
    # Bypass the ORM enum so the database's own enum/CHECK is what rejects it.
    with pytest.raises((IntegrityError, StatementError)):
        session.execute(
            text(
                "INSERT INTO stock_movements (reference, product_id, movement_type, "
                "to_location_id, quantity, source_type, source_id, performed_by) "
                "VALUES ('R', :p, 'BOGUS', :l, 1, 'receipt', 1, :u)"
            ),
            {"p": refs["product"], "l": refs["loc_a"], "u": refs["user"]},
        )
    session.rollback()


def test_valid_in_movement(session: Session, refs: dict[str, int]) -> None:
    session.add(movement(refs))
    session.commit()
    session.expire_all()
    stored = session.get(StockMovement, 1)
    assert stored.movement_type is MovementType.IN
    assert stored.from_location_id is None and stored.to_location_id == refs["loc_a"]
    assert stored.quantity == Decimal("100") and stored.created_at is not None


def test_valid_out_movement(session: Session, refs: dict[str, int]) -> None:
    session.add(
        movement(
            refs,
            reference="WH/OUT/0001",
            movement_type=MovementType.OUT,
            from_location_id=refs["loc_a"],
            to_location_id=None,
            quantity=Decimal("20"),
            source_type="delivery",
        )
    )
    session.commit()


def test_valid_transfer_movement(session: Session, refs: dict[str, int]) -> None:
    session.add(
        movement(
            refs,
            reference="WH/INT/0001",
            movement_type=MovementType.TRANSFER,
            from_location_id=refs["loc_a"],
            to_location_id=refs["loc_b"],
            quantity=Decimal("30"),
            source_type="transfer",
        )
    )
    session.commit()


def test_same_location_transfer_rejected(session: Session, refs: dict[str, int]) -> None:
    assert_rejected(
        session,
        movement(
            refs,
            movement_type=MovementType.TRANSFER,
            from_location_id=refs["loc_a"],
            to_location_id=refs["loc_a"],
        ),
    )


@pytest.mark.parametrize("quantity", [Decimal("3"), Decimal("-3"), Decimal("-0.5")])
def test_valid_adjustment_movement(
    session: Session, refs: dict[str, int], quantity: Decimal
) -> None:
    session.add(
        movement(
            refs,
            reference="WH/ADJ/0001",
            movement_type=MovementType.ADJUSTMENT,
            to_location_id=refs["loc_b"],
            quantity=quantity,
            source_type="adjustment",
        )
    )
    session.commit()
    session.expire_all()
    assert session.get(StockMovement, 1).quantity == quantity


@pytest.mark.parametrize(
    "movement_type, from_loc, to_loc",
    [
        (MovementType.IN, None, None),
        (MovementType.IN, "loc_a", "loc_b"),
        (MovementType.IN, "loc_a", None),
        (MovementType.OUT, None, None),
        (MovementType.OUT, "loc_a", "loc_b"),
        (MovementType.OUT, None, "loc_a"),
        (MovementType.TRANSFER, "loc_a", None),
        (MovementType.TRANSFER, None, "loc_b"),
        (MovementType.ADJUSTMENT, None, None),
        (MovementType.ADJUSTMENT, "loc_a", None),
        (MovementType.ADJUSTMENT, "loc_a", "loc_b"),
    ],
)
def test_location_shape_is_enforced_per_type(
    session: Session, refs: dict[str, int], movement_type, from_loc, to_loc
) -> None:
    assert_rejected(
        session,
        movement(
            refs,
            movement_type=movement_type,
            from_location_id=refs[from_loc] if from_loc else None,
            to_location_id=refs[to_loc] if to_loc else None,
        ),
    )


@pytest.mark.parametrize(
    "movement_type, from_loc, to_loc",
    [
        (MovementType.IN, None, "loc_a"),
        (MovementType.OUT, "loc_a", None),
        (MovementType.TRANSFER, "loc_a", "loc_b"),
    ],
)
@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1")])
def test_non_adjustment_quantity_must_be_positive(
    session: Session, refs: dict[str, int], movement_type, from_loc, to_loc, quantity
) -> None:
    assert_rejected(
        session,
        movement(
            refs,
            movement_type=movement_type,
            from_location_id=refs[from_loc] if from_loc else None,
            to_location_id=refs[to_loc] if to_loc else None,
            quantity=quantity,
        ),
    )


def test_zero_adjustment_rejected(session: Session, refs: dict[str, int]) -> None:
    assert_rejected(
        session, movement(refs, movement_type=MovementType.ADJUSTMENT, quantity=Decimal("0"))
    )


@pytest.mark.parametrize("field", ["reference", "source_type"])
def test_blank_text_fields_rejected(session: Session, refs: dict[str, int], field: str) -> None:
    assert_rejected(session, movement(refs, **{field: "  "}))


@pytest.mark.parametrize(
    "field", ["reference", "product_id", "movement_type", "quantity", "source_type",
              "source_id", "performed_by"],
)
def test_required_movement_fields(session: Session, refs: dict[str, int], field: str) -> None:
    assert_rejected(session, movement(refs, **{field: None}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"product_id": 999_999},
        {"to_location_id": 999_999},
        {"performed_by": 999_999},
        {
            "movement_type": MovementType.OUT,
            "from_location_id": 999_999,
            "to_location_id": None,
        },
    ],
    ids=["product", "to_location", "performed_by", "from_location"],
)
def test_movement_foreign_keys(session: Session, refs: dict[str, int], overrides) -> None:
    assert_rejected(session, movement(refs, **overrides))


def test_movement_reference_is_not_unique(session: Session, refs: dict[str, int]) -> None:
    """One document with several lines writes several movements sharing its reference."""
    session.add_all(
        [movement(refs), movement(refs, product_id=refs["other_product"], source_id=1)]
    )
    session.commit()


def test_movement_indexes(session: Session) -> None:
    indexed = {
        tuple(ix["column_names"]) for ix in inspect(session.get_bind()).get_indexes("stock_movements")
    }
    for column in ("product_id", "created_at", "movement_type", "reference",
                   "from_location_id", "to_location_id"):
        assert (column,) in indexed


# --- Read schemas -----------------------------------------------------------


def test_stock_read_schema(session: Session, refs: dict[str, int]) -> None:
    stock = Stock(
        product_id=refs["product"],
        location_id=refs["loc_a"],
        quantity=Decimal("100"),
        reserved_quantity=Decimal("30"),
    )
    session.add(stock)
    session.commit()

    body = StockRead.model_validate(stock).model_dump(mode="json")
    assert set(body) == {
        "id", "product_id", "location_id", "quantity", "reserved_quantity", "free_to_use",
    }
    assert Decimal(body["free_to_use"]) == Decimal("70")


def test_stock_read_derives_free_to_use_from_fields() -> None:
    read = StockRead(
        id=1, product_id=1, location_id=1, quantity=Decimal("10"), reserved_quantity=Decimal("4")
    )
    assert read.free_to_use == Decimal("6")


def test_movement_read_schema(session: Session, refs: dict[str, int]) -> None:
    row = movement(
        refs,
        reference="WH/ADJ/0001",
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("-3"),
        source_type="adjustment",
    )
    session.add(row)
    session.commit()

    body = MovementRead.model_validate(row).model_dump(mode="json")
    assert set(body) == {
        "id", "reference", "product_id", "movement_type", "from_location_id",
        "to_location_id", "quantity", "source_type", "source_id", "performed_by", "created_at",
    }
    assert body["movement_type"] == "ADJUSTMENT"
    assert Decimal(body["quantity"]) == Decimal("-3")
    assert body["from_location_id"] is None


# --- Migration 0008 ---------------------------------------------------------


@pytest.fixture
def sqlite_migration_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    yield alembic_config(url, monkeypatch), url
    get_settings.cache_clear()


def inspect_url(url: str, fn):
    engine = create_engine(url)
    try:
        return fn(inspect(engine))
    finally:
        engine.dispose()


def test_migration_0008_upgrade(sqlite_migration_db) -> None:
    cfg, url = sqlite_migration_db
    command.upgrade(cfg, "0007")
    assert "stock" not in inspect_url(url, lambda i: i.get_table_names())

    command.upgrade(cfg, "0008")

    def check(insp) -> None:
        assert {"stock", "stock_movements"} <= set(insp.get_table_names())
        assert {u["name"] for u in insp.get_unique_constraints("stock")} == {
            "uq_stock_product_id_location_id"
        }
        assert {c["name"] for c in insp.get_check_constraints("stock")} == {
            "ck_stock_quantity_non_negative",
            "ck_stock_reserved_quantity_non_negative",
            "ck_stock_reserved_not_above_quantity",
        }
        assert {c["name"] for c in insp.get_check_constraints("stock_movements")} >= {
            "ck_stock_movements_in_locations",
            "ck_stock_movements_out_locations",
            "ck_stock_movements_transfer_locations",
            "ck_stock_movements_adjustment_locations",
            "ck_stock_movements_quantity_not_zero",
            "ck_stock_movements_quantity_positive_unless_adjustment",
        }
        fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"])
            for fk in insp.get_foreign_keys("stock_movements")
        }
        assert fks == {
            (("product_id",), "products"),
            (("from_location_id",), "locations"),
            (("to_location_id",), "locations"),
            (("performed_by",), "users"),
        }

    inspect_url(url, check)
    command.check(cfg)  # models and migrations agree


def test_migration_0008_downgrade(sqlite_migration_db) -> None:
    cfg, url = sqlite_migration_db
    command.upgrade(cfg, "0008")
    command.downgrade(cfg, "0007")

    tables = inspect_url(url, lambda i: set(i.get_table_names()))
    assert not {"stock", "stock_movements"} & tables
    assert {"products", "locations", "users"} <= tables  # master data untouched

    command.upgrade(cfg, "0008")  # re-applies cleanly after a downgrade


@pytest.mark.skipif(not PG_URL, reason="needs a disposable PostgreSQL database")
def test_migration_0008_round_trip_on_postgresql(pg_engine, monkeypatch) -> None:
    """pg_engine has already upgraded the database to head (and cleans up)."""
    cfg = alembic_config(PG_URL, monkeypatch)
    enum_exists = text("SELECT 1 FROM pg_type WHERE typname = 'movement_type'")
    try:
        command.check(cfg)
        with pg_engine.connect() as connection:
            assert connection.scalar(enum_exists) == 1
            quantity = {c["name"]: c for c in inspect(connection).get_columns("stock")}["quantity"]
            assert (quantity["type"].precision, quantity["type"].scale) == (14, 3)

        command.downgrade(cfg, "0007")
        with pg_engine.connect() as connection:
            assert connection.scalar(enum_exists) is None  # enum type dropped too
            assert not {"stock", "stock_movements"} & set(inspect(connection).get_table_names())
    finally:
        command.upgrade(cfg, "head")  # leave the database as pg_engine expects
        get_settings.cache_clear()
