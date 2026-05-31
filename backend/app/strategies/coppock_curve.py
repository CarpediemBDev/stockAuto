import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class CoppockCurve(BaseStrategy):
    """
    코폭 커브 장기 바닥 전략 (Coppock Curve)
    - 거시적 시장 투매가 끝나는 진바닥을 포착하기 위해, 코폭 커브 지표가 0 이하 극단에서 우상향 반전(`coppock_up == 1.0`)할 때 진입.
    - 코폭 커브가 0 이상 구간에서 우하향 꺾여서 추세가 둔화될 때 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 코폭커브 장기바닥 (Coppock Curve)")
        self.base_allocation_pct = 0.30
        self.min_smart_exit_profit = 3.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        coppock = self._safe_get(row, 'coppock')
        coppock_up = self._safe_get(row, 'coppock_up')
        
        if is_entry:
            # 0선 아래 음수 영역에서 커브 우상향 턴 업할 때 매집 진입
            if coppock < 0.0 and coppock_up == 1.0:
                return 100.0
            return 0.0
        else:
            # 0선 위 양수 영역에서 커브 우하향 턴 다운할 때 청산
            if coppock > 0.0 and coppock_up == 0.0:
                return 100.0
            return 30.0
