from app.strategies.base_strategy import BaseStrategy

class RsiBbOnly(BaseStrategy):
    """
    RSI 볼린저밴드 극점 전략 (RSI BB Only)
    - 14일 RSI 과매도와 주가가 볼린저 밴드 하단을 극단적으로 이탈할 때 반등을 노려 매수
    - RSI가 40 이상 회복되거나 9일선 안착 시 홀딩 후 붕괴 시 탈출
    """
    
    def __init__(self):
        super().__init__(name="⚙️ RSI 볼린저밴드 (RSI BB Only)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            if self._safe_get(row, 'is_rsi_bb_extreme'):
                return 100.0
            return 0.0
        else:
            rsi = self._safe_get(row, 'RSI')
            if rsi >= 40.0 or close > self._safe_get(row, 'EMA9'):
                return 100.0
            return 30.0
