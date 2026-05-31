import pandas as pd
from app.strategies.strategy_c import StrategyC

class StrategyCEP(StrategyC):
    """
    🥇 전략 C - 에피소딕 피벗 통합형 (Strategy C-EP)
    - 40% 기본 비중 할당 (최소 $2,000 보장)
    - 정찰병 단계 없이 즉시 100% 풀비중 진입하여 급등세 초입 탑승
    - 에피소딕 피벗 (EP) 시그널 감지 시 (+10% 갭상승 & RVOL 3배 이상 & 양봉) 점수를 즉시 100점 만점으로 상향 진입
    - 에피소딕 피벗 전용 청산 룰 (EMA 9일선 이탈 또는 시가 붕괴) 및 전략 C 고유의 트레일링 스탑/손절선 듀얼 결합
    """
    
    def __init__(self):
        super().__init__()
        self.name = "🥇 전략 C-EP 통합형"

    def get_initial_entry_factor(self, regime: str) -> float:
        return 1.0  # 급등주 펌핑 탑승을 위해 즉시 풀비중 진입

    def get_pyramid_trigger(self, stage: int) -> float:
        return 999.0  # 이미 즉시 풀베팅 상태이므로 불타기 피라미딩 없음

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """급등세의 변동성을 견디기 위해 넓혀진 6% / 3x ATR 손절 버퍼 적용"""
        sl_base = 6.0
        sl_mult = 3.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        """수익 보전을 극대화하기 위해 넓혀진 4% / 2x ATR 트레일링 스탑 적용"""
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
            
        # 2. 에피소딕 피벗 (EP) 감지 필터
        # 갭 +10% 이상 & RVOL 3.0배 이상 & 시초가 돌파 강세 양봉
        is_ep_trigger = gap >= 10.0 and rvol >= 3.0 and close > open_val
        
        if is_entry:
            if is_ep_trigger:
                if score_card is not None:
                    score_card.append({"factor": "🚀 에피소딕 피벗 대대적 수급 포착 (즉시 만점)", "score": 100, "passed": True})
                return 100.0
            
            # EP가 아니면 표준 전략 C 스코어 계산을 따릅니다.
            return super().calculate_score(row, regime, is_entry, score_card)
        else:
            # 3. 청산/탈출 감시
            # 에피소딕 피벗 전용 즉시 청산 룰: EMA 9일선 이탈 또는 당일 시가 붕괴(음봉 전환)
            ema9 = self._safe_get(row, 'EMA9')
            if close < ema9 or close < open_val:
                if score_card is not None:
                    score_card.append({"factor": "🚨 에피소딕 피벗 강세선 이탈 청산", "score": 0, "passed": False})
                return 0.0  # 강제 시그널 붕괴로 즉시 매도 트리거
                
            # 강세선 유지 시 표준 전략 C의 스코어 및 붕괴 여부를 적용
            return super().calculate_score(row, regime, is_entry, score_card)
