"""seed_complete_strategy_catalog

Revision ID: c8e9f0123456
Revises: b7d8e9f01234
Create Date: 2026-06-15 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8e9f0123456"
down_revision: Union[str, None] = "b7d8e9f01234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STRATEGIES = (
    ("asqs", "🚀 ASQS (초신성 퀀텀 스퀴즈) 🔥", "Asqs"),
    ("bb_squeeze", "존카터 BB스퀴즈", "TTM Squeeze"),
    ("bollinger_tr", "볼밴 상단 돌파 추세", "Bollinger Trend"),
    ("complex", "전략 C (11대 복합)", "Complex"),
    ("complex_aggressive", "🔥 전략 C-공격형 (100%/50%)", "Complex Aggressive"),
    ("complex_ep", "전략 C-EP 통합형", "Complex Ep"),
    ("coppock_curve", "코폭커브 장기바닥", "Coppock Curve"),
    ("cross_asset", "자산간 금리필터", "Cross Asset"),
    ("dark_pool", "다크풀 블록딜", "Dark Pool Scan"),
    ("darvas_box", "다바스 박스 매매", "Darvas Box"),
    ("death_rebound", "역배열 극점 평균회귀", "Death Rebound"),
    ("double_bb", "마켓트랩 더블 볼린저밴드", "Double BB Reversion"),
    ("double_bb_reversion", "마켓트랩 더블 볼린저밴드", "Double BB Reversion"),
    ("double_bot", "이중바닥 W 돌파", "Double Bottom"),
    ("earn_drift", "깜짝실적 갭앤드리프트", "EGAD"),
    ("elder_ray", "엘더레이 힘의균형", "Elder Ray"),
    ("ema_only", "EMA 이평정배열", "EMA Only"),
    ("episodic_pivot", "에피소딕 피벗", "Episodic Pivot"),
    ("exploded_c", "전략 C-폭발형", "Exploded C"),
    ("first_red", "퍼스트 레드 데이 숏", "First Red"),
    ("fisher_transform", "피셔트랜스폼 정점반전", "Fisher"),
    ("float_rot", "유통주 회전율 돌파", "Float Rotation"),
    ("gamma_flip", "감마플립 셋업", "Gamma Flip"),
    ("heikin_ashi", "하이킨아시 추세추종 (Heikin-Ashi)", "Heikin Ashi"),
    ("hma_swing", "HMA 지연최소화 스윙", "HMA Swing"),
    ("ichimoku_kumo", "일목균형표 구름대돌파", "Ichimoku"),
    ("insider_buying", "내부자 지분매수", "Insider Scan"),
    ("keltner_reversion", "켈트너채널 반전", "Keltner Reversion"),
    ("keltner_tr", "켈트너 채널 추세추종", "Keltner Trend"),
    ("larry_williams", "윌리엄스 %R 단기반전 (Williams %R)", "Larry Williams"),
    ("macd_diverg", "MACD 다이버전스", "MACD Divergence"),
    ("max_pain", "맥스페인 반전", "Max Pain"),
    ("morning_gap_fade", "시초가 갭페이드", "Morning Fade"),
    ("multi_slot", "격리형 2슬롯 (EP 50% : RS 50%)", "Modular 2-Slot (EP 50% : RS 50%)"),
    ("multi_slot_3", "격리형 3슬롯 (EP 30% : ASQS 30% : RS 40%)", "Modular 3-Slot (EP 30% : ASQS 30% : RS 40%)"),
    ("obv_only", "차트픽 OBV 매집", "OBV Only"),
    ("offering_reb", "유증 악재 소멸 반등", "Offering Reb"),
    ("orb_only", "토비크라벨 ORB", "ORB Only"),
    ("order_flow", "볼륨델타 오더플로", "Order Flow"),
    ("overnight_gap", "오버나이트 갭 사냥", "Overnight Gap"),
    ("pairs_trading", "롱-숏 통계적 차익거래", "Pairs Trading"),
    ("panic_dip_buy", "모닝 패닉 딥 바잉", "Panic Dip"),
    ("parabolic_blow", "파라볼릭 폭발 청산", "Parabolic Blow"),
    ("parabolic_sar", "파라볼릭 SAR 반전", "Parabolic SAR"),
    ("pdufa_calendar", "PDUFA 임상스윙", "PDUFA Run"),
    ("pivot_point", "피봇포인트 반전", "Pivot Point"),
    ("pivot_rebound", "피봇 저항돌파/지지반등", "Pivot Rebound"),
    ("pre_gapper", "프리마켓 갭 돌파", "Pre Gapper"),
    ("premarket_breakout", "Pre-market Breakout", "Premarket Breakout"),
    ("pump_run_pull", "펌프 앤 런 눌림목", "Pump Pullback"),
    ("qullamaggie", "쿨라매기 돌파", "Qullamaggie"),
    ("range_contra", "변동성 캔들 수축 돌파", "Range Contraction"),
    ("regime_switching", "마스터 레짐스위칭", "Regime Switching"),
    ("relative_str", "지수 대비 강세 주도주", "Relative Strength"),
    ("rsi2_connors", "래리코너스 RSI 2", "RSI 2 Only"),
    ("rsi_bb_only", "RSI 볼린저밴드", "RSI BB Only"),
    ("senior_simple", "시니어 단순화", "Strategy S"),
    ("short_squeeze", "숏스퀴즈 가속", "Short Squeeze"),
    ("social_buzz", "소셜버즈 모멘텀", "Social Buzz"),
    ("stoch_extreme", "스토캐스틱 극점 반전", "Stoch Extreme"),
    ("stockauto_v1", "전략 A (태초 v1.0)", "Stockauto V1"),
    ("strategy_a", "전략 A (태초 v1.0)", "Strategy A"),
    ("strategy_b", "전략 B (실험용)", "Strategy B"),
    ("strategy_c", "전략 C (11대 복합)", "Strategy C"),
    ("strategy_c_aggressive", "🔥 전략 C-공격형 (100%/50%)", "Strategy C Aggressive"),
    ("strategy_c_ep", "전략 C-EP 통합형", "Strategy C Ep"),
    ("supernova", "슈퍼노바", "Supernova"),
    ("supernova_squeeze", "🚀 ASQS (초신성 퀀텀 스퀴즈) 🔥", "Supernova Squeeze"),
    ("supertrend", "슈퍼트렌드 모멘텀", "SuperTrend"),
    ("sympathy", "테마 2등주 짝짓기", "Sympathy Play"),
    ("three_slot", "격리형 3슬롯 (EP 30% : ASQS 30% : RS 40%)", "Modular 3-Slot (EP 30% : ASQS 30% : RS 40%)"),
    ("trend_stabilization", "Trend Stabilization Pullback", "Trend Stabilization"),
    ("triple_ema", "삼중 EMA 정배열 교차", "Triple EMA"),
    ("turn_of_month", "월말효과 계절성", "Turn of Month"),
    ("vcp_breakout", "변동성 축소 패턴", "VCP"),
    ("vix_hedging", "VIX 변동성 연계 헷지", "VIX Hedging"),
    ("vol_spike_brk", "10배 거래량 장대양봉", "Vol Spike"),
    ("volume_filtered_cross", "거래량 필터 이평교차", "Volume Golden Cross"),
    ("volume_profile", "매물대 프로파일", "Volume POC"),
    ("vwap_only", "VWAP 세력지지선", "VWAP Only"),
    ("warrant_arb", "워런트 괴리 매수", "Warrant Arb"),
    ("weekend_trend", "주말 추세 매매", "Weekend Trend"),
    ("woodies_cci", "우디 CCI 고스트", "Woodies CCI"),
    ("wyckoff_spring", "와이코프 스프링", "Wyckoff Spring"),
    ("zscore_reversion", "Z-스코어 평균회귀 (Z-Score Reversion)", "Zscore Reversion"),
)


def upgrade() -> None:
    strategy_table = sa.table(
        "strategies",
        sa.column("strategy_type", sa.String()),
        sa.column("name_ko", sa.String()),
        sa.column("name_en", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    connection = op.get_bind()
    existing_keys = set(
        connection.execute(
            sa.select(strategy_table.c.strategy_type)
        ).scalars()
    )
    missing_rows = [
        {
            "strategy_type": strategy_type,
            "name_ko": name_ko,
            "name_en": name_en,
            "is_active": True,
        }
        for strategy_type, name_ko, name_en in STRATEGIES
        if strategy_type not in existing_keys
    ]
    if missing_rows:
        op.bulk_insert(strategy_table, missing_rows)


def downgrade() -> None:
    # 전략 테이블은 운영 중 수정될 수 있으므로 데이터 다운그레이드는 수행하지 않습니다.
    pass
