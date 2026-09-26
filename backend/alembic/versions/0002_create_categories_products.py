"""create categories and products

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name=op.f("ck_categories_name_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    # Case-insensitive uniqueness of category names.
    op.create_index(
        "uq_categories_name_lower", "categories", [sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("uom", sa.String(length=20), server_default="Unit", nullable=False),
        sa.Column(
            "unit_cost", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False
        ),
        sa.Column("reorder_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_products_name_not_blank")),
        sa.CheckConstraint("length(trim(sku)) > 0", name=op.f("ck_products_sku_not_blank")),
        sa.CheckConstraint("unit_cost >= 0", name=op.f("ck_products_unit_cost_non_negative")),
        sa.CheckConstraint(
            "reorder_level >= 0", name=op.f("ck_products_reorder_level_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_products_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
    )
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_table("products")
    op.drop_index("uq_categories_name_lower", table_name="categories")
    op.drop_table("categories")
