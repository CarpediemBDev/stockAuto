import pandas as pd
from app.strategies.base_strategy import BaseStrategy


class CrossSectionalMomentum(BaseStrategy):
    """
    🚀 횡단면 모멘텀 (Cross-Sectional Momentum)

    설계 의도 — 트리아지 결론(개별 종목 타이밍형 롱온리 전략 76종 전부가 QQQ 단순보유에
    패배)을 정면으로 뒤집기 위한 '선택형(cross-sectional)' 접근이다. "언제 살까"가 아니라
    "유니버스에서 지금 가장 센 종목이 무엇인가"를 매 시점 겨루어 강자만 담는다.

    구현 원리 — 공유 백테스트 엔진(BacktestSimulator.run)은 매 타임스탬프마다 전 종목을
    채점해 점수 높은 순으로 정렬한 뒤 강한 종목부터 예수금이 소진될 때까지 매수한다
    (backtest_engine.py:901). 따라서 별도 엔진 훅 없이도 '모멘텀 강도 = 점수'로만 채점하면
    엔진이 자연히 상위 모멘텀 종목을 골라 담는 횡단면 근사가 성립한다.

    행동 규칙:
    - 균등 분산: 기본 배분 12% + 최소금액 제한 해제로 다수 종목에 분산(강자에 score_factor
      가중은 엔진 공유 사이징이 부여 → 최강 종목에 자연 집중).
    - 승자 방치(let winners run): 스마트 조기익절 비활성, 넓은 손절·트레일링, 시그널 붕괴
      임계 완화 → regime_switching을 자멸시킨 휩쏘 과매매를 차단하고 추세를 끝까지 태운다.
    - 모멘텀 크래시 가드: QQQ 약세장(BEARISH)에선 진입/유지 점수를 0으로 만들어 전량 현금
      대피(모멘텀 전략 최대 약점인 급락 동반 추락 방지).

    ⚠️ 실행 주기(interval): 반드시 일봉('1d')으로 구동한다. 1시간봉에서는 change_pct가
    20봉=약 3거래일짜리 초단기 신호가 되어 '모멘텀'이 아니라 단기 반전(고점 추격) 함정으로
    작동한다(실측: 1h는 -40%/MDD-47%, 1d는 +42%/MDD-8%, 동일 유니버스·2026-01~05).
    """

    def __init__(self, name: str = "🚀 횡단면 모멘텀 (Cross-Sectional Momentum)"):
        super().__init__(name=name)
        self.base_allocation_pct = 0.12    # 자산의 ~12%씩 균등 분산(약 8종목 지향)
        self.min_allocation_usd = 0.0      # 최소 금액 제한 해제 → 소액도 분산 매수
        self.min_smart_exit_profit = 999.0  # 스마트 조기익절 비활성(승자 방치)

    def get_initial_entry_factor(self, regime: str) -> float:
        # 정찰병 없이 목표 비중까지 즉시 진입. 약세장 차단은 calculate_score가 0점으로 처리.
        return 1.0

    def get_pyramid_trigger(self, stage: int) -> float:
        # 피라미딩(불타기) 미사용 — 종목 간 균등 분산 유지가 목적.
        return 999.0

    def get_cutoff_score(self, regime: str) -> float:
        # 모멘텀 상위 종목만 통과시키는 커트라인.
        return 65.0 if regime == "BULLISH" else 75.0

    def is_signal_collapsed(self, score: float, regime: str) -> bool:
        # 승자 방치: 모멘텀이 사실상 소멸(매우 낮은 점수)했을 때만 청산.
        return score < 20.0

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        # 넓은 손절 — 약세로 완전히 돌아선 종목만 천천히 컷(휩쏘 방지).
        sl_base = 10.0
        sl_mult = 3.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        # 넓은 트레일링 — 상승 추세를 끝까지 태우기 위한 여유 확보.
        ts_base = 12.0
        ts_mult = 4.0
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(ts_base, atr_pct * ts_mult)
        return ts_base

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        # 🛡️ 모멘텀 크래시 가드: 약세장에선 신규 진입·기존 유지 모두 0점 → 현금 대피 유도.
        if regime == "BEARISH":
            return 0.0

        close = self._safe_get(row, 'Close')
        volume = self._safe_get(row, 'Volume')

        # 유동성 관문(거래대금) — 진입 시에만 엄격 적용.
        if is_entry and close * volume < 7400.0:
            return 0.0

        score = 0.0

        # 1) 절대 모멘텀: 20봉 수익률(change_pct). 강할수록 가점, 하락 종목은 감점 배제.
        change_pct = self._safe_get(row, 'change_pct', 0.0)
        if change_pct >= 15.0:
            score += 40
        elif change_pct >= 8.0:
            score += 30
        elif change_pct >= 3.0:
            score += 20
        elif change_pct <= 0.0:
            score -= 20

        # 2) 상대 모멘텀: QQQ 대비 초과강도(relative_strength) + 5연속 초과수익(is_relative_strong).
        rs = self._safe_get(row, 'relative_strength', 0.0)
        if rs > 0:
            score += 25
        else:
            score -= 15
        if self._safe_get(row, 'is_relative_strong', 0.0) >= 1.0:
            score += 15

        # 3) 추세 정배열: EMA 9>20>120 완전 정배열 우대, 단기 정배열은 부분 가점.
        if self._safe_get(row, 'is_triple_ema_up', 0.0) >= 1.0:
            score += 20
        elif self._safe_get(row, 'EMA9') > self._safe_get(row, 'EMA20'):
            score += 10

        # 4) 주도력: 52주 신고가 근접 및 전고점 이격.
        if self._safe_get(row, 'is_near_52w_high', False):
            score += 15
        dist_to_high = self._safe_get(row, 'dist_to_high', -100.0)
        if dist_to_high > -5.0:
            score += 10

        return max(0.0, min(float(score), 100.0))
