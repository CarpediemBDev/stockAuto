import pandas as pd
from abc import ABC, abstractmethod
from contextlib import contextmanager

from app.bot.trade_calculations import DEFAULT_ROLLING_BOX_MINUTES

# 결손 필드 읽기 관찰자. 평시에는 None이라 _safe_get은 기존과 동일하게 동작한다.
# record_missing_fields()로 켜면 "없는 키를 읽어 기본값으로 떨어진" 사건을 수집한다.
_missing_field_observer = None


@contextmanager
def record_missing_fields():
    """블록 안에서 발생한 결손 필드 읽기를 (전략명, 키) 집합으로 모은다.

    _safe_get의 기본값은 "값이 없음"을 "값이 0"으로 바꿔버려 전략을 조용히 퇴화시킨다.
    정적 검사(scripts/check_signal_field_contract.py)는 소스에 리터럴로 적힌 읽기만
    보므로, 실행 시점에 실제로 무엇이 결손이었는지는 여기서만 알 수 있다.
    테스트가 이 관찰자로 "라이브 신호로 채점했을 때 결손 읽기가 없는가"를 검증한다.
    """
    global _missing_field_observer
    previous = _missing_field_observer
    collected = set()
    _missing_field_observer = collected
    try:
        yield collected
    finally:
        _missing_field_observer = previous

class BaseStrategy(ABC):
    """
    모든 트레이딩 전략이 상속받아야 하는 추상 베이스 클래스입니다.
    기본 변수(비중 할당, 손절선 배수, 스마트 익절 마진)의 디폴트값을 정의합니다.
    """
    
    # 자율 슬롯 여부: True인 전략은 스캐너 시그널/손절·트레일링 파이프라인을 우회하고
    # 스케줄러의 전용 경로(process_autonomous_slots)가 직접 집행합니다.
    is_autonomous = False

    # 롤링 박스 트레일링 스탑: 최근 박스 구간의 저점(래칫 단조 증가)을 이탈하면 청산.
    # 절대 최고가 기준 ATR 트레일링이 횡보 구간에서 옛 고점에 앵커링되어 느슨해지는
    # 문제를 보완한다. 기본 비활성 — 백테스트 A/B로 검증된 전략만 True로 opt-in.
    #
    # 박스 길이는 '봉 개수'가 아니라 '시간 길이(분)'로 선언한다. 봉 개수로 두면 같은
    # 값이 라이브(15분봉)와 백테스트(전략 인터벌)에서 서로 다른 실시간 길이를 뜻해
    # 검증 결과가 라이브로 전이되지 않는다. 실제 봉 수 환산은 각 타임프레임에서
    # trade_calculations.resolve_rolling_box_bars가 단독으로 담당한다.
    use_rolling_box_stop = False
    rolling_box_minutes = DEFAULT_ROLLING_BOX_MINUTES

    def __init__(self, name: str = "Base Strategy"):
        self.name = name
        
        # 💡 기본 자금 및 비중 제어 가이드라인 (디폴트: 전략 C 표준형)
        self.base_allocation_pct = 0.40  # 자산의 40% 기본단위
        self.min_allocation_usd = 2000.0 # 최소 $2,000 보장
        self.min_smart_exit_profit = 2.5 # 스마트 익절 최소 마진 2.5%
        
    def get_initial_entry_factor(self, regime: str) -> float:
        """신규 포지션 진입 시점의 비중 비율을 결정합니다."""
        if regime == "BULLISH":
            return 0.15  # 상승장: 정찰병 15% 진입
        elif regime == "BEARISH":
            return 0.30  # 하락장: 비중 30% 제한
        else:
            return 0.50  # 횡보장: 비중 50% 제한

    def get_cutoff_score(self, regime: str) -> float:
        """전략 진입을 위한 스코어 커트라인을 반환합니다."""
        return 85.0 if regime == "BULLISH" else 95.0

    def is_signal_collapsed(self, score: float, regime: str) -> bool:
        """보유 중 주가의 지표 강세 시그널이 붕괴되었는지 여부를 판단합니다."""
        if regime == "BULLISH":
            return score < 40.0
        return score < 50.0

    def get_pyramid_trigger(self, stage: int) -> float:
        """기존 보유 중인 포지션의 추가 매수(불타기) 트리거 수익률을 리턴합니다."""
        if stage == 1:
            return 2.0   # 2단계 추가 매수: 수익률 +2.0% 이상 돌파 시 (+35% 비중)
        elif stage == 2:
            return 4.0   # 3단계 추가 매수: 수익률 +4.0% 이상 돌파 시 (+50% 비중)
        return 999.0     # 3단계 초과 추가 매수 없음

    def get_stop_loss_pct(self, atr: float, price: float) -> float:
        """ATR 변동성에 기반한 동적 손절 폭(%)을 리턴합니다."""
        sl_base = 3.0     # 최소 손절선 3.0%
        sl_mult = 1.5     # ATR 1.5배 승수
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(sl_base, atr_pct * sl_mult)
        return sl_base

    def get_trailing_stop_pct(self, atr: float, price: float) -> float:
        """ATR 변동성에 기반한 동적 트레일링 스탑 폭(%)을 리턴합니다."""
        ts_base = 2.0     # 최소 트레일링 스탑 2.0%
        ts_mult = 1.0     # ATR 1.0배 승수
        if atr > 0:
            atr_pct = (atr / price) * 100
            return max(ts_base, atr_pct * ts_mult)
        return ts_base

    @abstractmethod
    def calculate_score(self, row, regime: str, is_entry: bool = True) -> float:
        """
        주어진 데이터 행(row)을 바탕으로 해당 종목의 강세 스코어(0~100점)를 계산합니다.
        row는 pandas Series(백테스트) 및 dict(실시간 스캐너) 모두 지원해야 하므로,
        안전한 조회를 위해 row.get('필드명') 형태로 작성할 것을 강력히 권장합니다.
        """
        pass

    def _safe_get(self, row, key: str, default=0.0):
        """pandas Series와 dict 모두에서 안전하게 값을 추출하기 위한 유틸리티 메서드입니다.

        주의 - 기본값 0.0은 "값이 0"과 "값이 없음"을 구분하지 못합니다. 라이브 진입
        채점 입력(app/scanner/scanner.py의 details)에 없는 지표를 그대로 읽으면 0.0이
        되어 `close > 지표` 형태의 돌파 조건이 `close > 0.0`으로 퇴화하고, 모든 종목에서
        항상 참이 됩니다. 돌파 기준선·이동평균·거래량 평균처럼 실제 종목에서 0 이하가
        될 수 없는 값은 읽은 뒤 반드시 양수 여부를 확인하고, 준비되지 않았으면 점수를
        내지 말아야 합니다(2026-08-23: darvas_box/donchian_breakout/
        opening_range_breakout이 이 경로로 무차별 진입했습니다).
        """
        if isinstance(row, dict):
            if key not in row:
                self._note_missing_field(key)
                return default
            return row[key]
        elif isinstance(row, pd.Series):
            if key in row.index:
                val = row[key]
                if pd.isna(val):
                    self._note_missing_field(key)
                    return default
                return val
            self._note_missing_field(key)
            return default
        else:
            try:
                val = getattr(row, key, default)
                if pd.isna(val):
                    self._note_missing_field(key)
                    return default
                return val
            except:
                return default

    def _note_missing_field(self, key: str) -> None:
        """결손 필드 읽기를 관찰자에게 알린다(관찰자가 꺼져 있으면 아무 일도 하지 않는다)."""
        if _missing_field_observer is not None:
            _missing_field_observer.add((self.name, key))
