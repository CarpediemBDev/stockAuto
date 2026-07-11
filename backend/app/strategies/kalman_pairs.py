from app.strategies.base_strategy import BaseStrategy

class KalmanPairs(BaseStrategy):
    """
    📊 칼만 필터 페어 트레이딩 (Kalman-Pairs Trading)
    - 실시간 칼만 필터(Kalman Filter) 상태전이를 거쳐 계산된 Z-score를 바탕으로 
      롱-온리 헷지 스프레드 거래를 수행합니다.
    - Z-score <= -2.0 진입 (단기 과도 이격)
    - Z-score >= -0.2 수렴 청산 (익절) 또는 Z-score <= -4.0 공적분 해제 시 즉시 손절.
    """
    
    def __init__(self):
        super().__init__(name="📊 칼만 필터 페어 (Kalman Pairs)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        z = self._safe_get(row, 'kalman_zscore', 0.0)
        
        if is_entry:
            # -2.0 극점 이탈 후 반등 초입 감지
            if z <= -1.8 and z > -3.5:
                return 100.0
            return 0.0
        else:
            # 균형점 수렴(0.2 이내) 시 익절, 극단적 이탈(-4.0 이하) 시 손절 청산
            if z > -4.0 and z < -0.2:
                return 100.0
            return 30.0
