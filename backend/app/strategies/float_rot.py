import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class FloatRotation(BaseStrategy):
    """
    ⚙️ 유통주 회전율 돌파 (Float Rotation)
    마스터 70대 전략 대항전을 위한 독창적 신규 전략 클래스 모듈입니다.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 유통주 회전율 돌파 (Float Rotation)")
        self.base_allocation_pct = 0.4
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        # 기본 필터링 조건
        is_penny = self._safe_get(row, 'is_penny')
        if is_penny == 0.0: return 0.0
        
        trigger_val = self._safe_get(row, 'is_float_rotation')
        
        if is_entry:
            if trigger_val == 1.0:
                return 100.0
            return 0.0
        else:
            # 청산 시그널
            ema20 = self._safe_get(row, 'EMA20')
            if close < ema20:
                return 100.0
            return 30.0
