"""add_account_equity_snapshots

Revision ID: 9a6c7d8e1f20
Revises: 0d4412661367
Create Date: 2026-06-15 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a6c7d8e1f20"
down_revision: Union[str, None] = "0d4412661367"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_equity_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("total_asset", sa.Float(), nullable=False),
        sa.Column("cash_balance", sa.Float(), nullable=True),
        sa.Column("stock_balance", sa.Float(), nullable=True),
        sa.Column("profit_rate", sa.Float(), nullable=True),
        sa.Column("fx_rate", sa.Float(), nullable=True),
        sa.Column("trade_mode", sa.String(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_equity_snapshots_id"),
        "account_equity_snapshots",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_equity_snapshots_user_id"),
        "account_equity_snapshots",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_equity_snapshots_captured_at"),
        "account_equity_snapshots",
        ["captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_account_equity_snapshots_captured_at"),
        table_name="account_equity_snapshots",
    )
    op.drop_index(
        op.f("ix_account_equity_snapshots_user_id"),
        table_name="account_equity_snapshots",
    )
    op.drop_index(
        op.f("ix_account_equity_snapshots_id"),
        table_name="account_equity_snapshots",
    )
    op.drop_table("account_equity_snapshots")
