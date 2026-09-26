"""Backend-owned reference numbers such as WH/IN/0001.

Generic infrastructure: it knows only about the `document_sequences` table. It
must not depend on Stock, Product, Location or the Inventory Engine, and there is
deliberately no public API for it; future operation services call it.

Concurrency
-----------
`generate_reference` issues ONE atomic statement,

    INSERT INTO document_sequences (prefix, last_number) VALUES (:prefix, 1)
    ON CONFLICT (prefix) DO UPDATE SET last_number = document_sequences.last_number + 1
    RETURNING last_number

so there is no read-then-write gap. The unique constraint on `prefix` makes the
first-use insert race safe, and on PostgreSQL the conflicting UPDATE locks the
row and re-reads the latest value, so two transactions can never receive the
same number.

Transactions
------------
The function only *participates* in the caller's transaction: it never commits or
rolls back. Callers must generate the reference and create the document in the
same transaction:

    reference = generate_reference(db, "WH/IN")
    db.add(Receipt(reference=reference, ...))
    db.commit()

Consequences of that design:
* Numbers are gapless: if the caller rolls back, the increment is rolled back too
  and the number is issued again.
* The row lock is held until the caller's transaction ends, so concurrent
  transactions using the SAME prefix are serialized (different prefixes are not).
  Keep the surrounding transaction short.
"""

from sqlalchemy.orm import Session

from app.models.document_sequence import DocumentSequence
from app.services.errors import InvalidPrefixError

# Registered prefixes. To add a document type later, add its prefix here; the
# mechanism itself needs no change.
ALLOWED_PREFIXES: frozenset[str] = frozenset({"WH/IN", "WH/OUT", "WH/INT", "WH/ADJ"})

MIN_DIGITS = 4  # minimum width only: 9999 -> 10000 is not truncated or wrapped


def _upsert_increment(db: Session):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif dialect == "sqlite":  # used by the unit tests
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        raise RuntimeError(f"Unsupported database dialect for sequences: {dialect}")
    return dialect_insert


def generate_reference(db: Session, prefix: str) -> str:
    """Return the next reference for `prefix`, e.g. "WH/IN/0001".

    Raises InvalidPrefixError for an unregistered prefix. Does not commit.
    """
    if prefix not in ALLOWED_PREFIXES:
        raise InvalidPrefixError(f"Unknown reference prefix: {prefix!r}")

    dialect_insert = _upsert_increment(db)
    statement = (
        dialect_insert(DocumentSequence)
        .values(prefix=prefix, last_number=1)
        .on_conflict_do_update(
            index_elements=[DocumentSequence.prefix],
            set_={"last_number": DocumentSequence.last_number + 1},
        )
        .returning(DocumentSequence.last_number)
    )
    number = db.execute(statement).scalar_one()
    return f"{prefix}/{number:0{MIN_DIGITS}d}"
