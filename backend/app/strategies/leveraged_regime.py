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

    def compute_state_series(self, daily_closes: pd.Series) -> pd.Series:
        """완결 일봉 종가 시리즈로 '매 시점의 확정 목표 상태'(IN/OUT) 시계열을 산출합니다.

        상태기계 SSOT: 시작은 OUT. SMA 위로 confirm_days 연속 마감 시 IN 확정,
        아래로 confirm_days 연속 마감 시 OUT 확정(휩쏘 가드). 라이브 판정(compute_target_state)과
        백테스트 엔진(자율 슬롯 경로)이 이 단일 전방 패스를 공유해 두 경로의 상태가 항상 일치한다.

        반환: 입력(결측 제거) 인덱스에 정렬된 "IN"/"OUT" 문자열 시리즈. 각 값은 '그 종가까지
        관측했을 때'의 확정 상태이므로, 백테스트는 state[t]로 판정하고 t+1 봉에서 체결하면
        룩어헤드가 없다.
        """
        closes = daily_closes.dropna()
        n = len(closes)

        if not self.use_filter:
            return pd.Series(["IN"] * n, index=closes.index)

        states = ["OUT"] * n
        if n < self.sma_period + self.confirm_days:
            # 데이터 부족 구간은 전부 안전측(현금)
            return pd.Series(states, index=closes.index)

        sma = closes.rolling(self.sma_period).mean()
        above = (closes > sma).astype(int).tolist()

        state = 0  # 0=OUT, 1=IN
        streak_dir = None
        streak = 0
        for i in range(self.sma_period - 1, n):
            d = above[i]
            if d == streak_dir:
                streak += 1
            else:
                streak_dir, streak = d, 1
            if state == 0 and d == 1 and streak >= self.confirm_days:
                state = 1
            elif state == 1 and d == 0 and streak >= self.confirm_days:
                state = 0
            states[i] = "IN" if state == 1 else "OUT"
        return pd.Series(states, index=closes.index)

    def compute_target_state(self, daily_closes: pd.Series) -> str:
        """마지막 완결 일봉 기준 목표 상태("IN"=보유 / "OUT"=현금)를 반환합니다(라이브 스케줄러용).

        상태 시계열 SSOT는 compute_state_series이며, 여기서는 그 마지막 값만 취한다.
        """
        series = self.compute_state_series(daily_closes)
        if series.empty:
            # 데이터 부족 시 안전측(현금)으로 판정
            return "OUT"
        return str(series.iloc[-1])

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        """자율 슬롯은 스캐너 점수 파이프라인을 사용하지 않습니다. 항상 0점(미발화)."""
        if score_card is not None:
            score_card.append({
                "factor": "자율 슬롯 (스캐너 점수 미사용 — 일봉 레짐 판정 전용)",
                "score": 0,
                "passed": False,
            })
        return 0.0


class LeveragedRegime3x(LeveragedRegime):
    """
    🚀 지수 레버리지 레짐 3x (Leveraged Regime 3x) — 공격형 슬리브

    - 코어(LeveragedRegime)와 신호·상태기계·룩어헤드 차단 로직이 완전히 동일하되,
      보유 자산만 QLD(2x) 대신 TQQQ(3x)를 사용한다.
    - 실증(월별 20년): 월 +30% 도달은 197개월 중 4회(2%)로 희귀하며, 그 대가로
      월 −35% 낙폭·상시 MDD −55%대를 감수한다. '월 30%' 2차 목표 도전 전용.
    """

    def __init__(self):
        super().__init__(
            name="🚀 지수 레버리지 레짐 3x (TQQQ 3x + SMA200)",
            asset_ticker="TQQQ",
            signal_ticker="QQQ",
            sma_period=200,
            confirm_days=3,
            use_filter=True,
        )


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
