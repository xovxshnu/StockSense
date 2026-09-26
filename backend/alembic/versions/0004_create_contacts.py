"""create contacts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On PostgreSQL this creates the native `contact_type` enum type.
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "type",
            sa.Enum("supplier", "customer", name="contact_type", create_constraint=True),
            nullable=False,
        ),
        sa.Column("address", sa.Text(), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_contacts_name_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )


def downgrade() -> None:
    op.drop_table("contacts")
    sa.Enum(name="contact_type").drop(op.get_bind(), checkfirst=True)
