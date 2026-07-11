from app.strategies.base_strategy import BaseStrategy

class ObiOfa(BaseStrategy):
    """
    📊 호가창 불균형 OFA 가속도 (OBI-OFA Acceleration)
    - 상위 5단계 호가 매수 잔량 비율(order_book_imbalance >= 0.7)과
      동적 주문 흐름 불균형 틱 가속도(OFI_acceleration > 0)가 동시에 폭발할 때 진입합니다.
    - 호가 수급이 급격히 이탈하거나 가속도가 둔화될 때 청산합니다.
    """
    
    def __init__(self):
        super().__init__(name="📊 호가창 OBI 가속도 (Obi Ofa)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        obi = self._safe_get(row, 'order_book_imbalance', 0.5)
        ofi_acc = self._safe_get(row, 'OFI_acceleration', 0.0)
        
        if is_entry:
            # 매수 호가 쏠림 + OFI 체결 방향 가속도 양수 전환
            if obi >= 0.70 and ofi_acc > 0.0:
                return 100.0
            return 0.0
        else:
            # 매수 잔량 이탈 또는 체결 가속도 붕괴(음수) 시 청산
            if obi >= 0.30 and ofi_acc >= -0.5:
                return 100.0
            return 30.0
