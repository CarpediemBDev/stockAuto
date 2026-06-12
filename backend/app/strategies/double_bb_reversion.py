import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class DoubleBbReversion(BaseStrategy):
    """
    ⚙️ 마켓트랩 더블 볼린저밴드 역추세 전략 (Double BB Reversion)
    - 3SD 하단 이탈 후 2SD 하단 안으로 복귀 시 셋업 형성.
    - 복귀 캔들의 고가를 종가 기준으로 상향 돌파 시 진입.
    - 2SD 상단 밴드 터치 시 익절 또는 손절 관리.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 마켓트랩 더블 볼린저밴드 (Double BB Reversion)")
        
        # 💡 기본 자금 및 비중 제어 가이드라인 (디폴트: 전략 C 표준형)
        self.base_allocation_pct = 0.40  # 자산의 40% 기본단위
        self.min_allocation_usd = 2000.0 # 최소 $2,000 보장
        self.min_smart_exit_profit = 1.5 # 스마트 익절 최소 마진 1.5%
        
        # 💡 볼린저 밴드 및 역추세 전략 파라미터 (하드코딩 방지)
        self.window = 20
        self.std_inner = 2.0
        self.std_outer = 3.0
        self.rsi_period = 14
        self.rsi_threshold = 30.0
        self.use_rsi_filter = True
        self.trigger_expiry = 3
        
        # 청산 관련 설정
        self.exit_on_upper_bb = True # 2SD 상단 터치 시 익절 처리 여부
        self.stop_loss_pct_default = 2.5 # 손절폭 기본값 2.5%
        self.trailing_stop_pct_default = 2.0 # 트레일링 스탑 기본값 2.0%

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """ATR 변동성에 기반한 동적 손절 폭(%)을 리턴합니다."""
        sl_base = self.stop_loss_pct_default
        sl_mult = 1.5
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        """ATR 변동성에 기반한 동적 트레일링 스탑 폭(%)을 리턴합니다."""
        ts_base = self.trailing_stop_pct_default
        ts_mult = 1.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(ts_base, atr_pct * ts_mult)
        return ts_base

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        if is_entry:
            # 3SD 하단 이탈 후 2SD 복귀 및 고가 돌파 안착 매수 시그널 검출
            if self._safe_get(row, 'is_double_bb_buy') == 1.0:
                return 100.0
            return 0.0
        else:
            # 포지션 보유 중인 경우 청산 시그널 판단
            # 1. 2SD 상단 밴드 상향 돌파 시 익절
            if self.exit_on_upper_bb:
                is_exit = self._safe_get(row, 'is_double_bb_sell') == 1.0
                if is_exit:
                    return 30.0  # 30점은 붕괴 임계값(50점) 미만이므로 즉시 청산 유도
            return 100.0  # 기본 홀딩
