import pandas as pd
from app.strategies.base_strategy import BaseStrategy

class StrategyC(BaseStrategy):
    """
    🏆 전략 C (손익비 최적화 v2.0)
    - 40% 기본 비중 할당 (최소 $2,000 보장)
    - 완화된 +2% / +4% 피라미딩 불타기 적용
    - 스마트 익절 최소 마진 2.5% 상향
    - 11대 기술지표 종합 가감점 스코어카드 채점 방식
    - 보유 중 필수 필터 붕괴 시 칼손절 대신 -15점 소프트 감점 적용
    """
    
    def __init__(self, name: str = "🥇 전략 C (11대 복합)"):
        super().__init__(name=name)
        self.base_allocation_pct = 0.40
        self.min_allocation_usd = 2000.0
        self.min_smart_exit_profit = 2.5

    def get_initial_entry_factor(self, regime: str) -> float:
        if regime == "BULLISH":
            return 0.15  # 상승장: 정찰병 15% 진입
        elif regime == "BEARISH":
            return 0.30  # 하락장: 비중 30% 제한
        else:
            return 0.50  # 횡보장: 비중 50% 제한

    def get_pyramid_trigger(self, stage: int) -> float:
        if stage == 1:
            return 2.0   # +2%에서 2단계 추가 진입
        elif stage == 2:
            return 4.0   # +4%에서 3단계 추가 진입
        return 999.0

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        vwap = self._safe_get(row, 'VWAP', default=float('nan'))
        rvol = self._safe_get(row, 'RVOL')
        
        # 1. 필수 관문 필터 (진입 시에만 엄격 적용)
        if is_entry:
            # 거래대금 필터
            if close * volume < 7400.0:
                if score_card is not None:
                    score_card.append({"factor": f"거래대금 부족 (${close * volume:,.2f})", "score": 0, "passed": False})
                return 0.0
            else:
                if score_card is not None:
                    score_card.append({"factor": "당일 거래대금 가이드라인 만족", "score": 0, "passed": True})
                    
            # 세력선 지지 필터
            if not pd.isna(vwap) and close < vwap:
                if score_card is not None:
                    score_card.append({"factor": f"VWAP 세력선 지지 실패 (Close: {close} < VWAP: {vwap:.2f})", "score": 0, "passed": False})
                return 0.0
            else:
                if score_card is not None:
                    score_card.append({"factor": "VWAP 세력지지선 상방 안착 통과", "score": 0, "passed": True})
                    
            # 상대거래량 필터
            if rvol < 1.1:
                if score_card is not None:
                    score_card.append({"factor": f"수급 RVOL 강도 미달 (RVOL: {rvol:.2f} < 1.1)", "score": 0, "passed": False})
                return 0.0
            else:
                if score_card is not None:
                    score_card.append({"factor": "수급 RVOL 최소 조건 통과", "score": 0, "passed": True})

        score = 0
        
        # 💡 [Stage 1] 공통 가점 요인 산출
        # RVOL 가점
        if rvol >= 2.0:
            score += 30
            if score_card is not None:
                score_card.append({"factor": f"상대 거래량(RVOL) 급증 (+{rvol:.2f}배)", "score": 30, "passed": True})
        elif rvol >= 1.2:
            score += 15
            if score_card is not None:
                score_card.append({"factor": f"상대 거래량(RVOL) 완만 상승 (+{rvol:.2f}배)", "score": 15, "passed": True})
        
        # 신고가 저항 돌파 가점
        dist_to_high = self._safe_get(row, 'dist_to_high', default=float('nan'))
        if not pd.isna(dist_to_high) and dist_to_high > -1.5: 
            score += 20
            if score_card is not None:
                score_card.append({"factor": f"전고점 저항선 돌파 영역 인접 ({dist_to_high:.2f}%)", "score": 20, "passed": True})
            
        # 지수 대비 강세 (Relative Strength)
        relative_strength = self._safe_get(row, 'relative_strength')
        if relative_strength > 0: 
            score += 10
            if score_card is not None:
                score_card.append({"factor": f"지수 대비 초과 강세 달성 (RS: {relative_strength:.4f})", "score": 10, "passed": True})
            
        # EMA 이평선 정배열 가점
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        if ema9 > ema20: 
            score += 10
            if score_card is not None:
                score_card.append({"factor": "EMA 9/20 정배열 상승 흐름 정방향 안착", "score": 10, "passed": True})
        
        # 52주 역사적 신고가 인접 가점
        if self._safe_get(row, 'is_near_52w_high'): 
            score += 25
            if score_card is not None:
                score_card.append({"factor": "52주 역사적 최고가 영역 근접", "score": 25, "passed": True})
                
        # 3연속 모멘텀 양봉 가점
        if self._safe_get(row, 'momentum_candles'): 
            score += 15
            if score_card is not None:
                score_card.append({"factor": "3연속 거래량 실린 강세 양봉 출현", "score": 15, "passed": True})
                
        # 실시간 프리마켓 갭 가점 (실시간 스캐너 연동용)
        premarket_gap = self._safe_get(row, 'premarket_gap_pct', 0.0)
        if premarket_gap >= 5.0:
            score += 20
            if score_card is not None:
                score_card.append({"factor": f"프리마켓 거래 갭 급증 (+{premarket_gap:.2f}%)", "score": 20, "passed": True})

        # 💡 [Stage 2] 장세 레짐 분기 채점
        wick = self._safe_get(row, 'Wick')
        
        if regime == "BULLISH":
            if score_card is not None:
                score_card.append({"factor": "나스닥 QQQ 상승장 레짐 보너스", "score": 5, "passed": True})
            score += 5  # 상승장 보너스
            
            if not pd.isna(vwap) and close > vwap: 
                score += 10
                if score_card is not None:
                    score_card.append({"factor": "VWAP 세력선 상방 돌파 유지 가중치", "score": 10, "passed": True})
                    
            if wick < 0.3: 
                score += 10
                if score_card is not None:
                    score_card.append({"factor": "윗꼬리 매물대 저항 없음 (캔들 안정성)", "score": 10, "passed": True})
            elif wick > 0.5: 
                score -= 20
                if score_card is not None:
                    score_card.append({"factor": "윗꼬리 악성 물량 저항 발생 (물림 위험)", "score": -20, "passed": False})
                    
            # 실시간 ORB 돌파 가점
            if self._safe_get(row, 'is_orb_breakout', False):
                score += 20
                if score_card is not None:
                    score_card.append({"factor": "장초반 5분봉 고가 상방 대량 돌파 (ORB)", "score": 20, "passed": True})
        else:
            # BEARISH / NEUTRAL 장세
            if self._safe_get(row, 'OBV_divergence') > 0: 
                score += 30
                if score_card is not None:
                    score_card.append({"factor": "세력 OBV 매집 다이버전스 골든크로스", "score": 30, "passed": True})
            else: 
                score -= 20
                if score_card is not None:
                    score_card.append({"factor": "세력 OBV 매집 약세 저항 발생", "score": -20, "passed": False})
                
            ema120 = self._safe_get(row, 'EMA120')
            if not pd.isna(ema120) and close > ema120: 
                score += 30
                if score_card is not None:
                    score_card.append({"factor": "일봉 장기 120일선 상방 가격 안착", "score": 30, "passed": True})
                    
            if self._safe_get(row, 'is_rsi_bb_extreme'): 
                score += 30
                if score_card is not None:
                    score_card.append({"factor": "RSI 볼린저밴드 하단 극점 터치 강력 반동 포착", "score": 30, "passed": True})
                    
            if regime == "BEARISH": 
                score -= 30
                if score_card is not None:
                    score_card.append({"factor": "나스닥 QQQ 약세장 감점 페널티 적용", "score": -30, "passed": False})
                
            if wick < 0.3: 
                score += 10
                if score_card is not None:
                    score_card.append({"factor": "윗꼬리 매물대 저항 없음 (안전)", "score": 10, "passed": True})
            elif wick > 0.5: 
                score -= 20
                if score_card is not None:
                    score_card.append({"factor": "윗꼬리 악성 물량 저항 발생 (약세장)", "score": -20, "passed": False})

        # 실시간 뉴스 감성 분석 가점 (실시간 스캐너 연동용)
        news_sentiment = self._safe_get(row, 'news_sentiment', 'NEUTRAL')
        news_score = self._safe_get(row, 'news_sentiment_score', 0.0)
        if news_sentiment == "POSITIVE":
            score += 20
            if score_card is not None:
                score_card.append({"factor": f"AI 뉴스 심리 진단 호재 포착 ({news_score}점)", "score": 20, "passed": True})
        elif news_sentiment == "NEGATIVE":
            score -= 30
            if score_card is not None:
                score_card.append({"factor": f"AI 뉴스 심리 진단 악재 경보 감지 ({news_score}점)", "score": -30, "passed": False})

        # VCP 및 컵앤핸들 상승 차트 패턴 가점 (실시간 스캐너 연동용)
        if self._safe_get(row, 'is_vcp', False):
            score += 15
            if score_card is not None:
                score_card.append({"factor": "마크 미너비니 VCP 변동성 수렴 돌파 가산", "score": 15, "passed": True})
        if self._safe_get(row, 'is_cup', False):
            score += 15
            if score_card is not None:
                score_card.append({"factor": "윌리엄 오닐 컵 앤 핸들 상승 패턴 가산", "score": 15, "passed": True})

        # 💡 [보유 중 감시] 관문 필터를 소프트 감점으로 전환 반영 (Whipsaw 방지 버퍼)
        if not is_entry:
            if not pd.isna(vwap) and close < vwap:
                score -= 15
                if score_card is not None:
                    score_card.append({"factor": "보유 종목 1분봉 VWAP 이탈 감점", "score": -15, "passed": False})
            if rvol < 1.1:
                score -= 15
                if score_card is not None:
                    score_card.append({"factor": "보유 종목 RVOL 수급 둔화 감점", "score": -15, "passed": False})

        return max(0.0, min(float(score), 100.0))
