import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class HeikinAshi(BaseStrategy):
    """
    하이킨아시 추세 추종 전략 (Heikin-Ashi Trend Rider)
    - 하이킨아시 캔들 필터를 통해 가격 노이즈를 평활화하고, 강한 추세 신호인 양봉 캔들 및 아래꼬리가 없는 상태(`HA_Low == HA_Open`)에서 매수 진입.
    - 캔들 색상이 음봉으로 전환되면 즉시 대피하여 하락을 미연에 회피.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 하이킨아시 추세추종 (Heikin-Ashi)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        ha_open = self._safe_get(row, 'HA_Open')
        ha_close = self._safe_get(row, 'HA_Close')
        ha_low = self._safe_get(row, 'HA_Low')
        
        if is_entry:
            # 하이킨아시 양봉 & 아래꼬리가 없음 (강한 매수세의 연속)
            if ha_close > ha_open and abs(ha_low - ha_open) < 0.0001:
                return 100.0
            return 0.0
        else:
            # 하이킨아시 캔들이 빨간색(음봉)으로 전환되면 탈출
            if ha_close < ha_open:
                return 100.0
            return 30.0
