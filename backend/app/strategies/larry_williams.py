import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class LarryWilliams(BaseStrategy):
    """
    윌리엄스 %R 단기 반전 전략 (Larry Williams %R Short-term)
    - %R 지표가 -90 이하(극단적 과매도) 구간을 탈출하여 -80을 상향 돌파할 때 단기 강세 전환으로 간주하고 매수.
    - %R 지표가 -20 이상(과매수) 영역을 하향 돌파 시 즉시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 윌리엄스 %R 단기반전 (Williams %R)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        wr = self._safe_get(row, 'williams_r')
        
        if is_entry:
            # 과매도 구역(-90) 탈출하여 -80 이상 상승 시 진입
            if wr >= -80.0 and wr < -20.0:
                return 100.0
            return 0.0
        else:
            # 과매수 구역(-20) 이하로 밀릴 시 청산
            if wr < -20.0 and wr > -80.0:
                return 100.0
            return 30.0
