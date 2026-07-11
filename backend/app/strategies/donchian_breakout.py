from app.strategies.base_strategy import BaseStrategy

class DonchianBreakout(BaseStrategy):
    """
    📊 돈키언 채널 추세 추종 (Donchian Breakout)
    - 리처드 돈키언의 고전적 채널 돌파 전략입니다.
    - 종가가 최근 20일간의 최고가(donchian_high_20)를 돌파할 때 진입합니다.
    - 종가가 최근 10일간의 최저가(donchian_low_10)를 이탈할 때 전량 매도 및 청산합니다.
    """
    
    def __init__(self):
        super().__init__(name="📊 돈키언 채널 돌파 (Donchian Breakout)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        d_high = self._safe_get(row, 'donchian_high_20')
        d_low = self._safe_get(row, 'donchian_low_10')
        
        # fallback if features are not pre-calculated
        if d_high == 0.0:
            d_high = self._safe_get(row, 'BB_upper')
        if d_low == 0.0:
            d_low = self._safe_get(row, 'BB_lower')
            
        if is_entry:
            # 20일 최고가 돌파 시 진입
            if close > d_high:
                return 100.0
            return 0.0
        else:
            # 10일 최저가 이상 유지 시 홀딩
            if close >= d_low:
                return 100.0
            return 30.0
