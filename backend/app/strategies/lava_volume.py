from app.strategies.base_strategy import BaseStrategy

class LavaVolume(BaseStrategy):
    """
    ⚡ 매물대 POC 및 VWAP 돌파 (LAVA Volume)
    - 매물분포(Volume Profile) 상 거래가 가장 집중된 POC(Point of Control) 라인을 돌파하고,
    - 당일 VWAP(거래량 가중평균선)을 1.5% 이상 거래량을 동반해 상향 돌파 시 진입.
    - 종가가 VWAP 하향 붕괴 시 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚡ 매물대 POC/VWAP 돌파 (Lava Volume)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        vwap = self._safe_get(row, 'VWAP')
        if vwap == 0.0:
            vwap = self._safe_get(row, 'EMA9') # fallback
            
        dev = (close / vwap - 1.0) * 100.0 if vwap > 0 else 0.0
        poc_dist = self._safe_get(row, 'poc_distance_pct', -1.0)
        
        if is_entry:
            # POC 매물대 위에 안착하고 VWAP 대비 +1.5% 이상 양봉 분출
            if poc_dist >= 0.0 and dev >= 1.5 and close > self._safe_get(row, 'Open'):
                return 100.0
            return 0.0
        else:
            # 종가 기준 당일 VWAP 지지 붕괴 시 청산
            if close >= vwap:
                return 100.0
            return 30.0
