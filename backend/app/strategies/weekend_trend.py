import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class WeekendTrend(BaseStrategy):
    """
    주말 추세 매매 전략 (Weekend Trend Trader)
    - 52주 신고가 근처에서 노이즈를 극복하고 올라온 강세 주도주를 포착하여 진입.
    - 장기 추세선인 120일선(EMA 120)을 붕괴시키지 않는 이상 극도의 장기 추세 추종을 지향.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 주말 추세 매매 (Weekend Trend)")
        self.base_allocation_pct = 0.30
        self.min_smart_exit_profit = 5.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            # 52주 신고가 돌파 근접(2% 이내 또는 상방 돌파) 시 진입
            if self._safe_get(row, 'is_near_52w_high'):
                return 100.0
            return 0.0
        else:
            ema120 = self._safe_get(row, 'EMA120')
            
            # 장기 추세선인 EMA 120 붕괴 시 청산 (신규 상장주 NaN 방어)
            if not pd.isna(ema120) and close < ema120:
                return 100.0
            return 30.0
