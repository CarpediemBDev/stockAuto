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
    


    def _get_prefix_for_strategy(self, strategy_type: str) -> str:
        prefix_map = {
            "regime_switching": "RS_",
            "episodic_pivot": "EP_",
            "senior_simple": "SS_",
            "qullamaggie": "QM_",
            "obv_only": "OB_",
            "rsi_bb_only": "RB_",
            "ema_only": "EM_",
            "vwap_only": "VW_",
            "orb_only": "OR_",
            "rsi2_connors": "RC_",
            "bb_squeeze": "BS_",
            "strategy_a": "SA_",
            "strategy_b": "SB_",
            "strategy_c": "SC_",
            "exploded_c": "XC_",
            "asqs": "ASQS_"
        }
        return prefix_map.get(strategy_type, "ST_")

    def _get_name_for_strategy(self, strategy_type: str) -> str:
        if not strategy_type:
            return "미지정 전략"

        try:
            from app.translations.translator import Translator
            return Translator.translate_strategy(strategy_type, "ko")
        except Exception:
            return f"단일 전략 ({strategy_type})"

    def __init__(self, strategy_type: str = "multi_slot"):
        if not strategy_type:
            strategy_type = "multi_slot"
            
        strategy_type = strategy_type.lower()
        
        if strategy_type == "multi_slot":
            # 2슬롯 분할 모드 (기본값)
            self.SLOTS = {
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
        elif strategy_type in ["three_slot", "multi_slot_3"]:
            # 3슬롯 분할 모드 (EP 30% : ASQS 30% : RS 40%)
            self.SLOTS = {
                "episodic_pivot": {
                    "weight": 0.30,
                    "prefix": "EP_",
                    "name": "에피소딕 피벗 (Episodic Pivot)",
                    "strategy_key": "episodic_pivot"
                },
                "asqs": {
                    "weight": 0.30,
                    "prefix": "ASQS_",
                    "name": "ASQS 돌파 (ASQS Breakout)",
                    "strategy_key": "asqs"
                },
                "regime_switching": {
                    "weight": 0.40,
                    "prefix": "RS_",
                    "name": "마스터 레짐스위칭 V2",
                    "strategy_key": "regime_switching"
                }
            }
        else:
            # 단일 전략 100% 모드
            prefix = self._get_prefix_for_strategy(strategy_type)
            name = self._get_name_for_strategy(strategy_type)
            self.SLOTS = {
                strategy_type: {
                    "weight": 1.0,
                    "prefix": prefix,
                    "name": name,
                    "strategy_key": strategy_type
                }
            }
            
        # 각 슬롯별 전략 인스턴스를 메모리에 지연 적재(Lazy Load) 및 캐싱
        self.strategies = {
            slot_key: get_strategy(cfg["strategy_key"])
            for slot_key, cfg in self.SLOTS.items()
        }
        logger.info(f"[MultiStrategyManager] Segmented {len(self.SLOTS)}-Slot Modular Core Engine initialized successfully for strategy_type: {strategy_type}")

    def calculate_slots_allocation(self, total_asset_usd: float, cash_balance_usd: float, holdings: list, sentiment: str = "BULLISH", session: str = "REGULAR_MARKET") -> dict:
        """
        각 슬롯별로 현재의 주식 평가액과 격리된 예수금을 수학적 보존 법칙 하에 정밀 계산합니다.
        
        - total_asset_usd: 계좌의 총 자산 가치 (현금 + 주식 평가금)
        - cash_balance_usd: 계좌의 총 실제 가용 현금(예수금)
        - holdings: 데이터베이스의 Holdings 레코드 리스트
        - sentiment: 현재 시장 레짐 (BULLISH, BEARISH, NEUTRAL)
        - session: 현재 시장 세션 (PRE_MARKET, REGULAR_MARKET, AFTER_HOURS, CLOSED)
        """
        # 1. 각 슬롯별 보유 종목의 평가액 실시간 합산
        slot_stock_values = {slot_key: 0.0 for slot_key in self.SLOTS}
        
        for h in holdings:
            qty = h.quantity
            # 현재 평가가치는 highest_price 또는 avg_price로 우선 활용하고, 스케너 루프에서 보정 가능
            price = getattr(h, 'current_price', None) or h.highest_price or h.avg_price
            
            slot_key = h.strategy_type
            if slot_key in slot_stock_values:
                slot_stock_values[slot_key] += qty * price
            else:
                # 매핑되지 않는 경우 기본적으로 첫번째 슬롯에 가산
                first_slot_key = list(self.SLOTS.keys())[0]
                if first_slot_key in slot_stock_values:
                    slot_stock_values[first_slot_key] += qty * price
                
        # 2. 엄격 격리 지분에 기반한 수학적 보존 분배 공식 적용
        slot_allocations = {}
        
        # 각 슬롯별 자본 배정(Allocation) 지분 가중치 설정
        # 하락장이라고 해서 지분 자체가 증발하지 않도록 weight는 항상 고정
        slot_weights = {
            slot_key: cfg["weight"]
            for slot_key, cfg in self.SLOTS.items()
        }
        
        # 총 가중치 합산 (무오류 처리를 위해 분모 계산)
        total_weight = sum(slot_weights.values())
        denom_weight = total_weight if total_weight > 0 else 1.0
        
        for slot_key, cfg in self.SLOTS.items():
            weight = slot_weights[slot_key]
            
            # 💡 [보존의 법칙 가드] 실제 전체 예수금을 가중치 지분 비율에 따라 정확히 비례 분배
            slot_cash = cash_balance_usd * (weight / denom_weight)
            
            # 해당 슬롯의 주식 평가 가치
            slot_stock_val = slot_stock_values[slot_key]
            
            # [시장 세션 방어 로직] 비정규장(PRE_MARKET, AFTER_HOURS)인 경우 신규 진입 예산 50% 삭감
            if session in ("PRE_MARKET", "AFTER_HOURS"):
                slot_cash = slot_cash * 0.5
                logger.info(f"[MultiStrategyManager] {session} detected. Applied 50% penalty to cash budget for slot {slot_key}.")

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
                         
        return focused
