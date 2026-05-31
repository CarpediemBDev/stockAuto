import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class OrderFlow(BaseStrategy):
    """
    볼륨 델타 불균형 전략 (Order Flow Delta)
    - 체결창의 실질적 시장가 매수세 vs 시장가 매도세의 힘을 캔들 몸통 가중치 비율로 모델링하여, 순매수 델타가 양수이고 수급(`RVOL >= 1.2`)이 동반될 때 진입.
    - 순매도 델타가 음수(`order_flow_delta < 0`)로 돌아서며 허수 주문 매도폭탄이 실체화될 때 전량 대피 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 볼륨델타 오더플로 (Order Flow)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        delta = self._safe_get(row, 'order_flow_delta')
        rvol = self._safe_get(row, 'RVOL')
        
        if is_entry:
            # 실질적 체결창 순매수세 양수 안착 & 수급 동반 시 진입
            if delta > 0.0 and rvol >= 1.2:
                return 100.0
            return 0.0
        else:
            # 순체결 델타가 음수로 돌아서서 매도 지배 시 청산
            if delta < 0.0:
                return 100.0
            return 30.0
