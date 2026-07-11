from app.strategies.base_strategy import BaseStrategy

class VolatilityRegime(BaseStrategy):
    """
    🛡️ 변동성 레짐 헷지 전략 (Dynamic Volatility Regime - DVRH)
    - VIX/VXV 비율 및 VIX 선물 F1/F2 스프레드 백워데이션(정상 1.0 초과) 전환을 감지합니다.
    - 변동성 폭발 징후 및 지수 하향 이탈 시, 롱 포지션을 청산하고 숏/안전자산으로 대피합니다.
    """
    
    def __init__(self):
        super().__init__(name="🛡️ 변동성 레짐 헷지 (Volatility Regime)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        vix_vxv = self._safe_get(row, 'vix_vxv_ratio', 0.9)
        term_struct = self._safe_get(row, 'vix_term_structure', 0.9)
        
        # 백워데이션 (F1/F2 >= 1.0) 및 단기 변동성 폭증 (VIX/VXV >= 1.0)
        is_panic = (vix_vxv >= 1.0 and term_struct >= 1.0)
        
        if is_entry:
            # 시장 패닉 상황 하에서 숏/헷지 진입 활성화
            if is_panic and regime == "BEARISH":
                return 100.0
            return 0.0
        else:
            # 변동성이 정상 안정 영역(0.96 미만)으로 복귀 시 숏/헷지 청산
            if vix_vxv >= 0.96:
                return 100.0
            return 30.0
