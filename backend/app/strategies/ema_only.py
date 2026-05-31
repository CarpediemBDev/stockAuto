from app.strategies.base_strategy import BaseStrategy

class EmaOnly(BaseStrategy):
    """
    EMA 이평정배열 전략 (EMA Only)
    - EMA 9일선이 20일선 위에 안착된 정배열 국면 내내 홀딩하며 시세를 발라내는 추세추종 전략
    """
    
    def __init__(self):
        super().__init__(name="EMA 이평정배열 (EMA Only)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        
        if is_entry:
            if ema9 > ema20:
                return 100.0
            return 0.0
        else:
            if ema9 > ema20:
                return 100.0
            return 30.0
