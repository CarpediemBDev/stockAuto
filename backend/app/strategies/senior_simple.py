import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class SeniorSimple(BaseStrategy):
    """
    💎 시니어 단순화 (Strategy S)
    - 복잡한 가감점 지표 노이즈를 걷어내고 직관적 핵심만 남김
    - 상승장: 오직 토비 크라벨 ORB 시가 돌파 (시가 돌파 + VWAP 상방 지지 + RVOL 수급 + EMA 정배열)
    - 하락/횡보장: 오직 RSI 볼밴 하단 극점 과매도 반등 + OBV 세력 매집
    """
    
    def __init__(self):
        super().__init__(name="시니어 단순화 (Strategy S)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        
        # 필수 거래대금 필터
        if close * volume < 7400.0:
            return 0.0
            
        vwap = self._safe_get(row, 'VWAP', default=float('nan'))
        rvol = self._safe_get(row, 'RVOL')
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        open_val = self._safe_get(row, 'Open')
        
        if regime == "BULLISH":
            # 🚀 상승장: 토비 크라벨 ORB 시가 돌파
            if is_entry:
                if not pd.isna(vwap) and close < vwap:
                    return 0.0
                if rvol < 1.1:
                    return 0.0
                if ema9 > ema20 and close > open_val:
                    return 100.0
                return 0.0
            else:
                # 홀딩 감시: VWAP 위에 있거나 이평 정배열 유지 시 홀딩
                if (not pd.isna(vwap) and close >= vwap) or (ema9 > ema20):
                    return 100.0
                return 30.0
        else:
            # 🛡️ 하락/횡보장: RSI BB + OBV 매집 반등
            if is_entry:
                is_rsi_bb = self._safe_get(row, 'is_rsi_bb_extreme')
                obv_div = self._safe_get(row, 'OBV_divergence')
                if is_rsi_bb and obv_div > 0:
                    return 100.0
                return 0.0
            else:
                # 홀딩 감시: RSI가 과매도존을 탈출(>=40)했거나 9일선 지지 시 홀딩
                rsi = self._safe_get(row, 'RSI')
                if rsi >= 40.0 or close > ema9:
                    return 100.0
                return 30.0
