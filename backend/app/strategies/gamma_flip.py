import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class GammaFlip(BaseStrategy):
    """
    감마 플립 셋업 전략 (Gamma Flip / GEX)
    - 옵션 마켓메이커들이 매도/매수 헤지 방식을 상방 촉진으로 변환하는 'Zero Gamma'(EMA 20 상방) 진입 시 탑승.
    - 감마 밴드가 붕괴하여 Negative Gamma Zone(`gamma_flip == -1.0`)으로 진입하며 변동성 폭락이 감지되면 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 감마플립 셋업 (Gamma Flip)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        gex = self._safe_get(row, 'gamma_flip')
        
        if is_entry:
            # Positive Gamma Zone 진입 확인 시 매수
            if gex == 1.0:
                return 100.0
            return 0.0
        else:
            # Negative Gamma Zone으로 이탈 시 청산
            if gex == -1.0:
                return 100.0
            return 30.0
