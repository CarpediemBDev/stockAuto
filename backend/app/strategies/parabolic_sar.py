import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ParabolicSar(BaseStrategy):
    """
    파라볼릭 SAR 반전 스윙 전략 (Parabolic SAR Trend Flip)
    - Parabolic SAR 지표가 주가 밑으로 전환(Bullish Flip)될 때 모멘텀 우상향 추세로 보고 진입.
    - 반대로 SAR 지표가 주가 위로 꺾여서 매도 시그널 전환(Bearish Flip)될 때 정밀 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 파라볼릭 SAR 반전 (Parabolic SAR)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        direction = self._safe_get(row, 'sar_direction')
        
        if is_entry:
            # SAR 점이 주가 하단에 뜨는 상승 추세(direction == 1) 시 진입
            if direction == 1:
                return 100.0
            return 0.0
        else:
            # SAR 점이 주가 상단에 뜨는 하락 추세(direction == -1)로 꺾일 시 청산
            if direction == -1:
                return 100.0
            return 30.0
