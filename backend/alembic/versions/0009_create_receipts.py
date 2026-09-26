"""create receipts and receipt lines

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On PostgreSQL this creates the native `receipt_status` enum type.
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("destination_location_id", sa.Integer(), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "READY", "DONE", "CANCELED", name="receipt_status", create_constraint=True
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
        sa.ForeignKeyConstraint(
            ["destination_location_id"],
            ["locations.id"],
            name=op.f("fk_receipts_destination_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
            name=op.f("fk_receipts_responsible_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["contacts.id"],
            name=op.f("fk_receipts_supplier_id_contacts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name=op.f("fk_receipts_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        sa.UniqueConstraint("reference", name=op.f("uq_receipts_reference")),
    )
    op.create_index(
        op.f("ix_receipts_destination_location_id"), "receipts", ["destination_location_id"]
    )
    op.create_index(op.f("ix_receipts_status"), "receipts", ["status"])
    op.create_index(op.f("ix_receipts_supplier_id"), "receipts", ["supplier_id"])
    op.create_index(op.f("ix_receipts_warehouse_id"), "receipts", ["warehouse_id"])

    op.create_table(
        "receipt_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_receipt_lines_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_receipt_lines_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["receipts.id"],
            name=op.f("fk_receipt_lines_receipt_id_receipts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipt_lines")),
        sa.UniqueConstraint(
            "receipt_id", "product_id", name=op.f("uq_receipt_lines_receipt_id_product_id")
        ),
    )
    op.create_index(op.f("ix_receipt_lines_product_id"), "receipt_lines", ["product_id"])


def downgrade() -> None:
    # Lines reference receipts, so they go first; indexes go with their tables.
    op.drop_table("receipt_lines")
    op.drop_table("receipts")
    sa.Enum(name="receipt_status").drop(op.get_bind(), checkfirst=True)
