from app.strategies.base_strategy import BaseStrategy

class ChaikinAtr(BaseStrategy):
    """
    ⚡ Chaikin-ATR 수축팽창 돌파 (Chaikin ATR Breakout)
    - Chaikin Volatility (CV) 지표가 -15 이하로 극대 수축하여 에너지가 응축된 이후,
    - 돈키언 채널 상단을 강하게 돌파하며 CV가 양수(+)로 전환 및 팽창을 개시할 때 진입.
    - 단기 10일선(EMA10) 붕괴 시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚡ Chaikin-ATR 돌파 (Chaikin ATR)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        cv = self._safe_get(row, 'chaikin_volatility', 0.0)
        donchian_high = self._safe_get(row, 'donchian_high_20')
        if donchian_high == 0.0:
            donchian_high = self._safe_get(row, 'BB_upper') # fallback
            
        ema10 = self._safe_get(row, 'EMA10')
        if ema10 == 0.0:
            ema10 = self._safe_get(row, 'EMA9')
            
        if is_entry:
            # 채널 상단(폴백 포함)과 거래량 기준선이 없으면 `close > 0.0`, `volume > 1.2`가 되어
            # 두 조건 모두 항상 참으로 퇴화한다. 기준값이 실제로 있을 때만 채점한다.
            volume_baseline = self._safe_get(row, 'volume_ma20')
            if not donchian_high > 0.0 or not volume_baseline > 0.0:
                return 0.0

            # 변동성 극수축 후 거래량 실린 돈키언 채널 돌파 + 변동성 증가 개시
            if cv > 0.0 and close > donchian_high and volume > volume_baseline * 1.2:
                return 100.0
            return 0.0
        else:
            # 10일선 유지 하에서 홀딩
            if close >= ema10:
                return 100.0
            return 30.0
