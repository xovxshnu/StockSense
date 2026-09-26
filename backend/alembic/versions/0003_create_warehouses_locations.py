"""create warehouses and locations

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("short_code", sa.String(length=20), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_warehouses_name_not_blank")),
        sa.CheckConstraint(
            "length(trim(short_code)) > 0", name=op.f("ck_warehouses_short_code_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouses")),
        sa.UniqueConstraint("short_code", name=op.f("uq_warehouses_short_code")),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("short_code", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_locations_name_not_blank")),
        sa.CheckConstraint(
            "length(trim(short_code)) > 0", name=op.f("ck_locations_short_code_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name=op.f("fk_locations_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint(
            "warehouse_id", "short_code", name=op.f("uq_locations_warehouse_id_short_code")
        ),
    )


def downgrade() -> None:
    # Locations reference warehouses, so they go first.
    op.drop_table("locations")
    op.drop_table("warehouses")
