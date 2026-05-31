import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class StrategyA(BaseStrategy):
    """
    🔴 전략 A (태초의 방패)
    - 10% 소액 유닛 진입 (최소 $2,000 하한 없음)
    - 불타기(피라미딩) 원천 금지
    - 보유 중 VWAP 또는 RVOL 1.1 하향 돌파 시 점수가 즉시 0점으로 강강손절 실행
    """
    
    def __init__(self):
        super().__init__(name="🔴 전략 A (태초 10% 비중 + 하드 컷)")
        self.base_allocation_pct = 0.10  # 10% 소액 비중
        self.min_allocation_usd = 0.0    # 최소 투자 하한 없음
        self.min_smart_exit_profit = 999.0 # 스마트 익절 비활성화 (999% 도달 불가)
        
    def get_cutoff_score(self, regime: str) -> float:
        return 80.0  # 기존 v1.0 / 전략 A는 일괄 80점 커트라인 적용
        
    def is_signal_collapsed(self, score: float, regime: str) -> bool:
        return score < 40.0  # 전략 A는 하락장 관계없이 40점 미만 시 청산
        
    def get_initial_entry_factor(self, regime: str) -> float:
        return 1.0  # 피라미딩이 없으므로 정찰병 단계 생략하고 곧바로 100% 진입

    def get_pyramid_trigger(self, stage: int) -> float:
        return 999.0  # 추가 불타기 금지

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        dollar_volume = self._safe_get(row, 'Close') * self._safe_get(row, 'Volume')
        if dollar_volume < 7400.0:
            return 0.0
            
        close = self._safe_get(row, 'Close')
        vwap = self._safe_get(row, 'VWAP', default=float('nan'))
        rvol = self._safe_get(row, 'RVOL')
        
        # 💡 보유 중 감시: VWAP 붕괴 또는 RVOL 1.1 미만 시 칼손절 (A의 시그니처)
        if not is_entry:
            if (not pd.isna(vwap) and close < vwap) or rvol < 1.1:
                return 0.0
                
        score = 0
        # RVOL 가점
        if rvol >= 2.0: score += 30
        elif rvol >= 1.2: score += 15
        
        # 신고가 저항 돌파 가점
        dist_to_high = self._safe_get(row, 'dist_to_high', default=float('nan'))
        if not pd.isna(dist_to_high) and dist_to_high > -1.5: 
            score += 20
            
        # EMA 정배열 가점
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        if ema9 > ema20: score += 10
        
        # 52주 역사적 신고가 인접 가점
        if self._safe_get(row, 'is_near_52w_high'): score += 25
        # 3연속 모멘텀 양봉 가점
        if self._safe_get(row, 'momentum_candles'): score += 15
        
        # 장세 레짐 보너스/패널티
        if regime == "BULLISH":
            score += 5
            if not pd.isna(vwap) and close > vwap: score += 10
            wick = self._safe_get(row, 'Wick')
            if wick < 0.3: score += 10
            elif wick > 0.5: score -= 20
        elif regime == "BEARISH":
            score -= 30  # 하락장 강력 감점
            
        return max(0.0, min(float(score), 100.0))
