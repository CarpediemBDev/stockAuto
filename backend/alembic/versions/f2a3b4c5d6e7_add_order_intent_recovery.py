"""add order intent recovery

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.add_column(sa.Column("intent_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("exchange_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("order_division", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("source", sa.String(), server_default="STRATEGY", nullable=False)
        )
        batch_op.add_column(
            sa.Column("submission_attempts", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("discovery_attempts", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("submission_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("response_received_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_discovery_at", sa.DateTime(), nullable=True))
        batch_op.alter_column(
            "broker_order_no",
            existing_type=sa.String(),
            nullable=True,
        )

    op.execute("UPDATE broker_orders SET intent_id = 'legacy-' || id WHERE intent_id IS NULL")

    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.alter_column("intent_id", existing_type=sa.String(), nullable=False)
        batch_op.create_index("ix_broker_orders_intent_id", ["intent_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.drop_index("ix_broker_orders_intent_id")
        batch_op.alter_column(
            "broker_order_no",
            existing_type=sa.String(),
            nullable=False,
        )
        batch_op.drop_column("last_discovery_at")
        batch_op.drop_column("response_received_at")
        batch_op.drop_column("submission_started_at")
        batch_op.drop_column("discovery_attempts")
        batch_op.drop_column("submission_attempts")
        batch_op.drop_column("source")
        batch_op.drop_column("order_division")
        batch_op.drop_column("exchange_code")
        batch_op.drop_column("intent_id")
