import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ZscoreReversion(BaseStrategy):
    """
    Z-스코어 평균 회귀 전략 (Z-Score Mean Reversion)
    - 20일 이동평균선 대비 주가의 표준편차가 과매도 임계값인 -2.5 이하로 극단 이탈할 때 반등 매수 집행.
    - 주가가 평균인 20일 이동평균선(Z-Score >= 0.0)에 복귀하면 완벽히 익절/청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ Z-스코어 평균회귀 (Z-Score Reversion)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        zscore = self._safe_get(row, 'zscore')
        
        if is_entry:
            # 주가가 자기 이평선 대비 2.5 표준편차 이하로 깨졌을 때 역발상(Contrarian) 매수
            if zscore <= -2.5:
                return 100.0
            return 0.0
        else:
            # 이평선(평균) 복귀 완료 시 청산
            if zscore >= 0.0:
                return 100.0
            return 30.0
