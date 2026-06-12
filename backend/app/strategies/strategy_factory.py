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
        
    elif strategy_type in ["strategy_c_ep", "complex_ep"]:
        from app.strategies.strategy_c_ep import StrategyCEP
        return StrategyCEP()
        
    elif strategy_type in ["strategy_c_aggressive", "complex_aggressive"]:
        from app.strategies.strategy_c_aggressive import StrategyCAggressive
        return StrategyCAggressive()
        
    elif strategy_type in ["asqs", "supernova_squeeze"]:
        from app.strategies.asqs import ASQS
        return ASQS()
        
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

    elif strategy_type in ["double_bb_reversion", "double_bb"]:
        from app.strategies.double_bb_reversion import DoubleBbReversion
        return DoubleBbReversion()

    elif strategy_type == "episodic_pivot":
        from app.strategies.episodic_pivot import EpisodicPivot
        return EpisodicPivot()
        
    elif strategy_type == "vcp_breakout":
        from app.strategies.vcp_breakout import VcpBreakout
        return VcpBreakout()
        
    elif strategy_type == "pairs_trading":
        from app.strategies.pairs_trading import PairsTrading
        return PairsTrading()
        
    elif strategy_type == "weekend_trend":
        from app.strategies.weekend_trend import WeekendTrend
        return WeekendTrend()
        
    elif strategy_type == "darvas_box":
        from app.strategies.darvas_box import DarvasBox
        return DarvasBox()
        
    elif strategy_type == "zscore_reversion":
        from app.strategies.zscore_reversion import ZscoreReversion
        return ZscoreReversion()
        
    elif strategy_type == "heikin_ashi":
        from app.strategies.heikin_ashi import HeikinAshi
        return HeikinAshi()
        
    elif strategy_type == "ichimoku_kumo":
        from app.strategies.ichimoku_kumo import IchimokuKumo
        return IchimokuKumo()
        
    elif strategy_type == "parabolic_sar":
        from app.strategies.parabolic_sar import ParabolicSar
        return ParabolicSar()
        
    elif strategy_type == "supertrend":
        from app.strategies.supertrend import SuperTrend
        return SuperTrend()
        
    elif strategy_type == "hma_swing":
        from app.strategies.hma_swing import HmaSwing
        return HmaSwing()
        
    elif strategy_type == "coppock_curve":
        from app.strategies.coppock_curve import CoppockCurve
        return CoppockCurve()
        
    elif strategy_type == "elder_ray":
        from app.strategies.elder_ray import ElderRay
        return ElderRay()
        
    elif strategy_type == "woodies_cci":
        from app.strategies.woodies_cci import WoodiesCci
        return WoodiesCci()
        
    elif strategy_type == "pivot_point":
        from app.strategies.pivot_point import PivotPoint
        return PivotPoint()
        
    elif strategy_type == "fisher_transform":
        from app.strategies.fisher_transform import FisherTransform
        return FisherTransform()
        
    elif strategy_type == "keltner_reversion":
        from app.strategies.keltner_reversion import KeltnerReversion
        return KeltnerReversion()
        
    elif strategy_type == "larry_williams":
        from app.strategies.larry_williams import LarryWilliams
        return LarryWilliams()
        
    elif strategy_type == "volume_filtered_cross":
        from app.strategies.volume_filtered_cross import VolumeFilteredCross
        return VolumeFilteredCross()

    elif strategy_type == "pdufa_calendar":
        from app.strategies.pdufa_calendar import PdufaCalendar
        return PdufaCalendar()
        
    elif strategy_type == "insider_buying":
        from app.strategies.insider_buying import InsiderBuying
        return InsiderBuying()
        
    elif strategy_type == "short_squeeze":
        from app.strategies.short_squeeze import ShortSqueeze
        return ShortSqueeze()
        
    elif strategy_type == "dark_pool":
        from app.strategies.dark_pool import DarkPool
        return DarkPool()
        
    elif strategy_type == "gamma_flip":
        from app.strategies.gamma_flip import GammaFlip
        return GammaFlip()
        
    elif strategy_type == "max_pain":
        from app.strategies.max_pain import MaxPain
        return MaxPain()
        
    elif strategy_type == "wyckoff_spring":
        from app.strategies.wyckoff_spring import WyckoffSpring
        return WyckoffSpring()
        
    elif strategy_type == "morning_gap_fade":
        from app.strategies.morning_gap_fade import MorningGapFade
        return MorningGapFade()
        
    elif strategy_type == "social_buzz":
        from app.strategies.social_buzz import SocialBuzz
        return SocialBuzz()
        
    elif strategy_type == "cross_asset":
        from app.strategies.cross_asset import CrossAsset
        return CrossAsset()
        
    elif strategy_type == "order_flow":
        from app.strategies.order_flow import OrderFlow
        return OrderFlow()
        
    elif strategy_type == "volume_profile":
        from app.strategies.volume_profile import VolumeProfile
        return VolumeProfile()
        
    elif strategy_type == "turn_of_month":
        from app.strategies.turn_of_month import TurnOfMonth
        return TurnOfMonth()
        
    elif strategy_type == "supernova":
        from app.strategies.supernova import Supernova
        return Supernova()
        
    elif strategy_type == "panic_dip_buy":
        from app.strategies.panic_dip_buy import PanicDipBuy
        return PanicDipBuy()
        
    elif strategy_type == "first_red":
        from app.strategies.first_red import FirstRedDay
        return FirstRedDay()
        
    elif strategy_type == "pump_run_pull":
        from app.strategies.pump_run_pull import PumpRunPullback
        return PumpRunPullback()
        
    elif strategy_type == "pre_gapper":
        from app.strategies.pre_gapper import PreMarketGapper
        return PreMarketGapper()
        
    elif strategy_type == "float_rot":
        from app.strategies.float_rot import FloatRotation
        return FloatRotation()
        
    elif strategy_type == "sympathy":
        from app.strategies.sympathy import SympathyPlay
        return SympathyPlay()
        
    elif strategy_type == "warrant_arb":
        from app.strategies.warrant_arb import WarrantArbitrage
        return WarrantArbitrage()
        
    elif strategy_type == "earn_drift":
        from app.strategies.earn_drift import EarningsGapDrift
        return EarningsGapDrift()
        
    elif strategy_type == "offering_reb":
        from app.strategies.offering_reb import OfferingRebound
        return OfferingRebound()
        
    elif strategy_type == "parabolic_blow":
        from app.strategies.parabolic_blow import ParabolicBlowoff
        return ParabolicBlowoff()
        
    elif strategy_type == "double_bot":
        from app.strategies.double_bot import DoubleBottom
        return DoubleBottom()
        
    elif strategy_type == "overnight_gap":
        from app.strategies.overnight_gap import OvernightGap
        return OvernightGap()
        
    elif strategy_type == "death_rebound":
        from app.strategies.death_rebound import DeathRebound
        return DeathRebound()
        
    elif strategy_type == "relative_str":
        from app.strategies.relative_str import RelativeStrength
        return RelativeStrength()
        
    elif strategy_type == "bollinger_tr":
        from app.strategies.bollinger_tr import BollingerTrend
        return BollingerTrend()
        
    elif strategy_type == "macd_diverg":
        from app.strategies.macd_diverg import MacdDivergence
        return MacdDivergence()
        
    elif strategy_type == "stoch_extreme":
        from app.strategies.stoch_extreme import StochExtreme
        return StochExtreme()
        
    elif strategy_type == "keltner_tr":
        from app.strategies.keltner_tr import KeltnerTrend
        return KeltnerTrend()
        
    elif strategy_type == "triple_ema":
        from app.strategies.triple_ema import TripleEma
        return TripleEma()
        
    elif strategy_type == "range_contra":
        from app.strategies.range_contra import RangeContraction
        return RangeContraction()
        
    elif strategy_type == "vol_spike_brk":
        from app.strategies.vol_spike_brk import VolSpikeBreakout
        return VolSpikeBreakout()
        
    elif strategy_type == "pivot_rebound":
        from app.strategies.pivot_rebound import PivotRebound
        return PivotRebound()
        
    elif strategy_type == "vix_hedging":
        from app.strategies.vix_hedging import VixHedging
        return VixHedging()
        
    elif strategy_type == "premarket_breakout":
        from app.strategies.premarket_breakout import PremarketBreakout
        return PremarketBreakout()
        
    elif strategy_type == "trend_stabilization":
        from app.strategies.trend_stabilization import TrendStabilization
        return TrendStabilization()
        
    else:
        # 매칭 실패 시 기본값으로 '마스터 레짐스위칭' 반환
        from app.strategies.regime_switching import RegimeSwitching
        return RegimeSwitching()
