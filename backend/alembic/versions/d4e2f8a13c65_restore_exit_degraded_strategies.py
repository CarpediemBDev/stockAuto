"""restore_exit_degraded_strategies

c8d1e5f20b74가 내린 3종(asqs, macro_momentum, strategy_c)의 is_selectable을 되돌린다.

철회 사유 - c8d1e5f20b74는 "청산 경로가 결손이면 시그널 청산이 불가능하다"는 전제로
카탈로그에서 3종을 내렸는데, 2026-08-31 실측에서 그 전제가 거짓임이 확인됐다.

  - 청산 로그 20,532건 중 91%가 시그널 붕괴다. 손절 5.5%, 트레일링 1.3%.
  - 대상 전략일수록 오히려 시그널 청산 비중이 높다. asqs는 청산 2,346건 중
    2,276건(97%)이 시그널 붕괴이고 손절은 0건이다.
  - 3종 모두 청산 점수가 가격에 정상 반응한다. 횡보·하락 입력에서 cutoff 아래로
    떨어져 붕괴 판정이 난다.
  - 보유 포지션 나이가 다른 전략과 같은 3.1일이라 빠져나오지 못한 포지션도 없었다.

결손 필드는 게이트가 아니라 가점·감점이거나 OR 항의 하나였다. strategy_c의
news_sentiment는 기본값이 'NEUTRAL'이라 결손 시 가점도 감점도 없는 의도된 안전
기본값이고, asqs의 is_float_rotation은 3항 OR의 하나이며 진입 분기에서만 쓰인다.

주의 - 이 마이그레이션은 c8d1e5f20b74 이전 상태(is_selectable=1)로 되돌린다.
그보다 앞선 b7c3d9e14a20이 내린 22종은 근거가 다르므로(외부 데이터 부재로 진입
자체가 불가능) 건드리지 않는다.

Revision ID: d4e2f8a13c65
Revises: c8d1e5f20b74
Create Date: 2026-08-31 03:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e2f8a13c65'
down_revision: Union[str, None] = 'c8d1e5f20b74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# c8d1e5f20b74가 내린 전략. 되돌림 대상은 정확히 이 3종뿐이다.
RESTORED_STRATEGIES = ('asqs', 'macro_momentum', 'strategy_c')


def _set_selectable(value: int) -> None:
    """대상 전략의 is_selectable을 일괄 갱신한다.

    SQL은 반드시 sa.text()와 바인드 파라미터로 조립한다. f-string으로 전략명을
    끼워 넣으면 scripts/check_migration_safety.py의 R1 규칙에 반려된다.
    """
    stmt = sa.text(
        "UPDATE strategies SET is_selectable=:value WHERE strategy_type=:strategy_type"
    )
    connection = op.get_bind()
    for strategy_type in RESTORED_STRATEGIES:
        connection.execute(stmt, {"value": value, "strategy_type": strategy_type})


def upgrade() -> None:
    _set_selectable(1)


def downgrade() -> None:
    _set_selectable(0)
