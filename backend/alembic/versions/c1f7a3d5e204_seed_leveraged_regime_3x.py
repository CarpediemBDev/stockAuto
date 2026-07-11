"""seed_leveraged_regime_3x

TQQQ 3x 공격형 자율 전략 식별자를 strategies 테이블에 시딩합니다.
(2026-07-09 관찰 전용 계정 3종 재편 — 월 30% 2차 목표 도전 슬리브)

Revision ID: c1f7a3d5e204
Revises: b8e4f6a2c913
Create Date: 2026-07-09 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f7a3d5e204'
down_revision: Union[str, None] = 'b8e4f6a2c913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_ROWS = (
    ("leveraged_regime_3x", "지수 레버리지 레짐 3x (TQQQ 3x + SMA200)", "Leveraged Regime 3x (TQQQ 3x + SMA200)"),
)


def upgrade() -> None:
    for strategy_type, name_ko, name_en in _SEED_ROWS:
        op.execute(
            sa.text(
                "INSERT INTO strategies (strategy_type, name_ko, name_en, is_active) "
                "SELECT :st, :ko, :en, 1 "
                "WHERE NOT EXISTS (SELECT 1 FROM strategies WHERE strategy_type = :st)"
            ).bindparams(st=strategy_type, ko=name_ko, en=name_en)
        )


def downgrade() -> None:
    for strategy_type, _, _ in _SEED_ROWS:
        op.execute(
            sa.text("DELETE FROM strategies WHERE strategy_type = :st").bindparams(st=strategy_type)
        )
