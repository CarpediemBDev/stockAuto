"""seed_missing_strategy_descriptions

Revision ID: 5864c6a24a72
Revises: 89c6a78e09ec
Create Date: 2026-07-23 02:57:20.362967

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5864c6a24a72'
down_revision: Union[str, None] = '89c6a78e09ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DESCRIPTIONS = {
    "asqs": "퀀텀 스퀴즈 모멘텀. 볼린저 밴드와 켈트너 채널의 극단적 축소 후 거래량 폭발 돌파 시 강력한 초기 추세 탑승",
    "bollinger_tr": "볼린저 밴드 상단 돌파 추세추종. 변동성 상한선 돌파 시 상방 모멘텀을 추종하는 전형적 라인 돌파 매매",
    "coppock_curve": "코폭 커브 장기 바닥 포착. 10/14개월 률-오브-체인지 기반 모멘텀 지표로 장기 하락장의 극점 바닥 반등 추적",
    "cross_asset": "자산간 금리 및 거시 지표 필터링. 채권 금리·환율 등 거시 자산 간 상관관계를 분석하여 매수 승수 제어",
    "dark_pool": "다크풀 기관 블록딜 추적. 비공개 세력 장외 대량 거래 수급 흔적 포착 시 세력 매집선 안착 공략",
    "darvas_box": "다바스 박스 모멘텀 스윙. 신고가 경신 후 생성된 상하한 박스권 상단 돌파 시 폭발적 주가 상승 추종",
    "death_rebound": "역배열 극점 평균회귀. 이동평균선 완전 역배열 상태에서 투매 과매도 발생 시 극점 단기 반등 공략",
    "double_bb_reversion": "마켓트랩 더블 볼린저밴드. 이중 볼린저 밴드 하단 외곽 이탈 후 내부 재진입 시 강한 평균회귀 스나이핑",
    "double_bot": "이중 바닥(W 패턴) 돌파. 2차 저점 형성 후 넥라인 저항선을 강한 거래량으로 돌파 시 진입",
    "earn_drift": "깜짝 실적 발표 갭 앤 드리프트 (EGAD). 시장 예상치를 크게 상회한 어닝 서프라이즈 갭 상승 후 지속 상승 추종",
    "elder_ray": "엘더레이 힘의 균형. Bull Power 및 Bear Power 지표로 세력의 매수/매도 압력 불균형을 포착하여 반전 타격",
    "episodic_pivot": "에피소딕 피벗. 주가 패러다임을 바꾸는 메가 호재(실적, FDA, 계약 등) 발표 시 시초가 폭발 돌파 매수",
    "first_red": "퍼스트 레드 데이 숏. 수일간 급등한 주도주가 최초로 꺾이는 음봉 발생 시 단기 조정 과열 청산 포착",
    "fisher_transform": "피셔 트랜스폼 정점 반전. 주가 분포를 정규분포로 변환하여 극단적 과매수/과매도 피크에서 반전 매매",
    "float_rot": "유통주식 회전율 돌파. 당일 유통 주식 수 이상의 대량 거래량 터지며 매물대 소화하는 주도주 공략",
    "gamma_flip": "옵션 감마플립 셋업. 옵션 딜러들의 델타 헷징 수급이 반전되는 핵심 체인지 포인트 수급 타격",
    "heikin_ashi": "하이킨아시 추세추종. 캔들 노이즈를 제거한 하이킨아시 연속 양봉/음봉으로 안정적 추세 지속성 추적",
    "hma_swing": "Hull 이동평균 지연최소화 스윙. 일반 이평선의 시차 지연을 최소화한 HMA 방식을 활용한 단기 스윙 타점",
    "ichimoku_kumo": "일목균형표 구름대 돌파. 주가가 두꺼운 저항 구름대를 강하게 상향 돌파할 때 강력한 추세 전환으로 진입",
    "insider_buying": "내부자 지분 매수 스캔. 회사 임원 및 대주주의 의미 있는 장내 대량 매수 공시 포착 시 동반 매수",
    "keltner_reversion": "켈트너 채널 하단 반전. 변동성 채널 하선 이탈 후 채널 내부로 회귀하는 단기 과매도 수나이핑",
    "keltner_tr": "켈트너 채널 추세추종. 켈트너 채널 상한선 위 지속 안착 시 강력한 밴드 워킹 추세 탑승",
    "larry_williams": "윌리엄스 %R 단기 반전. 윌리엄스 %R 지표가 극단적 과매도(-80 이하) 탈출 시 단기 반등 공략",
    "macd_diverg": "MACD 다이버전스 반전. 주가는 저점을 낮추나 MACD 히스토그램은 저점을 높이는 강세 다이버전스 포착",
    "max_pain": "옵션 맥스페인 반전. 만기일 옵션 발행자 이익이 최대화되는 맥스페인 가격대로의 주가 수렴 특성 활용",
    "morning_gap_fade": "시초가 과열 갭 페이드. 장초반 합당한 호재 없이 뜬 과도한 갭상승 종목의 시초가 음봉 반전 포착",
    "offering_reb": "유상증자 악재 소멸 반등. 유증 공시 후 폭락한 주가가 악재 소멸 및 매물 소화 후 지지받을 때 반등 매수",
    "order_flow": "볼륨 델타 오더플로우. 체결창 매수/매도 실시간 잔량 분석을 통해 실제 체결 강도가 폭발하는 지점 포착",
    "overnight_gap": "오버나이트 갭 사냥. 종가 무렵 강력한 수급이 유입된 주도주를 오버나이트하여 이튿날 시초가 갭 수익 도모",
    "pairs_trading": "롱-숏 통계적 차익거래. 동일 산업군 내 동조화 종목 간 스프레드 비정상 벌어짐 발생 시 평균회귀 매매",
    "panic_dip_buy": "모닝 패닉 딥 바잉. 장 초반 투매 및 손절 물량 쏟아질 때 주요 장기 이평선/피봇 지지선에서 스나이핑",
    "parabolic_blow": "파라볼릭 폭발 청산. 과열 급등 구간에서 파라볼릭 SAR 지표 회손 시 수익을 보존하는 과열 이탈 청산",
    "parabolic_sar": "파라볼릭 SAR 매매. 주가 곡선과 SAR 도트의 상하 교차를 추적하여 추세 전환 시점 즉시 포착",
    "pdufa_calendar": "바이오 PDUFA 임상 스윙. FDA 승인 심사 일정(PDUFA) 도래 전 선취매 수급 유입 기대 모멘텀 스윙",
    "pivot_point": "피봇 포인트 반전. 당일 피봇 1차/2차 지지선 및 저항선에서의 가격 반발 반전 매매",
    "pivot_rebound": "피봇 지지/저항 돌파 반등. 피봇 지지선에서의 반등 확인 또는 피봇 저항선 돌파 시 시세 확장 진입",
    "pre_gapper": "프리마켓 갭 돌파. 정규장 개장 전 프리마켓에서 5% 이상 거래량 동반 갭상승하는 핫 종목 선점",
    "premarket_breakout": "프리마켓 최고가 돌파. 프리마켓 장중 형성된 고점을 정규장 시초가에 넘어서는 돌파 공략",
    "pump_run_pull": "펌프 앤 런 눌림목. 급등 후 첫 번째 거래량 감소 눌림목(First Pullback) 구간에서 재차 반등 수급 공략",
    "range_contra": "변동성 수축(Inside Bar) 돌파. 캔들 몸통이 극도로 좁아진 수축 구간 이후 상방 변동성 확산 시 진입",
    "relative_str": "지수 대비 상대강도(RS) 주도주. 시장 지수가 하락/횡보할 때 홀로 신고가를 갱신하는 상대강도 최상위주 공략",
    "short_squeeze": "숏스퀴즈 가속. 높은 공매도 잔량 비율 종목에서 숏커버링 물량이 겹치며 주가 폭발 상승하는 구간 공략",
    "social_buzz": "소셜 버즈 모멘텀 스캔. 트위터, 레딧 등 소셜 미디어 언급량이 급증하며 관심집중되는 밈주/이슈주 타격",
    "stoch_extreme": "스토캐스틱 극점 반전. Stochastics Fast/Slow 지표의 과매도 영역(20 이하) 골든크로스 반전 진입",
    "supernova": "슈퍼노바 포모 급등주. 거래량이 평소 50배 이상 터지며 단기 대시세가 시작되는 초신성 주도주 타격",
    "supertrend": "슈퍼트렌드 모멘텀. ATR 기반 추세 방향선인 SuperTrend 지표의 색상 전환 시 정방향 추세 진입",
    "sympathy": "테마 2등주 짝짓기 매매. 테마 대장주가 시세를 분출할 때 뒤따라 상승하는 2등주/수혜주 시차 매수",
    "trend_stabilization": "추세 안착 눌림목. 급등 후 이동평균선(SMA 20) 부근까지 차분히 안정화되는 눌림 지지 확인 후 진입",
    "triple_ema": "삼중 EMA 정배열 교차. 단기(5), 중기(10), 장기(20) EMA 이평선이 동시 정배열 골든크로스 시 정추세 매수",
    "turn_of_month": "월말 월초 계절성 효과. 월말 기관 포트폴리오 리밸런싱 및 월초 신규 자금 유입 특성을 활용한 계절성 매매",
    "vcp_breakout": "마크 미네르비니 VCP 패턴. 변동성이 3~4차례 계단식으로 축소된 후 수축 완료 지점 강한 거래량 돌파 공략",
    "vix_hedging": "VIX 연계 리스크 헷지. 공포지수(VIX) 급등 시 포트폴리오 위험을 방어하기 위해 헷지 자산 및 비중 자동 조절",
    "vol_spike_brk": "10배 거래량 장대양봉 돌파. 평소 거래량의 1,000% 이상 폭발하며 전고점 뚫는 세력 개입 장대양봉 포착",
    "volume_filtered_cross": "거래량 필터링 이동평균 교차. 단순히 이평선 교차만 보는 것이 아니라 대량 거래량이 뒷받침된 교차만 진입",
    "volume_profile": "매물대 프로파일 (Volume Profile). 매물 집중 구간(POC)을 상향 돌파하거나 매물대 지지 반등 시 매수",
    "warrant_arb": "신주인수권/워런트 괴리 매수. 본주 가격과 워런트 행사가 간 차익 괴리율 발생 시 안전 차익 포착",
    "weekend_trend": "주말 보유 계절성 스윙. 금요일 종가 수급 우량주 매수 후 월요일 개장 시 시초가 갭 수익 실현",
    "woodies_cci": "우디 CCI 고스트 패턴. CCI 지표 산과 골짜기가 이루는 고스트/트렌드라인 돌파 구간 시그널 타격",
    "wyckoff_spring": "와이코프 스프링 반전. 세력이 지지선을 의도적으로 깨뜨려 개미 물량을 털어내는 Spring 구역 포착 후 안착 시 매수",
    "zscore_reversion": "Z-스코어 정규화 평균회귀. 주가 위치를 이동평균 대전제로 표준화(Z-Score)하여 ±2σ 이탈 시 회귀 매매",
    "connors_rsi": "래리 코너스 ConnorsRSI. RSI(3), Streak RSI, Percent Rank 3가지 요소를 합성한 극단적 과매도 스나이핑",
    "leveraged_regime": "지수 레버리지 레짐 (QLD 2x). SMA 200 이평선 위에 시장 지수가 있을 때 QLD 2x 레버리지를 적극 운용",
    "benchmark_qqq_hold": "QQQ 단순 보유 벤치마크. 전략 성과 비교를 위한 나스닥 100 지수 추종 ETF(QQQ) 100% 매수 후 홀딩",
    "core_satellite": "코어-새틀라이트 복합 운용. 레버리지 레짐 70%(코어) + 전략 C 30%(새틀라이트)로 안정성과 알파 동시 추구",
    "leveraged_regime_3x": "지수 레버리지 레짐 3x (TQQQ 3x). 시장 지수가 SMA 200 위에 있을 때 TQQQ 3배 레버리지 초고수익 추구",
    "multi_slot": "격리형 2슬롯 자본 분할. 에피소딕 피벗(EP 50%)과 ConnorsRSI(RS 50%) 자본 격리 병렬 운용",
    "multi_slot_3": "격리형 3슬롯 자본 분할. EP(30%) : ASQS(30%) : RS(40%) 독립 슬롯으로 멀티 디버시파이드 운용",
    "three_slot": "격리형 3슬롯 오케스트레이터. 3개 독립 매매 슬롯에 자본을 분할 배정하여 리스크를 분산 관리하는 오케스트레이터"
}


def upgrade() -> None:
    for stype, desc in DESCRIPTIONS.items():
        escaped_desc = desc.replace("'", "''")
        op.execute(
            f"UPDATE strategies SET summary_ko = '{escaped_desc}' "
            f"WHERE strategy_type = '{stype}' AND (summary_ko IS NULL OR summary_ko = '')"
        )


def downgrade() -> None:
    for stype in DESCRIPTIONS.keys():
        op.execute(
            f"UPDATE strategies SET summary_ko = NULL WHERE strategy_type = '{stype}'"
        )

