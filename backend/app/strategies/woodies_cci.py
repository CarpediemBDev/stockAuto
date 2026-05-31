import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class WoodiesCci(BaseStrategy):
    """
    우디 CCI 모멘텀 전략 (Woodies CCI)
    - CCI 지표가 -100 이하의 극단 과매도 영역을 탈출하고 상향 돌파할 때 단기 매수 진입.
    - CCI 지표가 +100 이상의 과매수 영역을 하향 돌파하여 힘이 빠질 때 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 우디 CCI 고스트 (Woodies CCI)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        cci = self._safe_get(row, 'cci')
        
        if is_entry:
            # -100 상향 돌파 시 진입
            if cci > -100.0 and cci - self._safe_get(row, 'cci_prev', default=cci) > 5.0: # 약세 극점 탈출 시그널
                return 100.0
            # 백업 단순 과매도 탈출
            if cci > -100.0 and cci < -50.0:
                return 90.0
            return 0.0
        else:
            # +100 하향 돌파 시 청산
            if cci < 100.0 and cci > 50.0:
                return 100.0
            return 30.0
