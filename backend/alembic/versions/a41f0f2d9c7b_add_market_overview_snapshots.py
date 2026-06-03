"""add_market_overview_snapshots

Revision ID: a41f0f2d9c7b
Revises: 908b777e8294
Create Date: 2026-06-03 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a41f0f2d9c7b"
down_revision: Union[str, None] = "908b777e8294"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_overview_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "market_condition",
            sa.String(),
            nullable=False,
            comment="QQQ 기반 시장 상태: BULLISH, BEARISH, NEUTRAL",
        ),
        sa.Column(
            "market_condition_sync_status",
            sa.String(),
            nullable=False,
            comment="시장 상태 동기화 상태: fresh, stale, failed, skipped",
        ),
        sa.Column("nasdaq_symbol", sa.String(), nullable=False, comment="NASDAQ 종합지수 Yahoo Finance 티커"),
        sa.Column("nasdaq_current", sa.Float(), nullable=True, comment="NASDAQ 종합지수 현재값"),
        sa.Column("nasdaq_change", sa.Float(), nullable=True, comment="NASDAQ 종합지수 전일 대비 등락폭"),
        sa.Column("nasdaq_change_pct", sa.Float(), nullable=True, comment="NASDAQ 종합지수 전일 대비 등락률"),
        sa.Column(
            "nasdaq_sync_status",
            sa.String(),
            nullable=False,
            comment="NASDAQ 데이터 동기화 상태: fresh, stale, failed, skipped",
        ),
        sa.Column("exchange_rate_symbol", sa.String(), nullable=False, comment="USD/KRW Yahoo Finance 티커"),
        sa.Column("exchange_rate_current", sa.Float(), nullable=True, comment="USD/KRW 현재 환율"),
        sa.Column("exchange_rate_change", sa.Float(), nullable=True, comment="USD/KRW 전일 대비 변화폭"),
        sa.Column("exchange_rate_change_pct", sa.Float(), nullable=True, comment="USD/KRW 전일 대비 변화율"),
        sa.Column(
            "exchange_rate_sync_status",
            sa.String(),
            nullable=False,
            comment="USD/KRW 데이터 동기화 상태: fresh, stale, failed, skipped",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True, comment="스냅샷 생성 시각"),
        sa.PrimaryKeyConstraint("id"),
        comment="시장 개요 API가 즉시 반환할 수 있도록 저장하는 최신 시장 상태, NASDAQ, USD/KRW 스냅샷",
    )
    op.create_index(op.f("ix_market_overview_snapshots_created_at"), "market_overview_snapshots", ["created_at"], unique=False)
    op.create_index(op.f("ix_market_overview_snapshots_id"), "market_overview_snapshots", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_market_overview_snapshots_id"), table_name="market_overview_snapshots")
    op.drop_index(op.f("ix_market_overview_snapshots_created_at"), table_name="market_overview_snapshots")
    op.drop_table("market_overview_snapshots")
