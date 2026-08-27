from app.strategies.base_strategy import BaseStrategy

class OpeningRangeBreakout(BaseStrategy):
    """
    ⚡ 시초가 레인지 돌파 (Opening Range Breakout - ORB)
    - 장초반 30분간 형성된 고가(orb_high_30m)와 저가(orb_low_30m) 레인지를 이용합니다.
    - 30분 시초가 레인지 고가를 1.5배 이상의 거래량 급증을 수반해 돌파할 때 추세에 승차합니다.
    - 시초가 레인지 저가 또는 VWAP선 이탈 시 칼같이 손절 및 청산합니다.
    """
    
    def __init__(self):
        super().__init__(name="⚡ 시초가 레인지 돌파 (ORB)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        orb_high = self._safe_get(row, 'orb_high_30m')
        orb_low = self._safe_get(row, 'orb_low_30m')
        vwap = self._safe_get(row, 'VWAP', self._safe_get(row, 'EMA9'))
        
        # 볼린저 밴드로 대체하지 않는다. 밴드는 변동성 통계이고 시초 레인지는 당일
        # 장초반 30분의 실제 고저다. 갈아끼우면 이름만 ORB이고 실제로는 볼린저 돌파를
        # 측정하게 되어, 백테스트 성적이 이 전략의 성적이 아니게 된다.
            
        if is_entry:
            # 시초 레인지 고가가 없으면 `close > 0.0`이 되고, 거래량 필터도 volume_ma20
            # 기본값 1.0 때문에 `volume > 1.5`로 퇴화해 사실상 무조건 통과한다.
            # 두 값이 실제로 존재할 때만 채점한다.
            volume_baseline = self._safe_get(row, 'volume_ma20')
            if not orb_high > 0.0 or not volume_baseline > 0.0:
                return 0.0

            # 30분 시초 고가를 거래량과 함께 강하게 상방 돌파
            if close > orb_high and volume > volume_baseline * 1.5:
                return 100.0
            return 0.0
        else:
            # 시초 저가 또는 VWAP 지지선 유지 시 홀딩
            if close >= orb_low and close >= vwap:
                return 100.0
            return 30.0
