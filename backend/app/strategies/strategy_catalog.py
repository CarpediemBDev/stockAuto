from dataclasses import dataclass
from enum import Enum


class StrategyDataBasis(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    OHLCV_PROXY = "OHLCV_PROXY"
    SYNTHETIC = "SYNTHETIC"


@dataclass(frozen=True)
class StrategyDataProfile:
    basis: StrategyDataBasis
    selection_eligible: bool
    reason: str


_DEFAULT_PROFILE = StrategyDataProfile(
    basis=StrategyDataBasis.MARKET_DATA,
    selection_eligible=True,
    reason="실제 OHLCV와 그로부터 계산한 기술 지표만 사용합니다.",
)


_STRATEGY_PROFILES = {
    "pdufa_calendar": StrategyDataProfile(
        basis=StrategyDataBasis.SYNTHETIC,
        selection_eligible=False,
        reason="실제 FDA 일정 대신 날짜의 90일 주기 대리값을 사용합니다.",
    ),
    "insider_buying": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 SEC Form 4 대신 저가와 상대 거래량으로 내부자 매수를 추정합니다.",
    ),
    "short_squeeze": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 공매도 잔고와 대차 비용 없이 가격과 거래량으로 숏스퀴즈를 추정합니다.",
    ),
    "dark_pool": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 다크풀 체결 대신 최대 거래량 봉의 가격을 사용합니다.",
    ),
    "institutional_follow": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 기관/외인 수급 데이터의 생산자가 없어 거래량 폭증·20일선 눌림목 대리 지표만 사용하며, 3년 실측에서 QQQ 대비 약 -81%p 언더퍼폼했습니다(2026-08-02 현황판).",
    ),
    "gamma_flip": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 옵션 GEX 대신 EMA20 상하 위치를 감마 플립으로 대체합니다.",
    ),
    "max_pain": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 옵션 미결제약정 없이 VWAP을 맥스페인 가격으로 대체합니다.",
    ),
    "social_buzz": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 소셜 언급량 대신 가격 모멘텀과 상대 거래량을 사용합니다.",
    ),
    "cross_asset": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 DXY와 금리 데이터 대신 QQQ 레짐을 교차자산 필터로 사용합니다.",
    ),
    "order_flow": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 체결 방향 데이터 없이 봉 위치와 거래량으로 주문 흐름을 추정합니다.",
    ),
    "volume_profile": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="가격대별 체결량 대신 최대 거래량 봉 가격을 POC로 사용합니다.",
    ),
    "float_rot": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 유통주식 수 없이 상대 거래량으로 회전율을 추정합니다.",
    ),
    "sympathy": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 테마와 선도주 관계 없이 가격과 거래량만으로 동조 종목을 추정합니다.",
    ),
    "warrant_arb": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 워런트 가격과 전환 조건 없이 보통주 가격 패턴만 사용합니다.",
    ),
    "earn_drift": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 실적 발표와 서프라이즈 데이터 없이 갭 상승을 실적 이벤트로 추정합니다.",
    ),
    "offering_reb": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="실제 증자 공시 없이 급락과 거래량으로 오퍼링을 추정합니다.",
    ),
    "premarket_breakout": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="세션별 프리마켓 데이터 대신 직전 10개 봉의 고가를 사용합니다.",
    ),
    "pairs_trading": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="공적분 검정과 숏 레그 없이 QQQ 대비 가격비율만 사용합니다.",
    ),
    "first_red": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="숏 전략 명칭과 달리 현재 백테스트 브로커는 롱 주문만 지원합니다.",
    ),
    "parabolic_blow": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="청산 전략 명칭과 달리 현재 백테스트 브로커는 롱 주문만 지원합니다.",
    ),
    "pre_gapper": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="페니주(is_penny)와 프리마켓 갭 셋업 프록시(is_pre_gapper_setup)에 의존 — 비페니·정규장 유니버스에선 구조적으로 발화하지 않습니다.",
    ),
    "supernova": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="페니주(is_penny)와 슈퍼노바 급등 셋업 프록시(is_supernova_setup)에 의존하는 저유동 소형주 전용 전략입니다.",
    ),
    "panic_dip_buy": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="페니주(is_penny)와 패닉 급락 셋업 프록시(is_panic_drop)에 의존 — 비페니 유니버스에선 발화하지 않습니다.",
    ),
    "pump_run_pull": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="페니주(is_penny)와 펌프-런-눌림 셋업 프록시(is_pump_run_pullback)에 의존하는 저유동 소형주 전용 전략입니다.",
    ),
    "vix_hedging": StrategyDataProfile(
        basis=StrategyDataBasis.OHLCV_PROXY,
        selection_eligible=False,
        reason="개별 종목 OHLCV가 아닌 외부 VIX 변동성 지수 연계 플래그(is_vix_ok)에 진입을 의존합니다.",
    ),
}


def get_strategy_data_profile(strategy_type: str) -> StrategyDataProfile:
    normalized = (strategy_type or "").lower()
    return _STRATEGY_PROFILES.get(normalized, _DEFAULT_PROFILE)
