"""Add broker provider provenance to holdings and broker orders.

Revision ID: 5b6c7d8e9f0a
Revises: 4a5b6c7d8e9f
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5b6c7d8e9f0a"
down_revision: Union[str, None] = "4a5b6c7d8e9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.add_column(sa.Column("broker_provider", sa.String(), nullable=True))
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.add_column(sa.Column("broker_provider", sa.String(), nullable=True))

    # 과거 코드는 같은 거래 모드에서 증권사 변경을 허용했으므로
    # 기존 원장의 출처를 현재 UserSettings로 역추론하지 않습니다.
    # legacy NULL은 자동 주문·재조정 대상에서 fail-closed 처리됩니다.
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.drop_constraint("_user_broker_order_uc", type_="unique")
        batch_op.create_unique_constraint(
            "_user_provider_broker_order_uc",
            ["user_id", "broker_provider", "broker_order_no"],
        )


def downgrade() -> None:
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.drop_constraint(
            "_user_provider_broker_order_uc",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "_user_broker_order_uc",
            ["user_id", "broker_order_no"],
        )
        batch_op.drop_column("broker_provider")
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.drop_column("broker_provider")
