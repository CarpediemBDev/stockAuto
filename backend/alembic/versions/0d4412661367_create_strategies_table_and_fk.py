"""create_strategies_table

Revision ID: 0d4412661367
Revises: cc508504ea6c
Create Date: 2026-06-15 21:37:05.554127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0d4412661367"
down_revision: Union[str, None] = "cc508504ea6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("strategy_type", sa.String(), nullable=False),
        sa.Column("name_ko", sa.String(), nullable=False),
        sa.Column("name_en", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("strategy_type"),
    )
    op.create_index(
        op.f("ix_strategies_strategy_type"),
        "strategies",
        ["strategy_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_strategies_strategy_type"), table_name="strategies")
    op.drop_table("strategies")
