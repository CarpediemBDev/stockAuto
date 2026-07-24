"""seed_remaining_strategy_descriptions

선행 리비전 5864c6a24a72의 DESCRIPTIONS에는 68종만 포함되어, 카탈로그 100종 중
15종은 여전히 summary_ko가 NULL/빈 문자열로 남아 있었다. 이 리비전은 그 잔여
15종만 채운다. 각 문구는 backend/app/strategies/<전략>.py의 실제 진입·청산
조건을 읽고 작성했다.

Revision ID: 7c1e4b93af58
Revises: 5864c6a24a72
Create Date: 2026-07-23 05:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1e4b93af58'
down_revision: Union[str, None] = '5864c6a24a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DESCRIPTIONS = {
    "cross_sectional_momentum": "횡단면 모멘텀 선택 매매. 20봉 수익률·QQQ 대비 상대강도·EMA 정배열·52주 신고가 근접을 합산 채점해 유니버스 최강 종목만 분산 편입하고, 약세장에선 0점 처리로 전량 현금 대피",
    "hurst_adaptive": "허스트 지수 적응형 듀얼 엔진. H>0.55 추세장은 볼린저 상단 돌파 추종, H<0.45 회귀장은 밴드 하단 이탈 후 양봉 복귀 매수, 0.45~0.55 랜덤워크 구간은 휩쏘 방지로 진입 금지",
    "kalman_pairs": "칼만 필터 페어 트레이딩. 칼만 상태전이로 산출한 스프레드 Z-스코어가 -1.8~-3.5 과도 이격일 때 롱 진입, -0.2 수렴 시 익절하고 -4.0 이탈은 공적분 해제로 보아 손절",
    "chaikin_atr": "Chaikin 변동성 수축팽창 돌파. 극수축했던 Chaikin Volatility가 양수로 전환해 팽창을 개시하면서 종가가 돈키언 20일 상단을 평균 대비 1.2배 거래량으로 돌파할 때 진입, EMA10 붕괴 시 청산",
    "sentiment_fomo": "소셜 감성 FOMO 추종. Reddit·Stocktwits 언급 가속도(z-스코어 2.5 이상)와 긍정 감성 0.6 이상이 양봉과 겹칠 때 탑승하고, 언급이 식거나 여론이 부정 전환하면 즉시 탈출",
    "macro_momentum": "매크로 듀얼 모멘텀. 10Y-2Y 금리 스프레드와 기대인플레이션(BEI)으로 침체 경보를 판별해 지수 상승장·BEI 1.8 이상·EMA20 상회일 때만 진입, 침체 경보나 EMA200 붕괴 시 청산",
    "obi_ofa": "호가창 불균형 OFA 가속도. 상위 호가 매수 잔량 비율 0.70 이상과 주문흐름 불균형 가속도 양전환이 동시 발생할 때 진입하고, 잔량 이탈 또는 체결 가속도 붕괴 시 청산",
    "volatility_regime": "변동성 레짐 헷지. VIX/VXV 비율과 VIX 선물 기간구조가 동시에 1.0을 넘는 백워데이션 패닉 국면에서 헷지를 가동하고, 비율이 0.96 미만 안정권으로 복귀하면 헷지 해제",
    "gex_pinning": "감마 익스포저 핀/스퀴즈. 양의 GEX에선 행사가 0.5% 이내 핀 고정 지지를 노리고, 음의 GEX에선 거래량 2.5배 폭발 양봉의 감마 스퀴즈 돌파에 탑승하며 EMA10 이탈 시 청산",
    "pca_knn": "PCA-KNN 단기 패턴 매칭. 다차원 기술 지표를 주성분 분석으로 축소 투영한 뒤 최근접 이웃의 상승 확률이 상승장 0.80·그 외 0.90 이상일 때 진입, 확률 0.40 미만 붕괴 시 즉시 청산",
    "sortino_momentum": "소르티노 모멘텀 자산배분. 60일 롤링 소르티노 랭킹 3위 이내이면서 소르티노 값이 양수인 종목만 편입하고, 5위 밖으로 밀리거나 음수 전환 시 리밸런싱 청산",
    "lava_volume": "매물대 POC 및 VWAP 돌파. 매물 집중 구간(POC) 위에 안착한 상태에서 종가가 당일 VWAP를 1.5% 이상 웃도는 양봉이 나올 때 진입하고, VWAP 지지 붕괴 시 청산",
    "td_sequential": "드마크 TD 순차 반등. TD Buy Setup 9 카운트가 완성된 과매도 극점 직후 첫 양봉 턴어라운드에 진입하고, 반대편 TD Sell Setup 9 카운트 도달 시 과열 극점으로 보아 청산",
    "donchian_breakout": "돈키언 채널 추세 추종. 리처드 돈키언의 고전 채널 돌파 기법으로 종가가 20일 최고가를 넘어설 때 진입하고, 10일 최저가를 이탈하면 전량 청산",
    "opening_range_breakout": "시초가 레인지 돌파(ORB). 장초반 30분간 형성된 레인지 고가를 평균 대비 1.5배 거래량과 함께 돌파할 때 승차하고, 레인지 저가 또는 VWAP 이탈 시 칼같이 손절",
}


def upgrade() -> None:
    # 선행 리비전과 동일하게 비어 있는 행만 채운다(기존 설명 덮어쓰기 방지).
    conn = op.get_bind()
    stmt = sa.text(
        "UPDATE strategies SET summary_ko = :desc "
        "WHERE strategy_type = :stype AND (summary_ko IS NULL OR summary_ko = '')"
    )
    for stype, desc in DESCRIPTIONS.items():
        conn.execute(stmt, {"desc": desc, "stype": stype})


def downgrade() -> None:
    # upgrade()는 비어 있던 행만 채우므로, 롤백도 이 마이그레이션이 실제로 써넣은
    # 문구와 정확히 일치하는 행만 되돌린다. 기존 설명이나 이후 수정본을 지우지 않기 위함.
    conn = op.get_bind()
    stmt = sa.text(
        "UPDATE strategies SET summary_ko = NULL "
        "WHERE strategy_type = :stype AND summary_ko = :desc"
    )
    for stype, desc in DESCRIPTIONS.items():
        conn.execute(stmt, {"desc": desc, "stype": stype})
