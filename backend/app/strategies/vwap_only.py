import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class VwapOnly(BaseStrategy):
    """
    VWAP 세력지지선 전략 (VWAP Only)
    - 당일 거래대금 가중평균 가격인 VWAP 세력선 위에서 주가가 견고하게 노는 지지력 거래
    """
    
    def __init__(self):
        super().__init__(name="⚙️ VWAP 세력지지선 (VWAP Only)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        vwap = self._safe_get(row, 'VWAP', default=float('nan'))
        
        if is_entry:
            if not pd.isna(vwap) and close > vwap:
                return 100.0
            return 0.0
        else:
            if not pd.isna(vwap) and close >= vwap:
                return 100.0
            return 30.0
