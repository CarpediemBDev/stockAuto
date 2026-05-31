import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class Rsi2Connors(BaseStrategy):
    """
    래리 코너스 RSI 2 극단 과매도 평균회귀 전략 (RSI 2 Only)
    - 상승장(BULLISH) 레짐 상태에서 단기 과매도 국면(RSI 2 < 10)에 탑승한 뒤 5일 이평선(EMA 5)을 돌파할 때 조기 익절하는 스나이핑 기법
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 래리코너스 RSI 2 (RSI 2 Only)")
        self.min_smart_exit_profit = 1.0  # 1.0% 수준의 아주 짧은 조기 청산 마진 허용

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        rsi2 = self._safe_get(row, 'RSI2', default=float('nan'))
        
        if is_entry:
            if regime == "BULLISH" and not pd.isna(rsi2) and rsi2 < 10.0:
                return 100.0
            return 0.0
        else:
            ema5 = self._safe_get(row, 'EMA5', default=float('nan'))
            # 5일 이평선을 종가가 상향 돌파 시 즉시 전량 청산 완료 (EMA5 위에 있으면 홀딩, 뚫고 밑으로 내려가면 청산)
            if not pd.isna(ema5) and close < ema5:
                return 100.0
            return 30.0
