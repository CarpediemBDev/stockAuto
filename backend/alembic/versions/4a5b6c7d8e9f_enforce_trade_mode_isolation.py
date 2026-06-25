"""Enforce trade mode isolation for holdings and trade logs.

Revision ID: 4a5b6c7d8e9f
Revises: 37240920731f
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op


revision: str = "4a5b6c7d8e9f"
down_revision: Union[str, None] = "37240920731f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 주문 원장과 연결 가능한 과거 체결만 실제 주문 모드로 복구합니다.
    # 연결할 수 없는 기존 행은 372 마이그레이션의 안전 기본값 SIMULATED를 보존합니다.
    op.execute(
        """
        UPDATE trade_logs
        SET trade_mode = (
            SELECT broker_orders.trade_mode
            FROM broker_orders
            WHERE broker_orders.user_id = trade_logs.user_id
              AND broker_orders.broker_order_no = trade_logs.order_no
            ORDER BY broker_orders.id DESC
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM broker_orders
            WHERE broker_orders.user_id = trade_logs.user_id
              AND broker_orders.broker_order_no = trade_logs.order_no
        )
        """
    )
    # 보유 원장은 주문 번호가 없어 안전하게 역추론할 수 없으므로 기존 모드를 그대로 보존합니다.
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.drop_constraint("_user_ticker_strategy_uc", type_="unique")
        batch_op.create_unique_constraint(
            "_user_ticker_strategy_mode_uc",
            ["user_id", "ticker", "strategy_type", "trade_mode"],
        )


def downgrade() -> None:
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.drop_constraint("_user_ticker_strategy_mode_uc", type_="unique")
        batch_op.create_unique_constraint(
            "_user_ticker_strategy_uc",
            ["user_id", "ticker", "strategy_type"],
        )
