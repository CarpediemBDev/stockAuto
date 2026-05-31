import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class VcpBreakout(BaseStrategy):
    """
    변동성 축소 패턴 돌파 전략 (Volatility Contraction Pattern - VCP)
    - 마크 미너비니의 VCP 패턴을 정밀 판정하여, 변동성 진폭이 점차 수축(20일 > 10일 > 5일)한 상태에서 5일 고가를 상향 돌파 시 매수.
    - 손절선을 2~3% 수준으로 꽉 죄어서 MDD를 완벽히 통제하는 것이 특장점.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 변동성 축소 패턴 (VCP)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        return 2.5  # VCP 특성에 맞춰 손절폭을 2.5%로 매우 좁게 제한

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            if self._safe_get(row, 'is_vcp_breakout'):
                return 100.0
            return 0.0
        else:
            ema20 = self._safe_get(row, 'EMA20')
            # 20일선 이탈 시 청산
            if close < ema20:
                return 100.0
            return 30.0
