import pandas as pd
from app.strategies.base_strategy import BaseStrategy


class InstitutionalFollow(BaseStrategy):
    """
    기관/외국인 스마트머니 수급 추종 전략 (Institutional & Foreigner Smart Money Flow)
    
    [핵심 메커니즘]
    1. 기관 및 외국인의 대규모/연속 순매수가 유입된 종목을 포착합니다.
    2. 수급 유입 후 20일 이동평균선(SMA20) 근처로 조정(Pullback) 받을 때 눌림목 진입을 수행합니다.
    3. 일반 OHLCV 백테스트 데이터 환경에서는 거래량 급증, 양봉 모멘텀, 20일선 지지를 결합한
       스마트머니 대리 지표(Proxy Indicator)로 동일 수급 파동을 추적합니다.
    4. 20일선 하향 이탈(-2.5%) 또는 ATR 변동성 손절 발생 시 명확히 청산합니다.
    """

    def __init__(self):
        super().__init__(name="⚙️ 스마트머니 수급 추종 (Smart Money Flow)")
        self.base_allocation_pct = 0.40
        self.min_allocation_usd = 2000.0
        self.min_smart_exit_profit = 2.5

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """수급 주체 지지선을 고려한 ATR 동적 손절 폭(%) 리턴."""
        sl_base = 3.0
        sl_mult = 1.5
        if atr > 0 and price > 0:
            atr_pct = (atr / price) * 100.0
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = float(self._safe_get(row, 'Close', 0.0))
        volume = float(self._safe_get(row, 'Volume', 0.0))

        if close <= 0 or volume <= 0:
            return 0.0

        # 거래대금 최소 요건 (주가 * 거래량 >= $7,400)
        if close * volume < 7400.0:
            return 0.0

        open_p = float(self._safe_get(row, 'Open', close))
        high_p = float(self._safe_get(row, 'High', close))
        low_p = float(self._safe_get(row, 'Low', close))

        # 이동평균선 및 수급 지표 조회
        sma20 = float(self._safe_get(row, 'sma20', 0.0))
        sma50 = float(self._safe_get(row, 'sma50', 0.0))
        vol_sma20 = float(self._safe_get(row, 'vol_sma20', volume))
        
        # 수급 데이터 (KIS/KRX API 실시간 수급)
        # ⚠️ 현재 저장소에 아래 4개 필드를 채우는 생산자가 없다(스캐너·백테스트 지표 파이프라인 모두
        # 미산출). 따라서 아래 1) 분기는 항상 미발화이며 실제로는 2) OHLCV 대리 분기만 동작한다.
        # 수급 API를 실제로 배선하기 전까지 이 전략은 프록시 전략으로 취급한다
        # (strategy_catalog의 selection_eligible=False 근거).
        organ_buy = float(self._safe_get(row, 'organ_net_buy', 0.0))
        foreigner_buy = float(self._safe_get(row, 'foreigner_net_buy', 0.0))
        smart_money_score = float(self._safe_get(row, 'smart_money_score', 0.0))
        net_buy_days = float(self._safe_get(row, 'institutional_net_buy_days', 0.0))

        if is_entry:
            # 1) 실시간 기관/외인 수급 데이터가 수집된 경우
            if smart_money_score > 0 or organ_buy > 0 or foreigner_buy > 0:
                # 기관 또는 외인 연속 순매수 또는 수급점수 70점 이상
                is_institutional_inflow = (
                    smart_money_score >= 70.0 or
                    net_buy_days >= 3.0 or
                    (organ_buy > 0 and foreigner_buy > 0)
                )
                # 수급 유입 + 20일선 위 눌림목 지지
                if is_institutional_inflow:
                    if sma20 > 0 and close >= sma20 * 0.98 and close <= sma20 * 1.05:
                        return 100.0
                    elif close > open_p:
                        return 90.0
                return 0.0

            # 2) 표준 OHLCV 백테스트 데이터 (Proxy 수급 추적)
            # - 거래량 유입 (20일 평균 거래량의 1.2배 이상)
            # - 상승 추세 (sma20 > sma50 또는 close > sma20)
            # - 20일선 근처 눌림목 반등 (sma20 * 0.98 <= close <= sma20 * 1.04)
            volume_ratio = volume / vol_sma20 if vol_sma20 > 0 else 1.0
            
            trend_ok = False
            if sma20 > 0 and sma50 > 0:
                trend_ok = (close >= sma20) and (sma20 >= sma50 * 0.98)
            elif sma20 > 0:
                trend_ok = (close >= sma20 * 0.98)
            else:
                trend_ok = (close >= open_p)

            pullback_ok = False
            if sma20 > 0:
                pullback_ok = (close >= sma20 * 0.985) and (close <= sma20 * 1.045)
            else:
                pullback_ok = True

            volume_ok = (volume_ratio >= 1.25) or (close >= open_p and volume_ratio >= 1.1)

            if trend_ok and pullback_ok and volume_ok:
                score = 85.0
                if volume_ratio >= 1.8:
                    score += 10.0
                if close > open_p:
                    score += 5.0
                return min(100.0, score)

            return 0.0

        else:
            # 포지션 보유 중 붕괴/청산 판정
            # 20일선 아래 -2.5% 이하로 하향 이탈 시 수급 붕괴로 간주하여 0.0점 (즉시 청산)
            if sma20 > 0 and close < sma20 * 0.975:
                return 0.0
            
            # 수급 유지 시 80.0점 유지
            return 80.0
