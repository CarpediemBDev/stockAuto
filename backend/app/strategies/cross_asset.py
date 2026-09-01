import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class CrossAsset(BaseStrategy):
    """
    자산간 모멘텀 필터 전략 (Cross-Asset Yield Filter)
    - 미 국채 금리 및 달러 인덱스 추세 전환에 따른 주식 장세 매크로 필터(`cross_asset_ok == 1.0`)와 주가 EMA 20 정배열 결합 시 진입.
    - 매크로 하락 전환(`cross_asset_ok == 0.0`) 또는 20일선 이탈 시 전면 관망/청산 실행.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 자산간 금리필터 (Cross Asset)")
        self.base_allocation_pct = 0.35
        self.min_smart_exit_profit = 2.5

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        macro_ok = self._safe_get(row, 'cross_asset_ok')
        ema20 = self._safe_get(row, 'EMA20')
        
        if is_entry:
            # 매크로 장세가 양호하고 주가 역시 20일선 위에 안착 시 진입
            if macro_ok == 1.0 and close > ema20:
                return 100.0
            return 0.0
        else:
            # 엔진은 is_signal_collapsed로 "낮은 점수 = 청산"을 읽는다(BaseStrategy).
            # 매크로 약세 전환이나 20일선 이탈이 청산 사유이므로 그때 낮은 점수를 낸다.
            # 2026-09-01 이전에는 반대로 돌려주고 있어, 필드가 배선되는 순간
            # 정상 구간에서 즉시 매도하고 악화 구간에서 버티는 전략이 될 상태였다.
            if macro_ok == 0.0 or close < ema20:
                return 0.0
            return 100.0
