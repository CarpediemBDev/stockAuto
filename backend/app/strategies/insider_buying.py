import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class InsiderBuying(BaseStrategy):
    """
    내부자 지분 매수 추적 전략 (Insider Buying Scan)
    - 대주주 및 대리인 장내 매집 프록시 지표(60일 신저가권에서 대량 RVOL 1.5배 이상 매수 지지) 발생 시 스마트머니 편승 진입.
    - 주요 이평선인 EMA 20선 이탈 시 수호 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 내부자 지분매수 (Insider Scan)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        insider = self._safe_get(row, 'insider_signal')
        
        if is_entry:
            # 60일 바닥권에서 대량의 내부자 거래 지지 성립 시 진입
            if insider == 1.0:
                return 100.0
            return 0.0
        else:
            ema20 = self._safe_get(row, 'EMA20')
            # 20일선 무너질 시 손절/청산
            if close < ema20:
                return 100.0
            return 30.0
