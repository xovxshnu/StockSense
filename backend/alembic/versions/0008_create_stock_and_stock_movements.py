"""create stock and stock movements

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column(
            "quantity", sa.Numeric(precision=14, scale=3), server_default="0", nullable=False
        ),
        sa.Column(
            "reserved_quantity",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
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
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_stock_quantity_non_negative")),
        sa.CheckConstraint(
            "reserved_quantity >= 0", name=op.f("ck_stock_reserved_quantity_non_negative")
        ),
        sa.CheckConstraint(
            "reserved_quantity <= quantity", name=op.f("ck_stock_reserved_not_above_quantity")
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_stock_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock")),
        sa.UniqueConstraint(
            "product_id", "location_id", name=op.f("uq_stock_product_id_location_id")
        ),
    )
    op.create_index(op.f("ix_stock_location_id"), "stock", ["location_id"])

    # On PostgreSQL this creates the native `movement_type` enum type.
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column(
            "movement_type",
            sa.Enum(
                "IN", "OUT", "TRANSFER", "ADJUSTMENT", name="movement_type", create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("from_location_id", sa.Integer(), nullable=True),
        sa.Column("to_location_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("performed_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "movement_type != 'IN' OR (from_location_id IS NULL AND to_location_id IS NOT NULL)",
            name=op.f("ck_stock_movements_in_locations"),
        ),
        sa.CheckConstraint(
            "movement_type != 'OUT' OR (from_location_id IS NOT NULL AND to_location_id IS NULL)",
            name=op.f("ck_stock_movements_out_locations"),
        ),
        sa.CheckConstraint(
            "movement_type != 'TRANSFER' OR (from_location_id IS NOT NULL"
            " AND to_location_id IS NOT NULL AND from_location_id != to_location_id)",
            name=op.f("ck_stock_movements_transfer_locations"),
        ),
        sa.CheckConstraint(
            "movement_type != 'ADJUSTMENT'"
            " OR (from_location_id IS NULL AND to_location_id IS NOT NULL)",
            name=op.f("ck_stock_movements_adjustment_locations"),
        ),
        sa.CheckConstraint("quantity != 0", name=op.f("ck_stock_movements_quantity_not_zero")),
        sa.CheckConstraint(
            "movement_type = 'ADJUSTMENT' OR quantity > 0",
            name=op.f("ck_stock_movements_quantity_positive_unless_adjustment"),
        ),
        sa.CheckConstraint(
            "length(trim(reference)) > 0", name=op.f("ck_stock_movements_reference_not_blank")
        ),
        sa.CheckConstraint(
            "length(trim(source_type)) > 0",
            name=op.f("ck_stock_movements_source_type_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["from_location_id"],
            ["locations.id"],
            name=op.f("fk_stock_movements_from_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"],
            ["users.id"],
            name=op.f("fk_stock_movements_performed_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_movements_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_location_id"],
            ["locations.id"],
            name=op.f("fk_stock_movements_to_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    op.create_index(
        op.f("ix_stock_movements_created_at"), "stock_movements", ["created_at"]
    )
    op.create_index(
        op.f("ix_stock_movements_from_location_id"), "stock_movements", ["from_location_id"]
    )
    op.create_index(
        op.f("ix_stock_movements_movement_type"), "stock_movements", ["movement_type"]
    )
    op.create_index(op.f("ix_stock_movements_product_id"), "stock_movements", ["product_id"])
    op.create_index(op.f("ix_stock_movements_reference"), "stock_movements", ["reference"])
    op.create_index(
        op.f("ix_stock_movements_to_location_id"), "stock_movements", ["to_location_id"]
    )


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints with it.
    op.drop_table("stock_movements")
    sa.Enum(name="movement_type").drop(op.get_bind(), checkfirst=True)
    op.drop_table("stock")
