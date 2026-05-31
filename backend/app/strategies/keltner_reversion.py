import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class KeltnerReversion(BaseStrategy):
    """
    켈트너 채널 상하단 반전 전략 (Keltner Channel Mean Reversion)
    - 주가가 켈트너 채널의 하단 밴드를 일시적 이탈(Under-shoot)했다가 종가 기준 채널 내부로 재진입(`keltner_reentry == 1.0`)할 때 반등 진입.
    - 채널의 최상단 밴드(Keltner Upper) 터치 또는 그 이상 오버슈팅 시 전량 완벽 익절 청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 켈트너채널 반전 (Keltner Reversion)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 1.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            # 켈트너 채널 하단 이탈 후 내부 재진입 성공 시 매수
            if self._safe_get(row, 'keltner_reentry') == 1.0:
                return 100.0
            return 0.0
        else:
            upper = self._safe_get(row, 'keltner_upper')
            # 상단 채널 밴드 터치 시 매도
            if upper > 0 and close >= upper:
                return 100.0
            return 30.0
