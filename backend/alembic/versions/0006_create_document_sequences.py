"""create document sequences

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prefix", sa.String(length=50), nullable=False),
        sa.Column("last_number", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_document_sequences_last_number_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sequences")),
        sa.UniqueConstraint("prefix", name=op.f("uq_document_sequences_prefix")),
    )


def downgrade() -> None:
    op.drop_table("document_sequences")
