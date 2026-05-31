import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class PairsTrading(BaseStrategy):
    """
    롱-숏 통계적 차익거래 전략 (Pairs Trading)
    - QQQ 지수와 대상 종목의 가격 비율(Spread)의 Z-Score를 분석하여 지수 대비 단기 과도 괴리(Z-Score <= -2.0) 발생 시 매입.
    - 스프레드가 다시 평균선(Z-Score >= 0.0)으로 복귀할 때 전량 청산 완료.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 롱-숏 통계적 차익거래 (Pairs Trading)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        zscore = self._safe_get(row, 'spread_zscore')
        
        if is_entry:
            # QQQ 대비 단기 이격도가 -2.0 이하로 급락했을 때 매수 진입 (롱)
            if zscore <= -2.0:
                return 100.0
            return 0.0
        else:
            # Z-Score가 0.0 이상으로 복귀하여 스프레드가 평균 수렴 시 청산
            if zscore >= 0.0:
                return 100.0
            return 30.0
