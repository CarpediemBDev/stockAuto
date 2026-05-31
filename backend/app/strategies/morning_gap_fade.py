import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class MorningGapFade(BaseStrategy):
    """
    시초가 갭 페이드 전략 (Morning Gap Fade)
    - 특별한 악재 없이 과도하게 갭하락(-3% 이하)하여 개시된 종목이 장 초반 시초가 위로 양봉 회복 돌파할 때 단기 반등 공략 매수.
    - 거래량이 가라앉거나 초단기 이평선(EMA 9) 붕괴 시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 시초가 갭페이드 (Morning Fade)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        fade = self._safe_get(row, 'is_gap_fade')
        
        if is_entry:
            # 갭하락 극점 극복 후 장초반 양봉 회복 돌파 시 매수
            if fade == 1.0:
                return 100.0
            return 0.0
        else:
            ema9 = self._safe_get(row, 'EMA9')
            # 9일선 붕괴 시 즉각 대피
            if close < ema9:
                return 100.0
            return 30.0
