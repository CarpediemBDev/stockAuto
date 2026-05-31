import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ElderRay(BaseStrategy):
    """
    엘더 레이 힘의 균형 전략 (Elder Ray Index)
    - 매도세의 모멘텀 소멸(Bear Power가 0 이하에서 우상향 반전, `elder_ray_bear_up == 1.0`)을 감착하고, 주가가 이평선 위에 있는 상승 조건 확인 후 매수.
    - 주가가 기준선인 EMA 20을 하향 돌파 시 즉시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 엘더레이 힘의균형 (Elder Ray)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ema20 = self._safe_get(row, 'EMA20')
        bear_power = self._safe_get(row, 'elder_ray_bear')
        bear_up = self._safe_get(row, 'elder_ray_bear_up')
        
        if is_entry:
            # Bear Power가 0 이하(매도세 지배)이나 그 힘이 소멸하며 방향을 위로 돌릴 때 + 이평선 위
            if bear_power < 0.0 and bear_up == 1.0 and close > ema20:
                return 100.0
            return 0.0
        else:
            # 주가가 EMA 20을 무너뜨리고 내려갈 때 리스크 관리 청산
            if close < ema20:
                return 100.0
            return 30.0
