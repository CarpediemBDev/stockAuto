"""hide_unsupported_live_strategies

라이브에서 진입이 불가능한 전략 22종을 카탈로그에서 선택 불가로 내린다.

배경(2026-08-23 실측) - 전략 클래스는 백테스트 엔진이 만드는 지표 이름으로 작성돼
있는데, 라이브 스캐너가 그 값을 싣지 않으면 BaseStrategy._safe_get이 예외 없이 0을
돌려주고 전략은 '진입 조건 미충족'으로 조용히 퇴화한다. 여기 나열한 21종이 요구하는
필드는 옵션 체인·호가 틱·내부자 공시·SNS 버즈처럼 외부 데이터가 있어야 채울 수 있어
계산으로 복구할 수 없다(app/scanner/signal_contract.py의 UNSUPPORTED_LIVE_FIELDS).

사용자가 이 전략을 고르면 봇은 기동되지만 단 한 건도 매매하지 않고 수익률 0%에
머문다. 실제로 개발 DB의 해당 계정들이 전부 거래 0건·수익률 정확히 0.00%였다.
고를 수 없게 막는 것이 데이터를 조달하기 전까지의 정답이다.

is_active는 건드리지 않는다. 백테스트·연구 목적의 조회는 계속 가능해야 하며,
이미 해당 전략을 쓰고 있는 계정의 동작도 바꾸지 않는다(그랜드파더링).

Revision ID: b7c3d9e14a20
Revises: a4c7e2b91f30
Create Date: 2026-08-23 14:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7c3d9e14a20'
down_revision: Union[str, None] = 'a4c7e2b91f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 외부 데이터 의존으로 라이브 진입이 불가능한 전략. 근거 필드를 함께 남긴다.
UNSUPPORTED_STRATEGIES = (
    ('cross_asset', 'cross_asset_ok'),
    ('dark_pool', 'dark_pool_price'),
    ('earn_drift', 'is_earnings_gap_drift'),
    ('float_rot', 'is_float_rotation'),
    ('gamma_flip', 'gamma_flip'),
    ('gex_pinning', 'net_gex_proxy, strike_distance'),
    ('insider_buying', 'insider_signal'),
    ('kalman_pairs', 'kalman_zscore'),
    ('max_pain', 'is_expiry_week, max_pain_price'),
    ('obi_ofa', 'OFI_acceleration, order_book_imbalance'),
    ('offering_reb', 'is_offering_rebound'),
    ('order_flow', 'order_flow_delta'),
    ('pairs_trading', 'spread_zscore'),
    ('pca_knn', 'knn_up_probability'),
    ('pdufa_calendar', 'days_to_pdufa'),
    ('sentiment_fomo', 'mention_zscore, sentiment_positive'),
    ('social_buzz', 'social_buzz_surge'),
    ('sympathy', 'is_sympathy_setup'),
    ('vix_hedging', 'is_vix_ok'),
    ('volatility_regime', 'vix_term_structure, vix_vxv_ratio'),
    ('warrant_arb', 'is_warrant_support'),
    # 외부 데이터 문제가 아니라 설계상 진입 채점이 없는 전략. 단독으로 고르면
    # 매수가 발생하지 않으므로 같은 사용자 피해(봇은 도는데 거래 0건)가 생긴다.
    ('parabolic_blow', '진입 채점 없음(청산 전용)'),
)


def _set_selectable(value: int) -> None:
    """대상 전략의 is_selectable을 일괄 갱신한다.

    SQL은 반드시 sa.text()와 바인드 파라미터(:strategy_type)로 조립한다.
    f-string으로 전략명을 문자열에 끼워 넣으면 값에 작은따옴표가 섞였을 때
    구문이 깨지고, scripts/check_migration_safety.py의 R1 규칙에 반려된다.
    """
    stmt = sa.text(
        "UPDATE strategies SET is_selectable=:value WHERE strategy_type=:strategy_type"
    )
    connection = op.get_bind()
    for strategy_type, _fields in UNSUPPORTED_STRATEGIES:
        connection.execute(stmt, {"value": value, "strategy_type": strategy_type})


def upgrade() -> None:
    _set_selectable(0)


def downgrade() -> None:
    _set_selectable(1)
