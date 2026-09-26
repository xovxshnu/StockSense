"""create transfers and transfer lines

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On PostgreSQL this creates the native `transfer_status` enum type.
    op.create_table(
        "transfers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("from_location_id", sa.Integer(), nullable=False),
        sa.Column("to_location_id", sa.Integer(), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "READY", "DONE", "CANCELED", name="transfer_status", create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "from_location_id != to_location_id", name=op.f("ck_transfers_locations_differ")
        ),
        sa.ForeignKeyConstraint(
            ["from_location_id"],
            ["locations.id"],
            name=op.f("fk_transfers_from_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
            name=op.f("fk_transfers_responsible_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_location_id"],
            ["locations.id"],
            name=op.f("fk_transfers_to_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfers")),
        sa.UniqueConstraint("reference", name=op.f("uq_transfers_reference")),
    )
    op.create_index(op.f("ix_transfers_from_location_id"), "transfers", ["from_location_id"])
    op.create_index(op.f("ix_transfers_status"), "transfers", ["status"])
    op.create_index(op.f("ix_transfers_to_location_id"), "transfers", ["to_location_id"])

    op.create_table(
        "transfer_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transfer_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_transfer_lines_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_transfer_lines_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_id"],
            ["transfers.id"],
            name=op.f("fk_transfer_lines_transfer_id_transfers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_lines")),
        sa.UniqueConstraint(
            "transfer_id", "product_id", name=op.f("uq_transfer_lines_transfer_id_product_id")
        ),
    )
    op.create_index(op.f("ix_transfer_lines_product_id"), "transfer_lines", ["product_id"])


def downgrade() -> None:
    # Lines reference transfers, so they go first; indexes go with their tables.
    op.drop_table("transfer_lines")
    op.drop_table("transfers")
    sa.Enum(name="transfer_status").drop(op.get_bind(), checkfirst=True)
