"""add_swing_prediction_snapshots

Revision ID: b7c8d9e0f1a2
Revises: a41f0f2d9c7b
Create Date: 2026-06-03 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a41f0f2d9c7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "swing_prediction_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "cache_key",
            sa.String(),
            nullable=False,
            comment="기본 스윙 풀과 사용자 관심종목을 정렬해 결합한 캐시 식별자",
        ),
        sa.Column("ticker_universe", sa.Text(), nullable=False, comment="분석 대상 티커 목록 JSON 배열"),
        sa.Column("candidates_json", sa.Text(), nullable=False, comment="스윙 예측 후보 결과 JSON 배열"),
        sa.Column(
            "sync_status",
            sa.String(),
            nullable=False,
            comment="스윙 예측 동기화 상태: fresh, stale, refreshing, failed, empty",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True, comment="스냅샷 생성 시각"),
        sa.PrimaryKeyConstraint("id"),
        comment="스윙 예측 폴링 API가 대량 yfinance 분석 없이 즉시 반환할 수 있도록 저장하는 후보 스냅샷",
    )
    op.create_index(op.f("ix_swing_prediction_snapshots_cache_key"), "swing_prediction_snapshots", ["cache_key"], unique=False)
    op.create_index(op.f("ix_swing_prediction_snapshots_created_at"), "swing_prediction_snapshots", ["created_at"], unique=False)
    op.create_index(op.f("ix_swing_prediction_snapshots_id"), "swing_prediction_snapshots", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_swing_prediction_snapshots_id"), table_name="swing_prediction_snapshots")
    op.drop_index(op.f("ix_swing_prediction_snapshots_created_at"), table_name="swing_prediction_snapshots")
    op.drop_index(op.f("ix_swing_prediction_snapshots_cache_key"), table_name="swing_prediction_snapshots")
    op.drop_table("swing_prediction_snapshots")
