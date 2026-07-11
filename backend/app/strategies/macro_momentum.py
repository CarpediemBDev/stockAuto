from app.strategies.base_strategy import BaseStrategy

class MacroMomentum(BaseStrategy):
    """
    📡 매크로 듀얼 모멘텀 (Macro-Driven Dual Momentum)
    - 미 국채 10Y-2Y 스프레드와 기대 인플레이션(BEI) 지표를 결합하여 거시 경제 레짐을 판별합니다.
    - S&P500/NASDAQ 지수가 우상향(BULLISH)인 상태에서 경기 호황(골디락스/리플레이션)일 때만 적극 가동합니다.
    - 매크로 침체 경보 발생 혹은 지수 장기 이평선 붕괴 시 즉시 안전자산 피난(청산)을 강제합니다.
    """
    
    def __init__(self):
        super().__init__(name="📡 매크로 모멘텀 (Macro Momentum)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        spread = self._safe_get(row, 'yield_curve_spread', 0.1) # 10Y-2Y
        bei = self._safe_get(row, 'inflation_expectation', 2.0) # BEI
        
        # 경기침체 경보 (금리 역전 후 정상화 구간 & 물가 둔화)
        is_recession_alert = (spread >= 0.0 and spread < 0.2 and bei < 1.8)
        
        if is_entry:
            # 1. 지수 상승장 + 2. 침체 경보가 없을 때만 진입 허용
            if regime == "BULLISH" and not is_recession_alert:
                # 완만한 기대인플레이션 모멘텀 확인
                if bei >= 1.8 and close > self._safe_get(row, 'EMA20'):
                    return 100.0
            return 0.0
        else:
            # 장기 이평선 붕괴 또는 매크로 침체 경보 발생 시 청산
            if not is_recession_alert and close >= self._safe_get(row, 'EMA200', 0.0):
                return 100.0
            return 30.0
