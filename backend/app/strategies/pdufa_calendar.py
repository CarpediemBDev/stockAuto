import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class PdufaCalendar(BaseStrategy):
    """
    바이오 임상 캘린더 스윙 전략 (PDUFA Calendar Run)
    - FDA 예정일(90일 주기 시뮬레이션) 60~85일 전에 진입하여 기대감으로 인한 주가 상승을 공략.
    - 실제 승인 결과 도박 배제를 위해 예정일 직전(일수 < 5 또는 > 85)에 칼같이 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ PDUFA 임상스윙 (PDUFA Run)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        days = self._safe_get(row, 'days_to_pdufa')
        
        if is_entry:
            # FDA PDUFA 승인일 60~85일 전 구간 (기대감 축적 단계) 진입
            if 60.0 <= days <= 85.0:
                return 100.0
            return 0.0
        else:
            # 승인 임계일 직전 또는 결과 발표 도박을 피하기 위해 청산
            if days < 5.0 or days > 85.0:
                return 100.0
            return 30.0
