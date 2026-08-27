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

        # 볼린저 밴드로 대체하지 않는다. 채널 돌파와 밴드 이탈은 다른 신호이고,
        # 갈아끼우면 이름만 돈키언인 채로 볼린저 전략을 측정하게 된다.
        # 채널값은 indicator_metrics.build_indicator_metrics가 두 경로 모두에 공급한다.

        if is_entry:
            # 채널 상단이 없으면 `close > 0.0`이 되어 모든 종목이 돌파로 판정된다.
            # 기준선이 실제로 존재할 때만 채점한다.
            if not d_high > 0.0:
                return 0.0

            # 20일 최고가 돌파 시 진입
            if close > d_high:
                return 100.0
            return 0.0
        else:
            # 10일 최저가 이상 유지 시 홀딩.
            # 하단이 없으면 이탈 판정이 불가능해 홀딩으로 남고, 실제 청산은 손절·트레일링
            # 스탑이 담당한다.
            if not d_low > 0.0:
                return 100.0
            if close >= d_low:
                return 100.0
            return 30.0
