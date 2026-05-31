import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class VolumeFilteredCross(BaseStrategy):
    """
    거래량 필터 이평 교차 전략 (Volume Filtered Golden Cross)
    - 9일 EMA선이 20일 EMA선을 골든크로스 할 때, 거래량 급증(RVOL >= 1.5)이 동반된 진성 돌파만 필터링하여 매수.
    - 9일 EMA선이 20일 EMA선을 다시 데드크로스 할 때 즉각 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 거래량 필터 이평교차 (Volume Golden Cross)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        rvol = self._safe_get(row, 'RVOL')
        
        if is_entry:
            # 9일선이 20일선 위에 위치하고 거래량이 1.5배 이상 동반된 강세 돌파
            if ema9 > ema20 and rvol >= 1.5:
                return 100.0
            return 0.0
        else:
            # 데드크로스 발생 시 청산
            if ema9 < ema20:
                return 100.0
            return 30.0
