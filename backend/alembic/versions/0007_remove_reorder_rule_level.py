"""remove reorder_rules.reorder_level

Product.reorder_level is the single low-stock threshold; a reorder rule now only
carries the replenishment quantity.

Upgrade DROPS the column, discarding any per-rule threshold values (they are not
copied to products). Downgrade restores the column and refills it from the
rule's product (products.reorder_level), the closest faithful value.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# batch mode is a plain ALTER on PostgreSQL and a table rebuild on SQLite, which
# cannot drop a column that a CHECK constraint uses.


def upgrade() -> None:
    with op.batch_alter_table("reorder_rules") as batch:
        batch.drop_constraint(
            op.f("ck_reorder_rules_reorder_level_non_negative"), type_="check"
        )
        batch.drop_column("reorder_level")


def downgrade() -> None:
    with op.batch_alter_table("reorder_rules") as batch:
        batch.add_column(sa.Column("reorder_level", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE reorder_rules SET reorder_level = "
        "(SELECT products.reorder_level FROM products WHERE products.id = reorder_rules.product_id)"
    )
    with op.batch_alter_table("reorder_rules") as batch:
        batch.alter_column("reorder_level", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint(
            op.f("ck_reorder_rules_reorder_level_non_negative"), "reorder_level >= 0"
        )
