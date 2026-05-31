import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class SuperTrend(BaseStrategy):
    """
    슈퍼트렌드 모멘텀 전략 (SuperTrend Swing)
    - 변동성(ATR) 기반의 채널 중심선을 가격이 돌파하여 SuperTrend 시그널이 초록색(direction == 1)으로 매수 상향 반전 시 진입.
    - SuperTrend 시그널이 빨간색(direction == -1)으로 하향 반전 시 철저히 청산하여 수익을 수호.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 슈퍼트렌드 모멘텀 (SuperTrend)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        direction = self._safe_get(row, 'supertrend_direction')
        
        if is_entry:
            # 초록색 강세장 추세 전환 시 매수
            if direction == 1:
                return 100.0
            return 0.0
        else:
            # 적색 하락장 추세 전환 시 매도
            if direction == -1:
                return 100.0
            return 30.0
