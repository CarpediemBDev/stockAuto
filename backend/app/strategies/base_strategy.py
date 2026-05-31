import pandas as pd
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    모든 트레이딩 전략이 상속받아야 하는 추상 베이스 클래스입니다.
    기본 변수(비중 할당, 손절선 배수, 스마트 익절 마진)의 디폴트값을 정의합니다.
    """
    
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
        """pandas Series와 dict 모두에서 안전하게 값을 추출하기 위한 유틸리티 메서드입니다."""
        if isinstance(row, dict):
            return row.get(key, default)
        elif isinstance(row, pd.Series):
            if key in row.index:
                val = row[key]
                return default if pd.isna(val) else val
            return default
        else:
            try:
                val = getattr(row, key, default)
                return default if pd.isna(val) else val
            except:
                return default
