from app.strategies.base_strategy import BaseStrategy

class SortinoMomentum(BaseStrategy):
    """
    📊 소르티노 모멘텀 자산배분 (Sortino Momentum)
    - 60일 롤링 소르티노 지수 랭킹(sortino_rank)이 최상위 3위 이내인 종목군에 진입합니다.
    - 순위가 5위 밖으로 밀려나거나(sortino_rank > 5), 소르티노 값 자체가 음수(-)로
      밀려날 때 리밸런싱 청산합니다.
    """
    
    def __init__(self):
        super().__init__(name="📊 소르티노 모멘텀 (Sortino Momentum)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        rank = self._safe_get(row, 'sortino_rank', 99) # default low rank
        ratio = self._safe_get(row, 'sortino_ratio_60d', 0.0)
        
        if is_entry:
            # 랭킹 상위 3위 이내 + 소르티노가 정상 양수일 때만 탑승
            if rank <= 3 and ratio >= 0.1:
                return 100.0
            return 0.0
        else:
            # 5위 밖으로 밀려나거나 소르티노 지수 음수 도달 시 청산
            if rank <= 5 and ratio >= 0.0:
                return 100.0
            return 30.0
