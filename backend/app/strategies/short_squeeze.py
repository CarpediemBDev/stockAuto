import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ShortSqueeze(BaseStrategy):
    """
    숏 스퀴즈 가속 전략 (Short Squeeze Metrics)
    - 공매도 비중이 많은 종목이 거래량 급증(RVOL >= 2.0)을 동반하고 10일 고가를 상향 돌파하며 숏 스퀴즈 랠리를 시동할 때 탑승.
    - 변동성이 극도로 높으므로 초단기 9일선(EMA 9) 붕괴 시 즉시 탈출.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 숏스퀴즈 가속 (Short Squeeze)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        squeeze = self._safe_get(row, 'is_squeeze_setup')
        
        if is_entry:
            # 대량의 공매도 숏 커버링 가속 돌파 신호 포착
            if squeeze == 1.0:
                return 100.0
            return 0.0
        else:
            ema9 = self._safe_get(row, 'EMA9')
            # 9일선 이탈 시 청산
            if close < ema9:
                return 100.0
            return 30.0
