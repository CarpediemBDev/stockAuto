from app.strategies.base_strategy import BaseStrategy

class PcaKnn(BaseStrategy):
    """
    🧬 PCA-KNN 단기 패턴 매칭 (PCA-KNN Pattern Matching)
    - 다차원 기술 지표를 PCA(주성분 분석)로 축소 투영한 후,
      과거 데이터의 유클리드 거리 KNN 이웃들의 상승 확률(knn_up_probability)을 기반으로 진입합니다.
    - 상승 확률이 임계값(0.8 / 0.9) 이상일 때 매수하며, 확률이 0.4 이하로 꺼지면 탈출합니다.
    """
    
    def __init__(self):
        super().__init__(name="🧬 PCA-KNN 패턴매칭 (Pca Knn)")

    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        if close * volume < 7400.0:
            return 0.0
            
        prob = self._safe_get(row, 'knn_up_probability', 0.5)
        
        # 레짐별 진입 컷오프 확률 조율
        cutoff = 0.80 if regime == "BULLISH" else 0.90
        
        if is_entry:
            if prob >= cutoff:
                return 100.0
            return 0.0
        else:
            # 상승 확률 40% 미만 붕괴 시 즉시 청산
            if prob >= 0.40:
                return 100.0
            return 30.0
