import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ASQS(BaseStrategy):
    """
    🥇 Antigravity Supernova Quantum-Squeeze (ASQS) 전략
    - 안티그래비티 독점 급등주 타겟팅 모델.
    - 장초반 돈의 유속 폭발 (RVOL >= 6배 또는 당일 하루 전체 거래량 15분 봉 급증) 감지.
    - 갭상승이 미미하더라도 장초반 거래량이 극단적으로 폭증하는 진짜 바닥 탈출 급등주를 실시간 15분 만에 사냥.
    - 장세 레짐 기반의 공격적 비중 분배:
      * 상승장 (BULLISH) -> 즉시 100% 풀비중 진입 (entry_factor = 1.0)
      * 하락/횡보장 (BEARISH/NEUTRAL) -> 50% 절반 비중 진입 (entry_factor = 0.5)
    - 휩쏘 페이크 이탈을 예방하기 위해 넓은 동적 손절선(6% / 3x ATR) 및 트레일링 스탑(4% / 2x ATR) 탑재
    """
    
    def __init__(self):
        super().__init__(name="🚀 ASQS (초신성 퀀텀 스퀴즈) 🔥")
        self.base_allocation_pct = 0.40  # 40% 기본비중
        self.min_allocation_usd = 2000.0 # 최소 $2,000 보장
        self.min_smart_exit_profit = 3.0  # 스마트 익절 최소 마진 3%

    def get_initial_entry_factor(self, regime: str) -> float:
        if regime == "BULLISH":
            return 1.0  # 상승장: 즉시 100% 풀비중
        return 0.5      # 약세/횡보장: 50% 절반 비중으로 안전장치 가동

    def get_pyramid_trigger(self, stage: int) -> float:
        # 50%로 진입했을 경우, +2% 상승 시 1차 불타기를 허용하여 100% 비중 완성
        if stage == 1:
            return 2.0
        return 999.0

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """변동성이 큰 초소형주의 휩쏘 방지를 위한 6% / 3x ATR 손절선 적용"""
        sl_base = 6.0
        sl_mult = 3.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        """수익을 확실하게 낚아채기 위한 4% / 2x ATR 트레일링 스탑 적용"""
        ts_base = 4.0
        ts_mult = 2.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(ts_base, atr_pct * ts_mult)
        return ts_base

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        open_val = self._safe_get(row, 'Open')
        gap = self._safe_get(row, 'gap_pct')
        rvol = self._safe_get(row, 'RVOL')
        
        # 1. 거래대금 필수 가이드라인
        if close * volume < 7400.0:
            return 0.0
            
        # 2. ASQS 핵심 DNA 마커 필터링
        # DNA 3: 장초반 돈의 유속 대분출 (RVOL 6.0배 이상 & 양봉 강도)
        is_money_velocity = rvol >= 6.0 and close > open_val * 1.02
        
        # DNA 2: 갭상승 돌파 셋업 (is_pre_gapper_setup 또는 gap 5% 이상 + RVOL 3배 이상)
        is_gap_breakout = (gap >= 5.0 and rvol >= 3.0 and close > open_val) or self._safe_get(row, 'is_pre_gapper_setup') == 1.0
        
        # DNA 1: 슈퍼노바 또는 10배 거래량 장대양봉 전조 발생 당일
        is_supernova = self._safe_get(row, 'is_supernova_setup') == 1.0 or self._safe_get(row, 'is_vol_10x_spike') == 1.0 or self._safe_get(row, 'is_float_rotation') == 1.0
        
        is_asqs_trigger = is_money_velocity or is_gap_breakout or is_supernova
        
        if is_entry:
            if is_asqs_trigger:
                if score_card is not None:
                    score_card.append({"factor": "🚀 ASQS 초신성 돈의유속/갭 돌파 포착 (즉시 만점)", "score": 100, "passed": True})
                return 100.0
            
            return 0.0  # ASQS 퀀텀 스퀴즈 조건 미달 시 매수하지 않음 (철저한 스나이퍼 매매)
        else:
            # 3. 청산/탈출 감시
            # 강세 모멘텀의 이탈 감지: EMA 9일선 이탈 또는 시가 붕괴(음봉 전환) 시 즉시 전량 청산
            ema9 = self._safe_get(row, 'EMA9')
            if close < ema9 or close < open_val:
                if score_card is not None:
                    score_card.append({"factor": "🚨 ASQS 강세 모멘텀 붕괴 이탈 청산", "score": 0, "passed": False})
                return 0.0
                
            return 100.0  # 강세 유지 시 계속 홀딩
