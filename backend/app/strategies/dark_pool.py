import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class DarkPool(BaseStrategy):
    """
    다크풀 대량 체결 추적 전략 (Dark Pool Block Print)
    - 비공개 대량 블록딜 평단가(`dark_pool_price`) 지지 벽을 추적하여, 해당 가격대 근처로 주가가 조정을 받을 때 분할 매집 진입.
    - 기관의 평단 지지선이 깨지고 2% 이상 하락할 때 정밀 청산(손절).
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 다크풀 블록딜 (Dark Pool Scan)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        dp_price = self._safe_get(row, 'dark_pool_price')
        
        if is_entry:
            # 주가가 기관 블록딜 가격의 1.0% 이내 지지권까지 눌렸을 때 진입
            if dp_price > 0 and close <= dp_price * 1.01:
                return 100.0
            return 0.0
        else:
            # 블록딜 지지벽이 붕괴되어 -2.0% 하향 돌파 시 청산
            if dp_price > 0 and close < dp_price * 0.98:
                return 100.0
            return 30.0
