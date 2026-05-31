from app.strategies.base_strategy import BaseStrategy

def get_strategy(strategy_type: str) -> BaseStrategy:
    """
    설정된 문자열 식별자를 바탕으로 해당 전략의 격리 인스턴스를 반환합니다 (팩토리 패턴).
    순환 참조(Circular Imports)를 원천 방지하기 위해 지연 임포트(Lazy Import) 방식을 사용합니다.
    """
    if not strategy_type:
        strategy_type = "regime_switching"
        
    strategy_type = strategy_type.lower()
    
    if strategy_type in ["strategy_a", "stockauto_v1"]:
        from app.strategies.strategy_a import StrategyA
        return StrategyA()
        
    elif strategy_type == "strategy_b":
        from app.strategies.strategy_b import StrategyB
        return StrategyB()
        
    elif strategy_type in ["strategy_c", "complex"]:
        from app.strategies.strategy_c import StrategyC
        return StrategyC()
        
    elif strategy_type == "exploded_c":
        from app.strategies.exploded_c import ExplodedC
        return ExplodedC()
        
    elif strategy_type == "senior_simple":
        from app.strategies.senior_simple import SeniorSimple
        return SeniorSimple()
        
    elif strategy_type == "qullamaggie":
        from app.strategies.qullamaggie import Qullamaggie
        return Qullamaggie()
        
    elif strategy_type == "obv_only":
        from app.strategies.obv_only import ObvOnly
        return ObvOnly()
        
    elif strategy_type == "rsi_bb_only":
        from app.strategies.rsi_bb_only import RsiBbOnly
        return RsiBbOnly()
        
    elif strategy_type == "ema_only":
        from app.strategies.ema_only import EmaOnly
        return EmaOnly()
        
    elif strategy_type == "vwap_only":
        from app.strategies.vwap_only import VwapOnly
        return VwapOnly()
        
    elif strategy_type == "orb_only":
        from app.strategies.orb_only import OrbOnly
        return OrbOnly()
        
    elif strategy_type == "rsi2_connors":
        from app.strategies.rsi2_connors import Rsi2Connors
        return Rsi2Connors()
        
    elif strategy_type == "bb_squeeze":
        from app.strategies.bb_squeeze import BbSqueeze
        return BbSqueeze()
        
    elif strategy_type == "regime_switching":
        from app.strategies.regime_switching import RegimeSwitching
        return RegimeSwitching()
        
    else:
        # 매칭 실패 시 기본값으로 '마스터 레짐스위칭' 반환
        from app.strategies.regime_switching import RegimeSwitching
        return RegimeSwitching()
