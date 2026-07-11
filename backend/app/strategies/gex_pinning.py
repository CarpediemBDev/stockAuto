from app.strategies.base_strategy import BaseStrategy

class GexPinning(BaseStrategy):
    """
    📊 감마 익스포저 핀/스퀴즈 (GEX Pinning & Squeeze)
    - 옵션 딜러의 델타 헤징 압력인 Net GEX Proxy(net_gex_proxy)를 분석합니다.
    - Net GEX > 0 (양의 감마) : 주가가 특정 행사가 근처에 고정되는 핀(Pinning) 효과에 지지 베팅.
    - Net GEX < 0 (음의 감마) : 폭발적 변동성을 동반한 저항선 돌파 시 감마 스퀴즈(Squeeze) 탑승.
    """
    
    def __init__(self):
        super().__init__(name="📊 GEX 핀/스퀴즈 (Gex Pinning)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        gex = self._safe_get(row, 'net_gex_proxy', 0.0)
        strike_dist = self._safe_get(row, 'strike_distance', 0.05) # 행사가 이격
        
        if is_entry:
            # A. 양의 감마 영역 - 지지 및 핀 수렴
            if gex > 0.0 and strike_dist <= 0.005:
                return 100.0
            # B. 음의 감마 영역 - 숏커버 감마 스퀴즈 돌파
            elif gex < 0.0 and volume > self._safe_get(row, 'volume_ma20', 1.0) * 2.5:
                # 당일 강한 돌파 장대양봉 발생
                if close > self._safe_get(row, 'Open'):
                    return 100.0
            return 0.0
        else:
            # 핀/스퀴즈 압력이 모두 소멸되거나 10일선(EMA10) 이탈 시 청산
            ema10 = self._safe_get(row, 'EMA10', self._safe_get(row, 'EMA9'))
            if close >= ema10:
                return 100.0
            return 30.0
