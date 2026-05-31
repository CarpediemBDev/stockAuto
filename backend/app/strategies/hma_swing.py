import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class HmaSwing(BaseStrategy):
    """
    Hull Moving Average Swing 전략 (HMA Swing)
    - 가중이평의 지연(Lag)을 최소화한 헐 이동평균선(HMA 20)의 방향성(기울기 양수 전환, hma_up == 1.0)에 매수.
    - HMA 20 기울기가 음수 전환(`hma_up == 0.0`) 시 반박자 빠르게 익절/청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ HMA 지연최소화 스윙 (HMA Swing)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        hma_up = self._safe_get(row, 'hma_up')
        
        if is_entry:
            # HMA 기울기가 우상향 전환 시 매수
            if hma_up == 1.0:
                return 100.0
            return 0.0
        else:
            # HMA 기울기가 우하향 전환 시 청산
            if hma_up == 0.0:
                return 100.0
            return 30.0
