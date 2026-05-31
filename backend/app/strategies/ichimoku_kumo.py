import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class IchimokuKumo(BaseStrategy):
    """
    일목균형표 의운(구름대) 돌파 전략 (Ichimoku Kumo Breakout)
    - 주가가 선행스팬 구름대(Kumo)의 상단 위로 완전히 우상향 탈출 시 중장기 저항 탈출로 판단하고 진입.
    - 강력한 지지 기준선인 기준선(Kijun-sen) 이탈 시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 일목균형표 구름대돌파 (Ichimoku)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        span_a = self._safe_get(row, 'senkou_span_a')
        span_b = self._safe_get(row, 'senkou_span_b')
        
        if is_entry:
            # 종가가 구름대 상단을 완전 돌파 시 매수
            kumo_top = max(span_a, span_b)
            if kumo_top > 0 and close > kumo_top:
                return 100.0
            return 0.0
        else:
            kijun_sen = self._safe_get(row, 'kijun_sen')
            # 지지선인 기준선(Kijun-sen)을 하향 이탈 시 청산
            if close < kijun_sen:
                return 100.0
            return 30.0
