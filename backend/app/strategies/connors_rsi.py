import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class ConnorsRsi(BaseStrategy):
    """
    래리 코너스 ConnorsRSI 초단기 극점 평균 회귀 전략 (ConnorsRSI Reversion)
    - 하락/횡보장세(BEARISH / NEUTRAL 레짐)에서 낙폭 과대 우량주의 단기 기술적 반등 스나이핑
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 래리코너스 ConnorsRSI (ConnorsRSI)")
        self.base_allocation_pct = 0.40  # 자산의 40% 기본단위
        self.min_allocation_usd = 2000.0 # 최소 $2,000 보장
        self.min_smart_exit_profit = 2.0 # 스마트 익절 최소 마진 2.0%

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:  # 최소 거래대금 $7,400 이하 탈락
            return 0.0
            
        crsi = self._safe_get(row, 'connors_rsi', default=float('nan'))
        if pd.isna(crsi):
            return 50.0 if not is_entry else 0.0

        if is_entry:
            # 1. 극단적 과매도 구간 스캔
            if crsi < 5.0:
                return 100.0  # 최상위 낙폭 과대 (모든 레짐 통과)
            elif crsi < 10.0:
                if regime == "BEARISH":
                    # 하락장에서는 단기 반등 혹은 수급 확인 필수
                    rvol = self._safe_get(row, 'RVOL', 1.0)
                    ema3 = self._safe_get(row, 'EMA3', 0.0)
                    if close > ema3 or rvol >= 1.2:
                        return 96.0  # 95점 컷오프 돌파
                    return 90.0      # 진입 차단
                elif regime == "NEUTRAL":
                    return 96.0      # 95점 컷오프 돌파 (진입 허용)
                elif regime == "BULLISH":
                    return 93.0      # 85점 컷오프 돌파 (진입 허용)
            elif crsi < 15.0:
                if regime == "BULLISH":
                    return 88.0      # 85점 컷오프 돌파 (상승장 정찰병 진입 허용)
            return 0.0
        else:
            # 2. 청산 로직 (is_signal_collapsed 트리거)
            ema5 = self._safe_get(row, 'EMA5', 0.0)
            # 종가가 5일선을 돌파했거나, ConnorsRSI가 70을 상회 시
            if (ema5 > 0 and close >= ema5) or crsi > 70.0:
                return 30.0  # score < 40/50 조건 충족 -> 즉시 청산
            return 100.0     # 홀딩
