from app.strategies.base_strategy import BaseStrategy

class OrbOnly(BaseStrategy):
    """
    토비 크라벨 ORB 시가 돌파 전략 (ORB Only)
    - 당일 시가를 강한 거래대금 및 수급 가속(RVOL >= 1.2)과 함께 장초반 돌파할 때 탑승하는 당일 가속 탄력 전략
    """
    
    def __init__(self):
        super().__init__(name="토비크라벨 ORB (ORB Only)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        rvol = self._safe_get(row, 'RVOL')
        open_val = self._safe_get(row, 'Open')
        
        if is_entry:
            if close > open_val and rvol >= 1.2:
                return 100.0
            return 0.0
        else:
            if close >= open_val or rvol >= 1.1:
                return 100.0
            return 30.0
