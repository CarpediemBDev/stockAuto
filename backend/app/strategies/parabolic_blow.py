import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ParabolicBlowoff(BaseStrategy):
    """
    ⚙️ 파라볼릭 폭발 청산 (Parabolic Blow)
    마스터 70대 전략 대항전을 위한 독창적 신규 전략 클래스 모듈입니다.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 파라볼릭 폭발 청산 (Parabolic Blow)")
        self.base_allocation_pct = 0.0
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        # 이 전략은 진입하지 않고 보유 중인 자산의 위험 극점 엑시트만 담당합니다.
        if is_entry:
            return 0.0
        
        climax = self._safe_get(row, 'is_parabolic_climax')
        if climax == 1.0:
            return 100.0  # 청산 스코어 최대치 리턴
        return 30.0
