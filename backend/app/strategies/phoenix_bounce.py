from app.strategies.base_strategy import BaseStrategy

class PhoenixBounce(BaseStrategy):
    """
    🦅 피닉스 바운스 (Phoenix Bounce)
    - 12개월 시장 주도 강세 상대강도(is_relative_strong)를 보인 대장주 중,
    - 15분봉 상 극단적 과매도(RSI <= 20)에 처했을 때,
    - 첫 번째 양봉(Close > Open) 발생과 함께 OBV 수급 반등(OBV_divergence > 0)이 
      감지되는 최적 바닥 찰나에 진입.
    - 단기 저항선(EMA20)에 도달하거나 과매도가 정상 회복(RSI >= 50)될 때 익절 및 탈출.
    """
    
    def __init__(self):
        super().__init__(name="🦅 피닉스 바운스 (Phoenix Bounce)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        open_price = self._safe_get(row, 'Open')
        rsi = self._safe_get(row, 'RSI')
        obv_div = self._safe_get(row, 'OBV_divergence')
        is_strong = self._safe_get(row, 'is_relative_strong')
        ema20 = self._safe_get(row, 'EMA20')
        
        if is_entry:
            # 주도 대장주 + RSI 과매도(20이하) + 첫 번째 양봉 반등 + OBV 수급 턴어라운드
            if is_strong > 0 and rsi <= 20.0 and close > open_price and obv_div > 0:
                return 100.0
            return 0.0
        else:
            # RSI가 50 이상 회복했거나 단기 저항선(EMA20)에 다다르면 청산
            if rsi >= 50.0 or close >= ema20:
                return 30.0
            return 100.0
