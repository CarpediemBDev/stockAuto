"""Holding.last_price 및 AccountEquitySnapshot.profit_loss 컬럼 추가.

유저 대면 잔고 API에서 외부 네트워크 호출을 제거하기 위해
스케줄러가 관측한 현재가(last_price, USD)와 평가손익(profit_loss, KRW)을
DB에 영속화합니다.

Revision ID: 7a1b2c3d4e5f
Revises: 5342e2a95f25
Create Date: 2026-07-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a1b2c3d4e5f"
down_revision: Union[str, None] = "5342e2a95f25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "holdings",
        sa.Column("last_price", sa.Numeric(precision=20, scale=4), nullable=True),
    )
    op.add_column(
        "holdings",
        sa.Column("last_price_updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "account_equity_snapshots",
        sa.Column("profit_loss", sa.Numeric(precision=20, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_equity_snapshots", "profit_loss")
    op.drop_column("holdings", "last_price_updated_at")
    op.drop_column("holdings", "last_price")
