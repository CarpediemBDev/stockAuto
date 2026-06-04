from app.strategies.base_strategy import BaseStrategy

class RegimeSwitching(BaseStrategy):
    """
    👑 마스터 레짐스위칭 (Regime Switching) [🏆 통합 1위]
    - QQQ 지수가 상승장(BULLISH)일 때는 극강의 공격수 'EMA 이평정배열 (EMA Only)'로 질주
    - QQQ 지수가 하락/횡보장(BEARISH/NEUTRAL)일 때는 지옥의 방패 '쿨라매기 돌파' 기법으로 옷을 갈아입음
    - 자본 분할 및 익절선 등은 표준 v2.0 스펙 공유
    """
    
    def __init__(self):
        super().__init__(name="⚙️ 마스터 레짐스위칭 (Regime Switching)")

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')
        
        # 필수 거래대금 필터
        if close * volume < 7400.0:
            if score_card is not None:
                score_card.append({"factor": "기본 유동성 (거래대금 부족)", "score": 0, "passed": False})
            return 0.0
            
        ema9 = self._safe_get(row, 'EMA9')
        ema20 = self._safe_get(row, 'EMA20')
        
        score = 0.0
        
        if regime == "BULLISH":
            # 🚀 상승장 레짐: EMA 이평 정배열 추세 추종
            if is_entry:
                if ema9 > ema20:
                    if score_card is not None:
                        score_card.append({"factor": "상승장 공격모드 가동", "score": 20, "passed": True})
                        score_card.append({"factor": "EMA 단기 정배열 추세 (9 > 20)", "score": 80, "passed": True})
                    return 100.0
                else:
                    if score_card is not None:
                        score_card.append({"factor": "상승장 공격모드 가동", "score": 20, "passed": True})
                        score_card.append({"factor": "EMA 단기 정배열 추세 (9 > 20)", "score": 0, "passed": False})
                    return 20.0
            else:
                if ema9 > ema20:
                    return 100.0
                return 30.0  # 이탈 시 감점으로 조기 청산 유도
        else:
            # 🛡️ 하락/횡보장 레짐: 쿨라매기 돌파 (신고가 근접 + 양봉 모멘텀 저격)
            if is_entry:
                is_near = self._safe_get(row, 'is_near_52w_high')
                momentum = self._safe_get(row, 'momentum_candles')
                
                if score_card is not None:
                    score_card.append({"factor": "하락/횡보장 방어모드 가동", "score": 20, "passed": True})
                    
                if is_near:
                    score += 40
                    if score_card is not None:
                        score_card.append({"factor": "52주 신고가 돌파 근접 (쿨라매기 셋업)", "score": 40, "passed": True})
                else:
                    if score_card is not None:
                        score_card.append({"factor": "52주 신고가 돌파 근접 (쿨라매기 셋업)", "score": 0, "passed": False})
                        
                if momentum:
                    score += 40
                    if score_card is not None:
                        score_card.append({"factor": "단기 상승 모멘텀 (연속 양봉)", "score": 40, "passed": True})
                else:
                    if score_card is not None:
                        score_card.append({"factor": "단기 상승 모멘텀 (연속 양봉)", "score": 0, "passed": False})
                
                return 20.0 + score
            else:
                if ema9 > ema20:
                    return 100.0
                return 30.0
