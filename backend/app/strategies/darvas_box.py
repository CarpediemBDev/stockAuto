import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class DarvasBox(BaseStrategy):
    """
    다바스 박스 매매 전략 (Darvas Box Theory)
    - 주가가 역사적 또는 중단기 신고가권에서 형성한 20일 박스권 상단(Box High)을 강하게 상향 돌파 시 진입.
    - 지지선 역할을 하는 박스권 하단(Box Low)을 깨고 내려갈 때 칼같이 손절하는 안정적 전략.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 다바스 박스 매매 (Darvas Box)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 3.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        darvas_high = self._safe_get(row, 'darvas_high')
        darvas_low = self._safe_get(row, 'darvas_low')
        
        if is_entry:
            # 박스 상단 돌파 시 매수
            if close > darvas_high:
                return 100.0
            return 0.0
        else:
            # 박스 하단 이탈 시 청산
            if close < darvas_low:
                return 100.0
            return 30.0
