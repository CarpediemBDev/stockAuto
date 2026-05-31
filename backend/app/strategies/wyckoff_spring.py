import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class WyckoffSpring(BaseStrategy):
    """
    와이코프 스프링 트랩 전략 (Wyckoff Spring Trap)
    - 전저점을 이탈(Stop Hunting) 시켜 매물을 받아먹은 직후, 곧바로 20일 최저 지지선을 거래량과 함께 강하게 상방 재탈입할 때 매수 진입.
    - 주요 장단기 이동평균선인 EMA 20선 이탈 시 수호 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 와이코프 스프링 (Wyckoff Spring)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        spring = self._safe_get(row, 'is_wyckoff_spring')
        
        if is_entry:
            # 개미 털기 트랩 확인 후 빠른 재탈입 확인 시 매수
            if spring == 1.0:
                return 100.0
            return 0.0
        else:
            ema20 = self._safe_get(row, 'EMA20')
            # 20일선 이탈 시 청산
            if close < ema20:
                return 100.0
            return 30.0
