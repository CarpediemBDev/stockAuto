from app.strategies.base_strategy import BaseStrategy

class BbSqueeze(BaseStrategy):
    """
    존 카터 TTM 스퀴즈 변동성 돌파 전략 (BB Squeeze)
    - 볼린저 밴드가 켈트너 채널 내부로 응축하는 횡보 스퀴즈 구간을 겪은 후 상방을 강하게 뚫을 때 추세 탑승
    - 단기 9일선(EMA 9) 붕괴 시 청산
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 존카터 BB스퀴즈 (TTM Squeeze)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            if self._safe_get(row, 'is_squeeze_breakout'):
                return 100.0
            return 0.0
        else:
            ema9 = self._safe_get(row, 'EMA9')
            if close >= ema9:
                return 100.0
            return 30.0
