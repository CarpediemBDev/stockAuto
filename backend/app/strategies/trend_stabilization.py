import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class TrendStabilization(BaseStrategy):
    """
    추세 안정화 눌림목 (Trend Stabilization Pullback) 단타 전략
    - 정규장 오픈 후 30분간(09:30~10:00 EST)의 변동성이 진정되고 형성된 우상향 파동의 저점(눌림목) 공략
    """
    
    def __init__(self, name: str = "Trend Stabilization Pullback"):
        super().__init__(name)
        self.base_allocation_pct = 0.30
        self.min_smart_exit_profit = 3.0
        
    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        # 전일비 상승률 및 09:30~10:00 파동 저점 추세선 정보가 필요
        current_price = self._safe_get(row, 'close', 0.0)
        change_pct = self._safe_get(row, 'change_pct', 0.0)
        trendline_support = self._safe_get(row, 'trendline_support', 0.0)
        is_uptrend = self._safe_get(row, 'is_uptrend', False)
        
        if current_price == 0 or trendline_support == 0:
            return 0.0
            
        score = 0.0
        
        # 1. 전일 대비 5% ~ 15% 상승 조건 (강세 유지)
        if 5.0 <= change_pct <= 15.0:
            score += 30.0
            
        # 2. 10시 이후 우상향 추세인지 확인
        if is_uptrend:
            score += 30.0
            
            # 3. 현재가가 상승 파동 추세선(저점 연결선)에 근접하는지 (-1% ~ +1% 이내)
            distance_pct = ((current_price - trendline_support) / trendline_support) * 100
            if -1.0 <= distance_pct <= 1.0:
                score += 40.0
                
        # 레짐 보정
        if regime == "BEARISH":
            score *= 0.7
            
        return min(score, 100.0)
        
    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        # 넉넉하게 3% 또는 기본값 사용
        return max(3.0, super().get_stop_loss_pct(atr, price))
