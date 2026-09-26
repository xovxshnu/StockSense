"""create adjustments and adjustment lines

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On PostgreSQL this creates the native `adjustment_status` enum type.
    op.create_table(
        "adjustments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "DONE", name="adjustment_status", create_constraint=True),
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
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_adjustments_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
            name=op.f("fk_adjustments_responsible_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adjustments")),
        sa.UniqueConstraint("reference", name=op.f("uq_adjustments_reference")),
    )
    op.create_index(op.f("ix_adjustments_location_id"), "adjustments", ["location_id"])
    op.create_index(op.f("ix_adjustments_status"), "adjustments", ["status"])

    op.create_table(
        "adjustment_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("adjustment_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("system_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("difference", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.CheckConstraint(
            "counted_quantity >= 0",
            name=op.f("ck_adjustment_lines_counted_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "system_quantity >= 0", name=op.f("ck_adjustment_lines_system_quantity_non_negative")
        ),
        sa.CheckConstraint(
            "difference = counted_quantity - system_quantity",
            name=op.f("ck_adjustment_lines_difference_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["adjustment_id"],
            ["adjustments.id"],
            name=op.f("fk_adjustment_lines_adjustment_id_adjustments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_adjustment_lines_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adjustment_lines")),
        sa.UniqueConstraint(
            "adjustment_id",
            "product_id",
            name=op.f("uq_adjustment_lines_adjustment_id_product_id"),
        ),
    )
    op.create_index(op.f("ix_adjustment_lines_product_id"), "adjustment_lines", ["product_id"])


def downgrade() -> None:
    # Lines reference adjustments, so they go first; indexes go with their tables.
    op.drop_table("adjustment_lines")
    op.drop_table("adjustments")
    sa.Enum(name="adjustment_status").drop(op.get_bind(), checkfirst=True)
