from app.strategies.base_strategy import BaseStrategy

class Qullamaggie(BaseStrategy):
    """
    🛡️ 크리스찬 쿨라매기 돌파 전략 (Qullamaggie)
    - 52주 신고가 근접 수준에서 거래량이 폭발적으로 실린 3연속 상승 양봉 돌파 시 진입
    - EMA 9/20 정배열이 무너질 때 탈출
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 쿨라매기 돌파 (Qullamaggie)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        
        if is_entry:
            is_near = self._safe_get(row, 'is_near_52w_high')
            momentum = self._safe_get(row, 'momentum_candles')
            if is_near and momentum:
                return 100.0
            return 0.0
        else:
            if ema9 > ema20:
                return 100.0
            return 30.0
