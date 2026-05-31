from app.strategies.strategy_factory import get_strategy
from app.core.logging import logger

class MultiStrategyManager:
    """
    🥇 격리형 2슬롯 모듈러 코어 (Modular Multi-Strategy Isolation) 매니저
    - 단일 계좌 예수금을 수학적으로 2개 슬롯으로 완벽 격리 분배하여 동시 가동합니다.
    1. episodic_pivot [50% Cash] (EP_) - 엘리트 거래량 돌파형 스나이퍼
    2. regime_switching [50% Cash] (RS_) - 상승장 한정 불타기 피라미딩 엔진
    """
    
    SLOTS = {
        "episodic_pivot": {
            "weight": 0.50,
            "prefix": "EP_",
            "name": "에피소딕 피벗 (Episodic Pivot)",
            "strategy_key": "episodic_pivot"
        },
        "regime_switching": {
            "weight": 0.50,
            "prefix": "RS_",
            "name": "마스터 레짐스위칭 V2",
            "strategy_key": "regime_switching"
        }
    }
    
    # 🎯 타겟팅할 11대 최정예 급등주/변동성 포트폴리오 (낚시용 종목 포함 완벽 방어 검증용)
    TARGET_TICKERS = {"AKAN", "WNW", "ASTC", "SDA", "HUBC", "MNTS", "ITP", "SES", "AEHL", "ODYS", "PRFX"}

    def __init__(self):
        # 각 슬롯별 전략 인스턴스를 메모리에 지연 적재(Lazy Load) 및 캐싱
        self.strategies = {
            slot_key: get_strategy(cfg["strategy_key"])
            for slot_key, cfg in self.SLOTS.items()
        }
        logger.info("[MultiStrategyManager] Segmented 2-Slot Modular Core Engine initialized successfully.")

    def get_slot_by_holding_ticker(self, holding_ticker: str) -> tuple[str, str] | None:
        """
        보유 종목의 접두사(Prefix)를 분석하여 해당하는 슬롯 키와 순수 티커를 반환합니다.
        예: 'ASQS_ASTC' -> ('asqs', 'ASTC')
        접두사가 없거나 올바르지 않으면 None을 반환합니다.
        """
        if not holding_ticker:
            return None
            
        for slot_key, cfg in self.SLOTS.items():
            prefix = cfg["prefix"]
            if holding_ticker.startswith(prefix):
                clean_ticker = holding_ticker[len(prefix):]
                return slot_key, clean_ticker
        return None

    def get_prefix_for_slot(self, slot_key: str) -> str:
        """슬롯 키에 해당하는 접두사를 반환합니다."""
        return self.SLOTS.get(slot_key, {}).get("prefix", "")

    def make_prefixed_ticker(self, slot_key: str, clean_ticker: str) -> str:
        """순수 티커와 슬롯 키를 결합하여 접두사가 붙은 티커를 생성합니다."""
        prefix = self.get_prefix_for_slot(slot_key)
        return f"{prefix}{clean_ticker.upper()}"

    def calculate_slots_allocation(self, total_asset_usd: float, cash_balance_usd: float, holdings: list, sentiment: str = "BULLISH") -> dict:
        """
        각 슬롯별로 현재의 주식 평가액과 격리된 예수금을 수학적 보존 법칙 하에 정밀 계산합니다.
        
        - total_asset_usd: 계좌의 총 자산 가치 (현금 + 주식 평가금)
        - cash_balance_usd: 계좌의 총 실제 가용 현금(예수금)
        - holdings: 데이터베이스의 Holdings 레코드 리스트
        - sentiment: 현재 시장 레짐 (BULLISH, BEARISH, NEUTRAL)
        """
        # 1. 각 슬롯별 보유 종목의 평가액 실시간 합산
        slot_stock_values = {slot_key: 0.0 for slot_key in self.SLOTS}
        
        for h in holdings:
            ticker = h.ticker
            qty = h.quantity
            # 현재 평가가치는 highest_price 또는 avg_price로 우선 활용하고, 스케너 루프에서 보정 가능
            price = getattr(h, 'current_price', None) or h.highest_price or h.avg_price
            
            parsed = self.get_slot_by_holding_ticker(ticker)
            if parsed:
                slot_key, _ = parsed
                if slot_key in slot_stock_values:
                    slot_stock_values[slot_key] += qty * price
            else:
                # 레거시 일반 종목의 경우 기본적으로 마스터 레짐스위칭 슬롯에 가산
                slot_stock_values["regime_switching"] += qty * price
                
        # 2. 50:50 엄격 격리 지분에 기반한 수학적 보존 분배 공식 적용
        slot_allocations = {}
        
        # 각 슬롯별 자본 배정(Allocation) 지분 가중치 설정 (언제나 50:50 격리)
        # 하락장이라고 해서 지분 자체가 증발하지 않도록 weight는 항상 0.50 고정
        slot_weights = {
            "episodic_pivot": 0.50,
            "regime_switching": 0.50
        }
        
        # 총 가중치 합산 (무오류 처리를 위해 분모 계산)
        total_weight = sum(slot_weights.values())
        denom_weight = total_weight if total_weight > 0 else 1.0
        
        for slot_key, cfg in self.SLOTS.items():
            weight = slot_weights[slot_key]
            
            # 💡 [보존의 법칙 가드] 실제 전체 예수금을 가중치 지분 비율에 따라 정확히 1대1 비례 분배
            # 이 공식을 통해 EP_cash + RS_cash는 항상 실제 cash_balance_usd와 100% 완벽 일치합니다!
            slot_cash = cash_balance_usd * (weight / denom_weight)
            
            # 해당 슬롯의 주식 평가 가치
            slot_stock_val = slot_stock_values[slot_key]
            
            # 슬롯의 실시간 총 자산 가치 = 슬롯 가용 현금 + 슬롯 주식 평가 가치
            slot_total_asset = slot_cash + slot_stock_val
            
            slot_allocations[slot_key] = {
                "weight": weight,
                "name": cfg["name"],
                "prefix": cfg["prefix"],
                "total_asset": slot_total_asset,
                "stock_value": slot_stock_val,
                "cash_balance": slot_cash
            }
            
        return slot_allocations

    def get_focused_tickers(self, all_signals: list) -> set:
        """
        🥇 최정예 종목 Focusing 필터
        - 79개 종목을 다 매수해서 자금이 파편화되는 문제를 막기 위해 작동합니다.
        - 매일 아침 "최근 5일 내 대량 거래량 매집봉 흔적 (RVOL >= 2.0 이상 발생 이력)"이 있고
          유통 물량이 잠잠하게 응축(wick_ratio가 너무 높지 않은 가벼운 매집)된 5~10개 최정예 후보군만 선발합니다.
        """
        candidates = []
        for s in all_signals:
            ticker = s.get("ticker", "")
            details = s.get("details", {})
            rvol = details.get("rvol", 0.0)
            
            # 최근 5일 내 매집봉 흔적 (RVOL >= 2.0 이상 발생 이력 또는 갭상승 흔적)
            has_accumulation = rvol >= 2.0 or details.get("premarket_gap_pct", 0.0) >= 3.0
            
            # 극단적인 고가 위꼬리 음봉 페이크(가짜 돌파 위험)가 높은 종목 제외
            is_safe = details.get("risk", "LOW") != "HIGH"
            
            if has_accumulation and is_safe:
                # 점수 가중치 산출 (RVOL 가속도 + 지수 대비 상대강도 합산)
                score_weight = rvol * 10 + details.get("rs", 0.0)
                candidates.append((ticker, score_weight))
                
        # 가중치 내림차순 정렬
        candidates.sort(key=lambda x: x[1], reverse=True)
        focused = {t for t, _ in candidates[:10]}
        
        # 선별된 종목이 5개 미만인 경우 최정예 포트폴리오 11개 종목에서 부족분만큼 순차 보완하여 유동성/거래 기회 보장
        if len(focused) < 5:
            additional_needed = 5 - len(focused)
            for t in self.TARGET_TICKERS:
                if t not in focused:
                     focused.add(t)
                     additional_needed -= 1
                     if additional_needed <= 0:
                         break
                         
        return focused
