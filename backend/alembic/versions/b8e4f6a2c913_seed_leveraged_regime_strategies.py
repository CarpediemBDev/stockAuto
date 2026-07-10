"""seed_leveraged_regime_strategies

지수 레버리지 레짐(코어), QQQ 단순보유 벤치마크, 코어-새틀라이트 슬롯 모드 식별자를
strategies 테이블에 시딩합니다. (2026-07-09 코어-새틀라이트 라이브 시뮬레이션 배선)

Revision ID: b8e4f6a2c913
Revises: d6eba4e1ec31
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e4f6a2c913'
down_revision: Union[str, None] = 'd6eba4e1ec31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_ROWS = (
    ("leveraged_regime", "지수 레버리지 레짐 (QLD 2x + SMA200)", "Leveraged Regime (QLD 2x + SMA200)"),
    ("benchmark_qqq_hold", "QQQ 단순보유 벤치마크", "Benchmark QQQ Buy & Hold"),
    ("core_satellite", "코어-새틀라이트 (레버리지 레짐 70% + 전략C 30%)", "Core-Satellite (Leveraged Regime 70% + Strategy C 30%)"),
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
