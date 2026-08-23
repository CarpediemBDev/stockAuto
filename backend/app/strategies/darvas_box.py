import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class DarvasBox(BaseStrategy):
    """
    다바스 박스 매매 전략 (Darvas Box Theory)
    - 주가가 역사적 또는 중단기 신고가권에서 형성한 20일 박스권 상단(Box High)을 강하게 상향 돌파 시 진입.
    - 지지선 역할을 하는 박스권 하단(Box Low)을 깨고 내려갈 때 칼같이 손절하는 안정적 전략.
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 다바스 박스 매매 (Darvas Box)")
        self.base_allocation_pct = 0.40
        self.min_smart_exit_profit = 3.0

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        darvas_high = self._safe_get(row, 'darvas_high')
        darvas_low = self._safe_get(row, 'darvas_low')

        if is_entry:
            # 박스 상단이 없으면 돌파 여부를 판단할 수 없다. 0.0인 채로 `close > 0.0`을
            # 계산하면 모든 종목이 돌파로 판정되므로(라이브 시그널에는 darvas_high가 없다)
            # 기준선이 준비되지 않았을 때는 점수를 내지 않는다.
            if not darvas_high > 0.0:
                return 0.0

            # 박스 상단 돌파 시 매수
            if close > darvas_high:
                return 100.0
            return 0.0
        else:
            # 박스 하단 이탈 시 청산.
            # 하단이 없으면 이탈 판정이 불가능해 홀딩(100.0)으로 남고, 실제 청산은
            # 손절·트레일링 스탑이 담당한다. 보유분 처리 방침은 별도 결정 사항이다.
            if darvas_low > 0.0 and close < darvas_low:
                return 0.0
            return 100.0

