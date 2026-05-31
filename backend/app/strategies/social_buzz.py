import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class SocialBuzz(BaseStrategy):
    """
    소셜 버즈 모멘텀 전략 (Social Buzz Scan)
    - Reddit(WSB), Twitter(X) 언급량 500% 폭증(RVOL 3.0배 이상 및 단기 모멘텀 급증 시뮬레이션) 포착 시 광기 편승 매수.
    - 변동성이 크고 거품이 빠르게 빠지므로 초단기 9일선(EMA 9) 붕괴 시 즉시 전량 익절/손절 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 소셜버즈 모멘텀 (Social Buzz)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        buzz = self._safe_get(row, 'social_buzz_surge')
        
        if is_entry:
            # 소셜 버즈 폭발 모멘텀 진입
            if buzz == 1.0:
                return 100.0
            return 0.0
        else:
            ema9 = self._safe_get(row, 'EMA9')
            # 9일선 이탈 시 청산
            if close < ema9:
                return 100.0
            return 30.0
