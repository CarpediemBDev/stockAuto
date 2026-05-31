from app.strategies.strategy_c import StrategyC

class ExplodedC(StrategyC):
    """
    🔥 전략 C-폭발형
    - 40% 기본 비중 할당 (최소 $2,000 보장)
    - 정찰병 단계를 완벽히 생략하고 진입 시점부터 즉시 100% 풀비중 베팅
    - 불타기 피라미딩 비활성화
    - 지동 휩쏘 손절을 방지하기 위해 2배 넓은 ATR 손절선(6% / 3 ATR) 및 트레일링 스탑(4% / 2 ATR) 가동
    """
    
    def __init__(self):
        super().__init__()
        self.name = "🧪 전략 C-폭발형"

    def get_initial_entry_factor(self, regime: str) -> float:
        return 1.0  # 정찰병 15% 단계를 과감히 생략하고 즉시 100% 비중 진입

    def get_pyramid_trigger(self, stage: int) -> float:
        return 999.0  # 이미 즉시 풀베팅 상태이므로 추가 매수 없음

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """폭발형 전략은 2배 더 넓은 손절 버퍼(기본 6.0% 및 3.0x ATR)를 적용합니다."""
        sl_base = 6.0
        sl_mult = 3.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        """폭발형 전략은 2배 더 넓은 트레일링 스탑 버퍼(기본 4.0% 및 2.0x ATR)를 적용합니다."""
        ts_base = 4.0
        ts_mult = 2.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(ts_base, atr_pct * ts_mult)
        return ts_base
