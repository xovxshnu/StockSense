import ast
import os
import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, DocumentSequence
from app.services import sequence_service
from app.services.errors import InvalidPrefixError
from app.services.sequence_service import ALLOWED_PREFIXES, generate_reference


def test_first_reference_for_each_allowed_prefix(db: Session) -> None:
    for prefix in ("WH/IN", "WH/OUT", "WH/INT", "WH/ADJ"):
        assert generate_reference(db, prefix) == f"{prefix}/0001"


def test_allowed_prefixes() -> None:
    assert ALLOWED_PREFIXES == {"WH/IN", "WH/OUT", "WH/INT", "WH/ADJ"}


def test_second_reference_increments(db: Session) -> None:
    assert generate_reference(db, "WH/IN") == "WH/IN/0001"
    assert generate_reference(db, "WH/IN") == "WH/IN/0002"


def test_counters_are_independent_per_prefix(db: Session) -> None:
    generate_reference(db, "WH/IN")
    generate_reference(db, "WH/IN")
    assert generate_reference(db, "WH/OUT") == "WH/OUT/0001"
    assert generate_reference(db, "WH/IN") == "WH/IN/0003"
    assert generate_reference(db, "WH/OUT") == "WH/OUT/0002"


@pytest.mark.parametrize(
    "last, expected",
    [
        (0, "WH/IN/0001"),
        (9, "WH/IN/0010"),
        (98, "WH/IN/0099"),
        (999, "WH/IN/1000"),
        (1000, "WH/IN/1001"),
        (9998, "WH/IN/9999"),
        (9999, "WH/IN/10000"),  # padding is a minimum width: no truncation or wrap
        (10000, "WH/IN/10001"),
    ],
)
def test_padding_and_values_above_9999(db: Session, last: int, expected: str) -> None:
    db.add(DocumentSequence(prefix="WH/IN", last_number=last))
    db.flush()
    assert generate_reference(db, "WH/IN") == expected


@pytest.mark.parametrize("prefix", ["", "WH", "wh/in", "WH/IN/", "WH/IN/0001", "WH/RCV", " WH/IN", None])
def test_invalid_prefix_rejected(db: Session, prefix) -> None:
    with pytest.raises(InvalidPrefixError):
        generate_reference(db, prefix)
    assert db.scalar(select(DocumentSequence.id)) is None  # nothing was created


def test_invalid_prefix_error_is_a_value_error() -> None:
    assert issubclass(InvalidPrefixError, ValueError)


def test_sequence_row_is_persisted(db: Session) -> None:
    generate_reference(db, "WH/IN")
    generate_reference(db, "WH/IN")
    generate_reference(db, "WH/OUT")
    db.commit()
    rows = {r.prefix: r.last_number for r in db.scalars(select(DocumentSequence))}
    assert rows == {"WH/IN": 2, "WH/OUT": 1}


def test_generation_does_not_commit(db: Session) -> None:
    generate_reference(db, "WH/IN")
    assert db.in_transaction()
    db.rollback()
    assert db.scalar(select(DocumentSequence.id)) is None


def test_rollback_reissues_the_number(db: Session) -> None:
    """Numbers are gapless: a rolled-back caller does not consume a number."""
    assert generate_reference(db, "WH/IN") == "WH/IN/0001"
    db.commit()
    assert generate_reference(db, "WH/IN") == "WH/IN/0002"
    db.rollback()
    assert generate_reference(db, "WH/IN") == "WH/IN/0002"


def test_committed_number_is_never_reissued(db: Session) -> None:
    generate_reference(db, "WH/IN")
    db.commit()
    db.rollback()
    assert generate_reference(db, "WH/IN") == "WH/IN/0002"


def test_repeated_generation_is_unique(db: Session) -> None:
    references = [generate_reference(db, "WH/ADJ") for _ in range(200)]
    assert len(set(references)) == 200
    assert references[0] == "WH/ADJ/0001" and references[-1] == "WH/ADJ/0200"


def test_exact_sequence_table_fields() -> None:
    assert {c.key for c in inspect(DocumentSequence).columns} == {"id", "prefix", "last_number"}
    assert DocumentSequence.__tablename__ == "document_sequences"


def test_db_enforces_unique_prefix(db: Session) -> None:
    db.add(DocumentSequence(prefix="WH/IN"))
    db.commit()
    db.add(DocumentSequence(prefix="WH/IN"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_enforces_non_negative_last_number(db: Session) -> None:
    db.add(DocumentSequence(prefix="WH/IN", last_number=-1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_last_number_defaults_to_zero(db: Session) -> None:
    db.add(DocumentSequence(prefix="WH/IN"))
    db.commit()
    assert db.scalar(select(DocumentSequence.last_number)) == 0


def test_no_public_sequence_api(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if "sequence" in p]


def test_sequence_service_is_independent_of_inventory_and_master_data() -> None:
    source = Path(sequence_service.__file__).read_text()
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    app_imports = {m for m in imported if m.startswith("app.")}
    assert app_imports == {"app.models.document_sequence", "app.services.errors"}


# --- Real-PostgreSQL concurrency test -------------------------------------
# SQLite serializes all writers, so it cannot demonstrate row-lock safety and no
# claim is made from it. This test only runs when TEST_POSTGRES_URL points at a
# disposable PostgreSQL database (e.g. postgresql+psycopg://user:pw@localhost/scratch).


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"), reason="needs a disposable PostgreSQL database"
)
def test_concurrent_generation_is_unique_on_postgresql() -> None:
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    table = [DocumentSequence.__table__]
    Base.metadata.drop_all(engine, tables=table)
    Base.metadata.create_all(engine, tables=table)
    factory = sessionmaker(bind=engine)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(10):
            with factory() as session:
                reference = generate_reference(session, "WH/IN")
                session.commit()
            with lock:
                results.append(reference)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    Base.metadata.drop_all(engine, tables=table)
    assert len(results) == 80 and len(set(results)) == 80
    assert set(results) == {f"WH/IN/{n:04d}" for n in range(1, 81)}
