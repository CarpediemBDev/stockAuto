import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class VolumeProfile(BaseStrategy):
    """
    매물대 프로파일 POC 전략 (Volume Profile POC)
    - 역사적으로 가장 많은 매매 대금이 쌓인 매물 지지대 장벽인 POC(`volume_poc`)선까지 주가가 정밀 눌림목 조정을 받을 때 분할 매수.
    - 가장 두터운 매물대 벽인 POC선이 최종 붕괴되어 -2.0% 하향 돌파 시 즉시 수호 손절/청산.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 매물대 프로파일 (Volume POC)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        poc = self._safe_get(row, 'volume_poc')
        
        if is_entry:
            # 주가가 매물대 POC 벽 근처(1.5% 이내)로 눌려 지지 성립 시 진입
            if poc > 0 and close <= poc * 1.015 and close >= poc * 0.995:
                return 100.0
            return 0.0
        else:
            # 매물대 지지 장벽이 완전히 뚫리고 내려갔을 때 청산
            if poc > 0 and close < poc * 0.98:
                return 100.0
            return 30.0
