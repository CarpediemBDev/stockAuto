import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class MaxPain(BaseStrategy):
    """
    맥스 페인 반전 전략 (Max Pain Theory)
    - 옵션 만기일 주간(`is_expiry_week == 1.0`)에 주가가 옵션 매도 세력의 최대 이익 지점인 Max Pain Price(`max_pain_price`)보다 3% 이상 과도하게 저평가되어 있을 때 진입.
    - 만기일 자석 효과로 인해 평단가 부근(`Close >= max_pain_price`)에 도달 시 전량 청산 완료.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 맥스페인 반전 (Max Pain)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        is_expiry = self._safe_get(row, 'is_expiry_week')
        max_pain = self._safe_get(row, 'max_pain_price')
        
        if is_entry:
            # 옵션 만기 주간이면서 가격이 맥스 페인 가격보다 3% 이상 저렴할 때 진입
            if is_expiry == 1.0 and max_pain > 0 and close <= max_pain * 0.97:
                return 100.0
            return 0.0
        else:
            # 맥스 페인 자석 가격 도달 또는 만기 주간이 지나면 청산
            if max_pain > 0 and close >= max_pain:
                return 100.0
            return 30.0
