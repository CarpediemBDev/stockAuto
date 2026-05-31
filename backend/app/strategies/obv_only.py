from app.strategies.base_strategy import BaseStrategy

class ObvOnly(BaseStrategy):
    """
    차트픽 OBV 매집 전략 (OBV Only)
    - On-Balance Volume 지표의 상승 다이버전스(세력 매집) 발생 시 매수
    - 매집이 소멸하거나 9일선 이탈 시 탈출
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 차트픽 OBV 매집 (OBV Only)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        obv_div = self._safe_get(row, 'OBV_divergence')
        
        if is_entry:
            if obv_div > 0:
                return 100.0
            return 0.0
        else:
            if obv_div > 0 or close > self._safe_get(row, 'EMA9'):
                return 100.0
            return 30.0
