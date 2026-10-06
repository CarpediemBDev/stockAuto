"""백테스트 엔진 목표비중 경로(canary_allocation) + 공용 수량 계획 함수 회귀 테스트.

핵심 계약:
1. 판단일 d의 목표는 d '이후' 봉에서 체결된다(룩어헤드 없음)
2. 리밸런싱은 매도 먼저, 매수 나중
3. 확정 목표가 바뀌지 않으면 매매하지 않는다(월말 반복·밴드 유지)
4. plan_target_weight_orders는 floor(총자산×비중×버퍼/가격)로 차이 수량을 내고, 목표 밖 보유는 전량 매도
5. 목표비중 전략은 신호·보유 티커를 엔진 유니버스에 자동 보충한다

네트워크를 쓰지 않도록 prepare_data를 우회하고 합성 시계열을 주입한다.
"""
import numpy as np
import pandas as pd
import pytest

from app.backtests.backtest_engine import BacktestSimulator
from app.bot.trade_calculations import plan_target_weight_orders
from app.strategies import canary_allocation as ca


class TestPlanTargetWeightOrders:
    def test_floor_with_buffer_and_sell_outside_target(self):
        plan = plan_target_weight_orders(
            10000, {"QQQ": 0.5, "BIL": 0.5}, {"QQQ": 500.0, "BIL": 91.0, "IEF": 95.0},
            {"IEF": 30},
        )
        # QQQ: floor(10000*0.5*0.995/500)=9, BIL: floor(4975/91)=54, IEF 목표 밖 → -30
        assert plan == {"QQQ": 9, "BIL": 54, "IEF": -30}

    def test_partial_reduce(self):
        plan = plan_target_weight_orders(10000, {"QQQ": 0.2, "BIL": 0.8}, {"QQQ": 500.0, "BIL": 100.0}, {"QQQ": 9, "BIL": 49})
        # QQQ floor(1990/500)=3, BIL floor(7960/100)=79
        assert plan == {"QQQ": 3 - 9, "BIL": 79 - 49}

    def test_missing_price_holds(self):
        assert plan_target_weight_orders(10000, {"QQQ": 1.0}, {}, {}) is None

    def test_no_change_gives_empty_plan(self):
        assert plan_target_weight_orders(10000, {"QQQ": 1.0}, {"QQQ": 490.0}, {"QQQ": 20}) == {}


def _sim(targets: pd.DataFrame, prices: dict, idx):
    sim = BacktestSimulator(tickers=[], start_date=str(idx[0].date()), end_date=str(idx[-1].date()),
                            interval="1d", initial_cash=10000.0, strategy_type="canary_allocation")
    sim.timeline = list(idx)
    sim.raw_closes = {t: pd.Series(v, index=idx) for t, v in prices.items()}
    sim.raw_closes["SPY"] = pd.Series(100.0, index=idx)
    qm = pd.DataFrame({"Close": sim.raw_closes["QQQ"]})
    qm["regime"] = "BULLISH"
    sim.qqq_metrics = qm  # 리포트의 QQQ 대조 수익률용
    # 신호 계산은 별도 테스트(test_canary_allocation)가 보증한다. 여기서는 집행만 검증하도록 확정 목표를 주입한다.
    sim.strategy.compute_target_series = lambda closes, nfci, decisions: targets
    return sim


class TestTargetWeightBacktest:
    def test_universe_is_supplemented(self):
        sim = BacktestSimulator(tickers=["QQQ"], start_date="2024-01-01", end_date="2024-12-31",
                                interval="1d", strategy_type="canary_allocation")
        assert set(ca.DATA_TICKERS) | set(ca.HOLD_TICKERS) <= set(sim.tickers)

    def test_executes_after_decision_and_sells_before_buys(self):
        idx = pd.bdate_range("2024-01-01", "2024-03-29")
        d1 = pd.Timestamp("2024-01-31")
        d2 = pd.Timestamp("2024-02-29")
        targets = pd.DataFrame({"QQQ": [1.0, 3 / 7], "IEF": [0.0, 0.0], "BIL": [0.0, 4 / 7]}, index=[d1, d2])
        sim = _sim(targets, {"QQQ": np.linspace(400, 440, len(idx)), "IEF": 95.0, "BIL": 91.5}, idx)
        sim.run()
        logs = sim.broker.trade_logs
        first = logs[0]
        assert first["trade_type"] == "BUY" and first["ticker"] == "QQQ"
        assert pd.Timestamp(first["timestamp"]) > d1  # 판단일 당일이 아닌 다음 봉
        assert pd.Timestamp(first["timestamp"]) == idx[idx > d1][0]
        second_batch = [l for l in logs if pd.Timestamp(l["timestamp"]) > d2]
        assert [l["trade_type"] for l in second_batch] == ["SELL", "BUY"]
        assert second_batch[0]["ticker"] == "QQQ" and second_batch[1]["ticker"] == "BIL"
        assert len(logs) == 3  # 같은 목표가 이어지는 동안 추가 매매 없음

    def test_unchanged_target_never_retrades(self):
        idx = pd.bdate_range("2024-01-01", "2024-06-28")
        months = ca.month_end_dates(idx)
        targets = pd.DataFrame({"QQQ": 0.5, "IEF": 0.0, "BIL": 0.5}, index=months)
        sim = _sim(targets, {"QQQ": 400.0, "IEF": 95.0, "BIL": 91.5}, idx)
        sim.run()
        assert len(sim.broker.trade_logs) == 2  # 첫 진입 QQQ·BIL 매수만

    def test_rejects_intraday_interval(self):
        idx = pd.bdate_range("2024-01-01", "2024-02-28")
        sim = _sim(pd.DataFrame(), {"QQQ": 400.0, "IEF": 95.0, "BIL": 91.5}, idx)
        sim.interval = "1h"
        with pytest.raises(ValueError):
            sim.run()
