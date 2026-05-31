import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class EpisodicPivot(BaseStrategy):
    """
    에피소딕 피벗 전략 (Episodic Pivot - EP)
    - 갭상승 +10% 이상, RVOL >= 3.0(거래량 300% 이상 폭발)을 보인 돌파주 포착 후 시초가 위에서 진입.
    - 강세 이평선(EMA 9) 이탈 시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 에피소딕 피벗 (Episodic Pivot)")
        self.base_allocation_pct = 0.50  # 폭발형 진입으로 비중 50% 설정
        self.min_smart_exit_profit = 1.5

    def get_initial_entry_factor(self, regime: str) -> float:
        return 1.0  # 정찰병 없이 즉시 풀비중 진입

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            gap = self._safe_get(row, 'gap_pct')
            rvol = self._safe_get(row, 'RVOL')
            open_val = self._safe_get(row, 'Open')
            
            # 갭 +10% 이상 & RVOL 3.0배 이상 & 시초가 돌파 상태
            if gap >= 10.0 and rvol >= 3.0 and close > open_val:
                return 100.0
            return 0.0
        else:
            ema9 = self._safe_get(row, 'EMA9')
            open_val = self._safe_get(row, 'Open')
            # 9일선 이평 붕괴 또는 시가 밑으로 음봉 전환 시 청산
            if close < ema9 or close < open_val:
                return 100.0
            return 30.0
