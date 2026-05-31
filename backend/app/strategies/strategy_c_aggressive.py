import pandas as pd
from app.strategies.strategy_c import StrategyC

class StrategyCAggressive(StrategyC):
    """
    🔥 전략 C - 공격형 (Strategy C-Aggressive)
    - 40% 기본 비중 할당 (최소 $2,000 보장)
    - 장세 레짐 맞춤형 공격 포지션 셋업:
      * 상승장 (BULLISH) -> 즉시 100% 풀비중 진입 (initial_entry_factor = 1.0)
      * 하락장/횡보장 (BEARISH/NEUTRAL) -> 50% 절반 비중 진입 (initial_entry_factor = 0.5)
    - 50% 진입 시, +2% 상승 시 1차 피라미딩 불타기를 통해 풀비중 달성 허용
    - 휩쏘 페이크 돌파를 예방하기 위해 넓은 손절선 (6% / 3x ATR) 및 트레일링 스탑 (4% / 2x ATR) 탑재
    """
    
    def __init__(self):
        super().__init__()
        self.name = "🔥 전략 C-공격형 (100%/50%)"

    def get_initial_entry_factor(self, regime: str) -> float:
        if regime == "BULLISH":
            return 1.0  # 상승장: 즉시 100% 풀비중 베팅
        return 0.5      # 약세/횡보장: 즉시 50% 절반 비중 제한 진입

    def get_pyramid_trigger(self, stage: int) -> float:
        # 50%로 진입했을 경우, +2% 상승 시 1차 추가 매수를 통해 100% 풀비중 완성이 가능하도록 설계
        if stage == 1:
            return 2.0
        return 999.0

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """변동성이 심한 공격형 전략 전용 동적 6% 손절선 적용"""
        sl_base = 6.0
        sl_mult = 3.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        """수익 방어를 위한 4% 트레일링 스탑 적용"""
        ts_base = 4.0
        ts_mult = 2.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(ts_base, atr_pct * ts_mult)
        return ts_base
