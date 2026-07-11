import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class TurnOfMonth(BaseStrategy):
    """
    월말 효과 계절성 매매 전략 (Turn-of-the-Month)
    - 매월 기관들의 대규모 리밸런싱 및 신규 자금 집행이 모이는 월말 마지막 1거래일 ~ 초반 3거래일 구간(`is_tom == 1.0`)에만 주식 롱 포지션 유지.
    - 리밸런싱 자금 분출 기간이 끝나고 주중 노이즈 장세(`is_tom == 0.0`)로 돌입하면 전량 청산 완료하여 현금 관망.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 월말효과 계절성 (Turn of Month)")
        self.base_allocation_pct = 0.30
        self.min_smart_exit_profit = 0.5 # 아주 짧은 계절성 마진 타겟

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        
        # 1. 거래대금 필터 강화 (유동성 부족한 잡주 차단: 최소 $500,000)
        if close * volume < 500000.0:
            return 0.0
            
        tom = self._safe_get(row, 'is_tom')
        
        if is_entry:
            # 월말-월초 자금 분출 기간이면서 지수 대비 강세(상대 강도) 또는 최소 20일선 정배열 지지 시에만 진입
            if tom == 1.0:
                relative_strength = self._safe_get(row, 'relative_strength', 0.0)
                ema20 = self._safe_get(row, 'EMA20', 0.0)
                if relative_strength > 0.0 or (ema20 > 0.0 and close > ema20):
                    return 100.0
            return 0.0
        else:
            # 리밸런싱 기간 종료 시 청산 후 현금화
            if tom == 1.0:
                return 100.0
            return 30.0
