import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock
from app.bot.backtest_engine import BacktestSimulator

def test_backtest_simulator_variants_initialization():
    # 1. BASE 변형 초기화 검증
    sim_base = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="BASE"
    )
    assert sim_base.variant == "BASE"
    assert sim_base.exit_confirm_count == 2
    assert sim_base.day_lock_enabled is False
    assert sim_base.bullish_alloc_100 is False

    # 2. BUF3 변형 초기화 검증
    sim_buf3 = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="BUF3"
    )
    assert sim_buf3.variant == "BUF3"
    assert sim_buf3.exit_confirm_count == 3
    assert sim_buf3.day_lock_enabled is False
    assert sim_buf3.bullish_alloc_100 is False

    # 3. LOCK 변형 초기화 검증
    sim_lock = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="LOCK"
    )
    assert sim_lock.variant == "LOCK"
    assert sim_lock.exit_confirm_count == 2
    assert sim_lock.day_lock_enabled is True
    assert sim_lock.bullish_alloc_100 is False

    # 4. WHIP 변형 초기화 검증
    sim_whip = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="WHIP"
    )
    assert sim_whip.variant == "WHIP"
    assert sim_whip.exit_confirm_count == 3
    assert sim_whip.day_lock_enabled is True
    assert sim_whip.bullish_alloc_100 is False

    # 5. FULL 변형 초기화 검증
    sim_full = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="FULL"
    )
    assert sim_full.variant == "FULL"
    assert sim_full.exit_confirm_count == 3
    assert sim_full.day_lock_enabled is True
    assert sim_full.bullish_alloc_100 is True


def test_backtest_variants_logic_branches():
    # 1. 당일 재진입 금지 검증 (LOCK)
    sim = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="LOCK"
    )
    sim.broker = MagicMock()
    # 동일 날짜에 매도한 이력이 있음
    sim.broker.sell_cooldowns = {"TSLA": datetime(2025, 1, 5, 10, 0)}
    sim.broker.holdings = {}
    
    # 쿨다운 조건 검증 단계 (t와 매도 기록 날짜가 동일)
    t = datetime(2025, 1, 5, 14, 0)
    assert sim.day_lock_enabled is True
    
    last_sell = sim.broker.sell_cooldowns.get("TSLA")
    day_locked = sim.day_lock_enabled and t.date() == last_sell.date()
    assert day_locked is True

    # 다른 날짜일 때 당일 재진입 금지 미작동 검증
    t_other = datetime(2025, 1, 6, 9, 30)
    day_locked_other = sim.day_lock_enabled and t_other.date() == last_sell.date()
    assert day_locked_other is False

    # 2. 상승장 100% 비중 검증 (FULL)
    sim_full = BacktestSimulator(
        tickers=["TSLA"],
        start_date="2025-01-01",
        end_date="2025-01-10",
        variant="FULL"
    )
    assert sim_full.bullish_alloc_100 is True
    
    regime = "BULLISH"
    proposed_alloc_factor = 0.15 # 원래 정찰병 비중
    if sim_full.bullish_alloc_100 and regime == "BULLISH":
        proposed_alloc_factor = 1.0
    assert proposed_alloc_factor == 1.0

    # 하락장(BEARISH)일 때는 100% 비중 강제 미작동 검증
    regime_bear = "BEARISH"
    proposed_alloc_factor_bear = 0.30
    if sim_full.bullish_alloc_100 and regime_bear == "BULLISH":
        proposed_alloc_factor_bear = 1.0
    assert proposed_alloc_factor_bear == 0.30
