from app.strategies.base_strategy import BaseStrategy

class RegimeSwitching(BaseStrategy):
    """
    👑 마스터 레짐스위칭 (Regime Switching) [🏆 통합 1위]
    - QQQ 지수가 상승장(BULLISH)일 때는 극강의 공격수 'EMA 이평정배열 (EMA Only)'로 질주
    - QQQ 지수가 하락/횡보장(BEARISH/NEUTRAL)일 때는 지옥의 방패 '쿨라매기 돌파' 기법으로 옷을 갈아입음
    - 자본 분할 및 익절선 등은 표준 v2.0 스펙 공유
    """
    
    def __init__(self):
        super().__init__(name="👑 마스터 레짐스위칭 (Regime Switching)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        
        # 필수 거래대금 필터
        if close * volume < 7400.0:
            return 0.0
            
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        
        if regime == "BULLISH":
            # 🚀 상승장 레짐: EMA 이평 정배열 추세 추종
            if is_entry:
                if ema9 > ema20:
                    return 100.0
                return 0.0
            else:
                if ema9 > ema20:
                    return 100.0
                return 30.0  # 이탈 시 감점으로 조기 청산 유도
        else:
            # 🛡️ 하락/횡보장 레짐: 쿨라매기 돌파 (신고가 근접 + 양봉 모멘텀 저격)
            if is_entry:
                is_near = self._safe_get(row, 'is_near_52w_high')
                momentum = self._safe_get(row, 'momentum_candles')
                if is_near and momentum:
                    return 100.0
                return 0.0
            else:
                if ema9 > ema20:
                    return 100.0
                return 30.0
