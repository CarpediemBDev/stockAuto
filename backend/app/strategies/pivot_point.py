import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class PivotPoint(BaseStrategy):
    """
    피봇 포인트 반전 전략 (Pivot Point Floor Trader Method)
    - 당일 또는 전주 주가 변동 기준 지지선인 S1 또는 S2 레벨까지 하락 후 종가 기준 반등하는 눌림목 타점에서 진입.
    - 저항 벽인 R1 또는 R2 돌파 실패 및 상향 터치 시 즉시 수익 실현 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 피봇포인트 반전 (Pivot Point)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        s1 = self._safe_get(row, 'pivot_s1')
        s2 = self._safe_get(row, 'pivot_s2')
        r1 = self._safe_get(row, 'pivot_r1')
        r2 = self._safe_get(row, 'pivot_r2')
        
        if is_entry:
            # 주가가 1차 지지선 S1 또는 2차 지지선 S2 근방 또는 이하로 눌렸을 때 분할성 지지 반등 매수
            if s1 > 0 and close <= s1 * 1.005:
                return 100.0
            return 0.0
        else:
            # 1차 저항선 R1 또는 2차 저항선 R2 도달 시 청산
            if r1 > 0 and close >= r1 * 0.995:
                return 100.0
            return 30.0
