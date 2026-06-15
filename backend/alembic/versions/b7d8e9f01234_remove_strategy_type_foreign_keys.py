"""remove_strategy_type_foreign_keys

Revision ID: b7d8e9f01234
Revises: 9a6c7d8e1f20
Create Date: 2026-06-15 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b7d8e9f01234"
down_revision: Union[str, None] = "9a6c7d8e1f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STRATEGY_FOREIGN_KEYS = (
    ("broker_orders", "fk_broker_orders_strategy_type"),
    ("holdings", "fk_holdings_strategy_type"),
    ("trade_logs", "fk_trade_logs_strategy_type"),
    ("user_settings", "fk_user_settings_strategy_type"),
)


def upgrade() -> None:
    for table_name, constraint_name in STRATEGY_FOREIGN_KEYS:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")


def downgrade() -> None:
    for table_name, constraint_name in STRATEGY_FOREIGN_KEYS:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                "strategies",
                ["strategy_type"],
                ["strategy_type"],
                onupdate="CASCADE",
            )
