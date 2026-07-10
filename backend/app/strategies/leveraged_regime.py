import pandas as pd
from app.strategies.base_strategy import BaseStrategy


class LeveragedRegime(BaseStrategy):
    """
    🏛️ 지수 레버리지 레짐 (Leveraged Regime) — 코어 자본층 전략

    - 종목 선택을 하지 않는다. QQQ 일봉 종가가 200일 SMA 위에 있으면 레버리지 ETF(QLD 2x)를
      보유하고, 아래로 이탈이 확정되면 전량 매도해 현금으로 대피한다.
    - 휩쏘 가드: SMA 위/아래로 3거래일 '연속' 마감해야 상태 전환을 확정한다.
    - 신호는 완결된 일봉만 사용(당일 미완결 봉 제외)하고 체결은 다음 정규장에서 이뤄지므로
      백테스트(신호 익일 체결)와 등가이며 룩어헤드가 없다.
    - 스캐너 시그널 파이프라인·손절/트레일링 청산을 사용하지 않는 자율(autonomous) 슬롯으로,
      스케줄러의 전용 경로(process_autonomous_slots)가 집행한다.

    실증 근거(2026-07-07/09 현황판): QLD 2x+SMA200(3일 확정) 5창 4승·15.5년 CAGR +23.0%
    (QQQ +18.9%), 거래 연 5~6회. 상세 수치는 docs/tasks 기록 참조.
    """

    # 스케줄러가 일반 진입/청산 파이프라인에서 이 슬롯을 면제하는 식별 플래그
    is_autonomous = True

    def __init__(
        self,
        name: str = "🏛️ 지수 레버리지 레짐 (QLD 2x + SMA200)",
        asset_ticker: str = "QLD",
        signal_ticker: str = "QQQ",
        sma_period: int = 200,
        confirm_days: int = 3,
        use_filter: bool = True,
    ):
        super().__init__(name=name)
        self.asset_ticker = asset_ticker
        self.signal_ticker = signal_ticker
        self.sma_period = sma_period
        self.confirm_days = confirm_days
        self.use_filter = use_filter

        # 자율 슬롯은 슬롯 현금을 통째로 단일 ETF에 배정한다 (소액계좌 몰빵 하한 미적용)
        self.base_allocation_pct = 1.0
        self.min_allocation_usd = 0.0

    def compute_target_state(self, daily_closes: pd.Series) -> str:
        """완결 일봉 종가 시리즈로 목표 상태("IN"=보유 / "OUT"=현금)를 판정합니다.

        상태기계: 시작은 OUT. SMA 위로 confirm_days 연속 마감 시 IN 확정,
        아래로 confirm_days 연속 마감 시 OUT 확정. (백테스트 하네스와 동일 로직)
        """
        if not self.use_filter:
            return "IN"

        closes = daily_closes.dropna()
        if len(closes) < self.sma_period + self.confirm_days:
            # 데이터 부족 시 안전측(현금)으로 판정
            return "OUT"

        sma = closes.rolling(self.sma_period).mean()
        above = (closes > sma).astype(int).tolist()

        state = 0  # 0=OUT, 1=IN
        streak_dir = None
        streak = 0
        for d in above[self.sma_period - 1:]:
            if d == streak_dir:
                streak += 1
            else:
                streak_dir, streak = d, 1
            if state == 0 and d == 1 and streak >= self.confirm_days:
                state = 1
            elif state == 1 and d == 0 and streak >= self.confirm_days:
                state = 0
        return "IN" if state == 1 else "OUT"

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        """자율 슬롯은 스캐너 점수 파이프라인을 사용하지 않습니다. 항상 0점(미발화)."""
        if score_card is not None:
            score_card.append({
                "factor": "자율 슬롯 (스캐너 점수 미사용 — 일봉 레짐 판정 전용)",
                "score": 0,
                "passed": False,
            })
        return 0.0


class BenchmarkQqqHold(LeveragedRegime):
    """
    📏 QQQ 단순보유 벤치마크 (Benchmark Buy & Hold)

    - 레짐 필터 없이 QQQ를 슬롯 현금 전액으로 1회 매수 후 계속 보유한다.
    - 라이브 시뮬레이션에서 다른 계정들과 동일 체결/수수료 조건의 공정 비교 기준선을 제공한다.
    """

    def __init__(self):
        super().__init__(
            name="📏 QQQ 단순보유 벤치마크",
            asset_ticker="QQQ",
            signal_ticker="QQQ",
            use_filter=False,
        )
