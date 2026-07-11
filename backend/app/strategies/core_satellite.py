from app.strategies.base_strategy import BaseStrategy


class CoreSatellite(BaseStrategy):
    """
    🏛️ 코어-새틀라이트 (Core-Satellite) — 복합 자본배분 전략

    단일 종목 스코어링 전략이 아니라, 자본을 두 층으로 격리 배분하는 '복합 전략'이다.
    구성(SATELLITE_SLOTS)이 이 클래스의 단일 출처(SSOT)이며, MultiStrategyManager는
    하드코딩 대신 이 선언을 읽어 슬롯을 생성한다.

    - 코어(70%): `leveraged_regime` — QQQ 200일 SMA 레짐으로 QLD(2x) 보유/현금 대피(자율 슬롯).
    - 새틀라이트(30%): `strategy_c` — 스캐너 기반 종목선택 알파 탐색.

    근거(2026-07-07/09 현황판): 개별종목 타이밍 85종 전패 결론 수용 후, 검증된 견고 속성
    (지수 레버리지 레짐의 다년 QQQ 초과)을 코어로, 기존 알파 탐색을 새틀라이트로 병렬 운용.

    복합 전략 자체는 매 시점 스코어링 대상이 아니므로(하위 슬롯 전략이 각자 스코어링),
    calculate_score는 미발화(0.0)한다.
    """

    # 이 복합 전략이 슬롯 조립 대상임을 알리는 식별 플래그
    is_composite = True

    # (slot_key, weight, prefix) — 구성의 단일 출처. MultiStrategyManager가 이것으로 슬롯을 만든다.
    SATELLITE_SLOTS = (
        ("leveraged_regime", 0.70, "LR_"),
        ("strategy_c", 0.30, "SC_"),
    )

    def __init__(self):
        super().__init__(name="🏛️ 코어-새틀라이트 (레버리지 레짐 70% + 전략C 30%)")

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        """복합 전략은 직접 스코어링하지 않는다(하위 슬롯 전략이 각자 수행). 항상 0점."""
        if score_card is not None:
            score_card.append({
                "factor": "복합 전략 (하위 슬롯 leveraged_regime·strategy_c가 각자 스코어링)",
                "score": 0,
                "passed": False,
            })
        return 0.0
