import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class PremarketBreakout(BaseStrategy):
    """
    프리마켓 고점 돌파 (Pre-market Breakout) 단타 전략
    - 정규장 오픈 직후(09:00 ~ 11:00 EST) 프리마켓의 고점 밴드를 강한 거래량으로 돌파할 때 진입
    """
    
    def __init__(self, name: str = "Pre-market Breakout"):
        super().__init__(name)
        self.base_allocation_pct = 0.30
        self.min_smart_exit_profit = 3.0
        
    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        # 이 전략은 실시간 분봉 또는 틱 데이터에서
        # 프리마켓(04:00~09:30 EST) 고가와 최대 거래량을 비교하여 작동합니다.
        # 데이터가 충분하지 않거나 형식이 맞지 않으면 기본 스코어를 반환합니다.
        
        current_price = self._safe_get(row, 'close', 0.0)
        premarket_high = self._safe_get(row, 'premarket_high', 0.0)
        current_volume = self._safe_get(row, 'volume', 0.0)
        premarket_max_volume = self._safe_get(row, 'premarket_max_volume', 0.0)
        
        if current_price == 0 or premarket_high == 0:
            return 0.0
            
        score = 0.0
        
        # 1. 프리마켓 고점 돌파 확인
        if current_price > premarket_high:
            score += 50.0
            
            # 2. 거래량이 프리마켓 최대 거래량(저항 형성시 거래량)보다 많은가?
            if current_volume > premarket_max_volume and premarket_max_volume > 0:
                score += 50.0
        
        # 레짐에 따른 보정
        if regime == "BEARISH":
            score *= 0.8
            
        return min(score, 100.0)
        
    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        # 기본 ATR 연동을 위해 보수적으로 설정 (최소 2.5%)
        return max(2.5, super().get_stop_loss_pct(atr, price))
