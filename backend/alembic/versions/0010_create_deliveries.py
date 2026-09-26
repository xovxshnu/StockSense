"""create deliveries and delivery lines

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On PostgreSQL this creates the native `delivery_status` enum type.
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("source_location_id", sa.Integer(), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "WAITING",
                "READY",
                "DONE",
                "CANCELED",
                name="delivery_status",
                create_constraint=True,
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
            ["customer_id"],
            ["contacts.id"],
            name=op.f("fk_deliveries_customer_id_contacts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
            name=op.f("fk_deliveries_responsible_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_location_id"],
            ["locations.id"],
            name=op.f("fk_deliveries_source_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name=op.f("fk_deliveries_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
        sa.UniqueConstraint("reference", name=op.f("uq_deliveries_reference")),
    )
    op.create_index(op.f("ix_deliveries_customer_id"), "deliveries", ["customer_id"])
    op.create_index(
        op.f("ix_deliveries_source_location_id"), "deliveries", ["source_location_id"]
    )
    op.create_index(op.f("ix_deliveries_status"), "deliveries", ["status"])
    op.create_index(op.f("ix_deliveries_warehouse_id"), "deliveries", ["warehouse_id"])

    op.create_table(
        "delivery_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_delivery_lines_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["deliveries.id"],
            name=op.f("fk_delivery_lines_delivery_id_deliveries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_delivery_lines_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_lines")),
        sa.UniqueConstraint(
            "delivery_id", "product_id", name=op.f("uq_delivery_lines_delivery_id_product_id")
        ),
    )
    op.create_index(op.f("ix_delivery_lines_product_id"), "delivery_lines", ["product_id"])


def downgrade() -> None:
    # Lines reference deliveries, so they go first; indexes go with their tables.
    op.drop_table("delivery_lines")
    op.drop_table("deliveries")
    sa.Enum(name="delivery_status").drop(op.get_bind(), checkfirst=True)
