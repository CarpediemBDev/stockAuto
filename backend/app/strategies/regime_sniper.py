from app.strategies.base_strategy import BaseStrategy

class RegimeSniper(BaseStrategy):
    """
    🎯 레짐 스나이퍼 (Regime Sniper)
    - QQQ 지수가 상승세인 상승 레짐(BULLISH) 상태에서만 가동.
    - 볼린저 밴드 폭이 수축했다가 상단 채널을 거래량과 함께 강하게 뚫고 나가는 
      is_squeeze_breakout 신호 발생 시 진입.
    - 볼린저 밴드 중심선(EMA20)을 하향 이탈할 때 칼같이 손절 및 청산.
    """
    
    def __init__(self):
        super().__init__(name="🎯 레짐 스나이퍼 (Regime Sniper)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ema20 = self._safe_get(row, 'EMA20')
        
        if is_entry:
            # 대세 상승장(BULLISH) + 밴드 스퀴즈 상방 돌파 동시 만족
            if regime == "BULLISH" and self._safe_get(row, 'is_squeeze_breakout'):
                return 100.0
            return 0.0
        else:
            # 밴드 중심선(EMA20) 위에 머무는 동안 홀딩
            if close >= ema20:
                return 100.0
            return 30.0
