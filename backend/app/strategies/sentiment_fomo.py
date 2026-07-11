from app.strategies.base_strategy import BaseStrategy

class SentimentFomo(BaseStrategy):
    """
    🔥 소셜 감성 FOMO 추종 (Sentiment FOMO)
    - 대안 데이터 API 기반 Reddit/Stocktwits 언급 가속도(mention_zscore >= 2.5)와
      긍정 감성 극성(sentiment_positive >= 0.6)이 폭발하는 종목에 탑승합니다.
    - 언급량이 가라앉거나(mention_zscore < 0.5) 감성이 소멸할 때 빠르게 탈출합니다.
    """
    
    def __init__(self):
        super().__init__(name="🔥 소셜 FOMO 추종 (Sentiment FOMO)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        z_m = self._safe_get(row, 'mention_zscore', 0.0)
        sent_pos = self._safe_get(row, 'sentiment_positive', 0.5)
        
        if is_entry:
            # 급격한 대중의 관심 폭발 + 긍정적 FOMO 상태
            if z_m >= 2.5 and sent_pos >= 0.6 and close > self._safe_get(row, 'Open'):
                return 100.0
            return 0.0
        else:
            # 대중의 관심 소멸 또는 부정 여론 전환 시 빠른 탈출
            if z_m >= 0.5 and sent_pos >= 0.4:
                return 100.0
            return 30.0
