"""add broker orders

Revision ID: e1f2a3b4c5d6
Revises: bd07f17fb172
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "bd07f17fb172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("broker_order_no", sa.String(), nullable=False),
        sa.Column("broker_order_date", sa.String(), nullable=False),
        sa.Column("trade_mode", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("prefixed_ticker", sa.String(), nullable=False),
        sa.Column("ticker_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="SUBMITTED", nullable=False),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("broker_filled_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_filled_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("submitted_price", sa.Float(), nullable=False),
        sa.Column("filled_price", sa.Float(), nullable=True),
        sa.Column("buy_stage", sa.Integer(), nullable=True),
        sa.Column("regime_mode", sa.String(), nullable=True),
        sa.Column("signal_score", sa.Integer(), nullable=True),
        sa.Column("sell_reason", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resume_after_resolution", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_alerted_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "broker_order_no", name="_user_broker_order_uc"),
    )
    op.create_index(op.f("ix_broker_orders_id"), "broker_orders", ["id"], unique=False)
    op.create_index(op.f("ix_broker_orders_user_id"), "broker_orders", ["user_id"], unique=False)
    op.create_index("ix_broker_orders_user_status", "broker_orders", ["user_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_broker_orders_user_status", table_name="broker_orders")
    op.drop_index(op.f("ix_broker_orders_user_id"), table_name="broker_orders")
    op.drop_index(op.f("ix_broker_orders_id"), table_name="broker_orders")
    op.drop_table("broker_orders")
