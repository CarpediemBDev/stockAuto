from app.strategies.base_strategy import BaseStrategy

class HurstAdaptive(BaseStrategy):
    """
    🧬 허스트 지수 적응형 엔진 (Hurst-Adaptive Dual Engine)
    - 실시간 계산된 허스트 지수(hurst_exponent)에 따라 추세 모드와 역추세 모드를 스위칭합니다.
    - H > 0.55 (추세장) : 모멘텀 추세 추종 돌파 엔진 가동
    - H < 0.45 (평균회귀장) : 과매도 극점 회귀 엔진 가동
    - 0.45 <= H <= 0.55 (랜덤워크) : 휩쏘 방지를 위해 신규 진입 금지
    """
    
    def __init__(self):
        super().__init__(name="🧬 허스트 적응형 엔진 (Hurst Adaptive)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        h = self._safe_get(row, 'hurst_exponent', 0.5) # default 0.5
        rsi = self._safe_get(row, 'RSI')
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        bb_upper = self._safe_get(row, 'BB_upper')
        bb_lower = self._safe_get(row, 'BB_lower')
        open_price = self._safe_get(row, 'Open')
        
        # 1. 진입 로직
        if is_entry:
            # A. 추세 모멘텀 엔진 (H > 0.55)
            if h > 0.55:
                if close > bb_upper and ema9 > ema20:
                    return 100.0
            # B. 평균 회귀 엔진 (H < 0.45)
            elif h < 0.45:
                # 밴드 하단 탈출 후 양봉 복귀
                if close < bb_lower and close > open_price:
                    return 100.0
            return 0.0
            
        # 2. 청산 로직
        else:
            if h > 0.55:
                # 추세장 청산: 20일선 붕괴 시
                if close >= ema20:
                    return 100.0
                return 30.0
            else:
                # 평균회귀장 청산: 밴드 상단 도달 또는 RSI 과매수
                if close < bb_upper and rsi < 70.0:
                    return 100.0
                return 30.0
