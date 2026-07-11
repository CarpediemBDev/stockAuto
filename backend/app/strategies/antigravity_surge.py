from app.strategies.base_strategy import BaseStrategy

class AntigravitySurge(BaseStrategy):
    """
    🚀 안티그래비티 서지 (Antigravity Surge)
    - OBV 지표가 전고점을 돌파해 세력 수급이 들어온 상태에서,
    - 52주 신고가 근접 수준의 쿨라매기식 양봉 돌파가 동시 포착될 때 진입.
    - 종가 기준 10일선(EMA10) 지지가 붕괴되거나 세력 이탈 시 탈출.
    """
    
    def __init__(self):
        super().__init__(name="🚀 안티그래비티 서지 (Antigravity Surge)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ema9 = self._safe_get(row, 'EMA9')
            
        obv_div = self._safe_get(row, 'OBV_divergence')
        
        if is_entry:
            is_near = self._safe_get(row, 'is_near_52w_high')
            momentum = self._safe_get(row, 'momentum_candles')
            
            # OBV 매집 돌파 + 52주 신고가 근접 + 쿨라매기식 돌파
            if obv_div > 0 and is_near and momentum:
                return 100.0
            return 0.0
        else:
            # 종가 기준 EMA9 위에 있으면서 OBV 수급이 여전히 유지될 때 홀딩
            if close >= ema9 and obv_div > 0:
                return 100.0
            return 30.0
