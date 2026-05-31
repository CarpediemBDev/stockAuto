import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class FisherTransform(BaseStrategy):
    """
    피셔 트랜스폼 정점 반전 전략 (Fisher Transform Reversal)
    - 주가 변동 분포를 정규분포화하는 피셔 트랜스폼 지표가 극단 과매도 영역(-1.5 이하)에서 시그널선을 상향 교차할 때 바닥 포착 매수.
    - 극단 과매수 영역(+1.5 이상)에서 시그널선을 하향 돌파하며 꺾일 때 꼭대기 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 피셔트랜스폼 정점반전 (Fisher)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        fisher = self._safe_get(row, 'fisher')
        sig = self._safe_get(row, 'fisher_signal')
        
        if is_entry:
            # -1.5 이하 극과매도권 골든크로스 시 매수
            if fisher <= -1.5 and fisher > sig:
                return 100.0
            return 0.0
        else:
            # +1.5 이상 극과매수권 데드크로스 시 청산
            if fisher >= 1.5 and fisher < sig:
                return 100.0
            return 30.0
