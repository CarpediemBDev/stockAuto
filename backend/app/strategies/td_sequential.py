from app.strategies.base_strategy import BaseStrategy

class TdSequential(BaseStrategy):
    """
    📈 DeMark TD 순차 반등 (TD Sequential)
    - 토마스 드마크(Thomas DeMark)의 TD Sequential 기법을 적용합니다.
    - TD Buy Setup 9 카운트가 완성(td_buy_setup_count == 9)되어 단기 과매도 하락 극점에 다다르고,
      직후 첫 번째 양봉 반등(Close > Open) 시 진입합니다.
    - 반대로 단기 과열 매도 극점인 TD Sell Setup 9 카운트 완성 시 청산합니다.
    """
    
    def __init__(self):
        super().__init__(name="📈 드마크 TD 순차반등 (TD Sequential)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        td_buy = self._safe_get(row, 'td_buy_setup_count', 0)
        td_sell = self._safe_get(row, 'td_sell_setup_count', 0)
        open_price = self._safe_get(row, 'Open')
        
        if is_entry:
            # 9 카운트 극점 또는 그 직후 1~2봉 이내 첫 양봉 턴어라운드
            if td_buy >= 9 and close > open_price:
                return 100.0
            return 0.0
        else:
            # 매도 극점 9 카운트 도달 시 즉시 청산
            if td_sell < 9:
                return 100.0
            return 30.0
