"""block_exit_degraded_strategies

시그널 청산이 불가능한 전략 3종을 카탈로그에서 선택 불가로 내린다.

배경(2026-08-30 실측) - 진입 경로만 고치면 절반만 고친 것이다. 청산 조건이 결손
필드를 읽으면 BaseStrategy._safe_get이 0.0을 돌려주고 `close >= 기준선(0.0)`이 항상
참이 되어 홀딩 판정이 영구히 유지된다. 이 전략들은 포지션을 잡은 뒤 시그널로는 절대
빠져나오지 못하고 손절·트레일링으로만 정리된다.

  asqs           - is_float_rotation (유통주식수 데이터 없음)
  macro_momentum - yield_curve_spread, inflation_expectation (매크로 시계열 미연동)
  strategy_c     - news_sentiment, news_sentiment_score (뉴스 감성 중첩 누락)

선행 마이그레이션 b7c3d9e14a20은 '진입이 불가능한' 전략을 내렸다. 이번 건은 반대로
'진입은 되는데 청산이 죽은' 조합이라 그 그물에 걸리지 않았다.

중요 - is_selectable=0만으로는 신규 매수가 멈추지 않는다. 이 플래그는 카탈로그 조회
(app/strategy_catalog/router.py)와 전략 변경 검증(app/admin/router.py)에서만 쓰이고
스케줄러는 보지 않는다. 이미 해당 전략으로 설정된 계정은 계속 매수한다. 실제 차단은
app/bot/scheduler.py의 진입 채점 경로가 app/scanner/signal_contract.py의
ENTRY_BLOCKED_STRATEGY_SET을 보고 수행하며, 이 마이그레이션은 카탈로그 노출만 막는다.

is_active는 건드리지 않는다. 백테스트·연구 조회는 계속 가능해야 한다. 기존 보유분의
청산 경로(손절·트레일링·시그널)도 그대로 둔다 - 신규 진입만 막는 것이 의도다.

Revision ID: c8d1e5f20b74
Revises: b7c3d9e14a20
Create Date: 2026-08-30 07:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8d1e5f20b74'
down_revision: Union[str, None] = 'b7c3d9e14a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 청산 경로가 결손이라 시그널 청산이 불가능한 전략. 근거 필드를 함께 남긴다.
EXIT_DEGRADED_STRATEGIES = (
    ('asqs', 'is_float_rotation'),
    ('macro_momentum', 'inflation_expectation, yield_curve_spread'),
    ('strategy_c', 'news_sentiment, news_sentiment_score'),
)


def _set_selectable(value: int) -> None:
    """대상 전략의 is_selectable을 일괄 갱신한다.

    SQL은 반드시 sa.text()와 바인드 파라미터(:strategy_type)로 조립한다.
    f-string으로 전략명을 끼워 넣으면 scripts/check_migration_safety.py의
    R1 규칙에 반려된다.
    """
    stmt = sa.text(
        "UPDATE strategies SET is_selectable=:value WHERE strategy_type=:strategy_type"
    )
    connection = op.get_bind()
    for strategy_type, _fields in EXIT_DEGRADED_STRATEGIES:
        connection.execute(stmt, {"value": value, "strategy_type": strategy_type})


def upgrade() -> None:
    _set_selectable(0)


def downgrade() -> None:
    _set_selectable(1)
