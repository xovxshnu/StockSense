"""create reorder rules

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reorder_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("reorder_level", sa.Integer(), nullable=False),
        sa.Column("reorder_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reorder_level >= 0", name=op.f("ck_reorder_rules_reorder_level_non_negative")
        ),
        sa.CheckConstraint(
            "reorder_quantity > 0", name=op.f("ck_reorder_rules_reorder_quantity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_reorder_rules_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reorder_rules")),
        sa.UniqueConstraint("product_id", name=op.f("uq_reorder_rules_product_id")),
    )


def downgrade() -> None:
    op.drop_table("reorder_rules")
