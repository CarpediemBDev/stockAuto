"""백테스트 엔진 자율 슬롯(지수 레버리지 레짐) 경로 회귀 테스트.

핵심 계약:
1. 신호 지수(QQQ) 상태기계 IN 확정 → 자산(QLD) 전액 매수, OUT 확정 → 전량 청산
2. 룩어헤드 차단 — 매수는 상태가 IN이 된 '이후' 봉에서 체결(직전 완결봉 상태로 판정)
3. 벤치마크(use_filter=False)는 자산을 사서 계속 보유(청산 없음)
4. 자율 슬롯은 일봉(1d) 전용 — 다른 인터벌은 명확히 거부
5. 스캐너 경로는 무영향 (별도 파일 test_leveraged_regime.py가 상태기계 계약 보증)

네트워크를 쓰지 않도록 prepare_data를 우회하고 합성 시계열을 직접 주입한다.
"""
import numpy as np
import pandas as pd
import pytest

from app.backtests.backtest_engine import BacktestSimulator


def _make_sim(strategy_type, asset, qqq_close, asset_close, timeline_idx, sma_period=50):
    sim = BacktestSimulator(
        tickers=[asset],
        start_date="2020-01-01",
        end_date="2020-12-31",
        interval="1d",
        initial_cash=10000.0,
        strategy_type=strategy_type,
    )
    # 상태기계를 작은 SMA로 축소해 짧은 합성 시계열로 검증 (신호 로직 자체는 동일)
    sim.strategy.sma_period = sma_period
    sim.qqq_data = pd.DataFrame({"Close": qqq_close})
    qm = pd.DataFrame({"Close": qqq_close.reindex(timeline_idx)})
    qm["regime"] = "BULLISH"
    sim.qqq_metrics = qm
    sim.timeline = list(timeline_idx)
    am = pd.DataFrame({"Close": asset_close})
    sim.processed_metrics = {asset: am}
    sim.tickers_data = {asset: am}
    return sim


def _up_then_crash_index():
    idx = pd.date_range("2020-01-01", periods=140, freq="B")
    rise = np.linspace(100.0, 160.0, 90)   # 90봉 상승 → SMA50 위 확정(IN)
    crash = np.linspace(160.0, 100.0, 50)  # 50봉 급락 → SMA50 아래 확정(OUT)
    qqq = pd.Series(np.concatenate([rise, crash]), index=idx)
    qld = pd.Series(
        np.concatenate([np.linspace(50.0, 110.0, 90), np.linspace(110.0, 60.0, 50)]),
        index=idx,
    )
    return idx, qqq, qld


class TestAutonomousBacktest:
    def test_regime_buys_on_in_then_sells_on_out(self):
        idx, qqq, qld = _up_then_crash_index()
        sim = _make_sim("leveraged_regime", "QLD", qqq, qld, idx, sma_period=50)

        report = sim.run()
        logs = sim.broker.trade_logs
        buys = [l for l in logs if l["trade_type"] == "BUY"]
        sells = [l for l in logs if l["trade_type"] == "SELL"]

        assert len(buys) >= 1, "IN 확정 시 자산 매수가 발생해야 한다"
        assert len(sells) >= 1, "OUT 확정 시 전량 청산이 발생해야 한다"
        assert buys[0]["ticker"] == "QLD"
        assert buys[0]["timestamp"] < sells[0]["timestamp"]
        # 같은 기간 QQQ 벤치마크 수익률이 리포트에 포함(공정 비교 근거)
        assert "qqq_bench_return_rate" in report

    def test_no_lookahead_entry_lags_state(self):
        idx, qqq, qld = _up_then_crash_index()
        sim = _make_sim("leveraged_regime", "QLD", qqq, qld, idx, sma_period=50)
        state = sim.strategy.compute_state_series(qqq)
        first_in_ts = state[state == "IN"].index[0]

        sim.run()
        buy_ts = [l for l in sim.broker.trade_logs if l["trade_type"] == "BUY"][0]["timestamp"]

        # 직전 완결봉 상태로 집행하므로 매수는 IN 최초 확정 '이후' 봉이라야 룩어헤드가 없다
        assert buy_ts > first_in_ts
        # 체결가는 매수 봉의 자산 종가와 일치(당봉 체결)
        assert sim.broker.trade_logs[0]["price"] == pytest.approx(float(qld.loc[buy_ts]))

    def test_benchmark_buys_and_holds(self):
        idx, qqq, _ = _up_then_crash_index()
        # 벤치마크는 QQQ 자산을 그대로 보유
        sim = _make_sim("benchmark_qqq_hold", "QQQ", qqq, qqq, idx)

        sim.run()
        logs = sim.broker.trade_logs
        buys = [l for l in logs if l["trade_type"] == "BUY"]
        sells = [l for l in logs if l["trade_type"] == "SELL"]

        assert len(buys) == 1, "벤치마크는 최초 1회만 매수한다"
        assert len(sells) == 0, "벤치마크는 청산하지 않고 계속 보유한다"
        assert buys[0]["ticker"] == "QQQ"

    def test_autonomous_rejects_non_daily_interval(self):
        sim = BacktestSimulator(
            tickers=["QLD"],
            start_date="2020-01-01",
            end_date="2020-12-31",
            interval="1h",
            initial_cash=10000.0,
            strategy_type="leveraged_regime",
        )
        with pytest.raises(ValueError, match="일봉"):
            sim.run()


class TestTournamentAutonomousParticipant:
    """아레나 토너먼트에 병합되는 자율 참가자 dict 정형(_shape_autonomous_result) — 네트워크 미사용."""

    def _fake_report(self):
        return {
            "initial_cash": 10000.0,
            "final_value": 12000.0,
            "total_pnl": 2000.0,
            "total_return_rate": 20.0,
            "mdd": -15.0,
            "total_trades": 1,
            "win_rate": 100.0,
            "profit_factor": 3.0,
            "qqq_bench_return_rate": 12.0,
            "annualized_return": 18.0,
            "sharpe_ratio": 0.7,
            "calmar_ratio": 0.4,
            "trade_logs": [
                {"timestamp": pd.Timestamp("2020-03-02"), "ticker": "QLD",
                 "trade_type": "BUY", "price": 50.0, "quantity": 100, "realized_pnl": 0.0},
                {"timestamp": pd.Timestamp("2020-09-01"), "ticker": "QLD",
                 "trade_type": "SELL", "price": 70.0, "quantity": 100, "realized_pnl": 2000.0},
            ],
            "equity_curve": [
                {"timestamp": pd.Timestamp("2020-03-02"), "cash": 0.0, "holdings_value": 5000.0, "total": 5000.0},
                {"timestamp": pd.Timestamp("2020-09-01"), "cash": 12000.0, "holdings_value": 0.0, "total": 12000.0},
            ],
        }

    def test_shape_matches_tournament_participant_contract(self):
        from app.admin.backtest_runner import _shape_autonomous_result

        result = _shape_autonomous_result("leveraged_regime", self._fake_report())

        # 스캐너 참가자와 동일 키가 모두 채워져야 아레나가 무변경 렌더 가능
        for key in ("strategy_type", "name", "final_value", "total_pnl", "total_return_rate",
                    "mdd", "total_trades", "win_rate", "ticker_stats", "equity_curve"):
            assert key in result, f"참가자 dict에 '{key}' 키가 없습니다"

        assert result["strategy_type"] == "leveraged_regime"
        assert isinstance(result["name"], str) and result["name"]
        assert result["total_return_rate"] == 20.0
        # 매수/매도 통계가 종목별로 집계돼야 한다
        assert result["ticker_stats"]["QLD"] == {"buys": 1, "sells": 1, "pnl": 2000.0}
        # equity_curve 타임스탬프는 JSON 직렬화 가능한 문자열이라야 한다
        assert len(result["equity_curve"]) == 2
        assert isinstance(result["equity_curve"][0]["timestamp"], str)


class TestLowFrequencyEligibility:
    """아레나 랭킹 게이트 — 저빈도(자율/보유형)는 거래 횟수 대신 관측 기간으로 표본 적정성 판정."""

    def _report(self, trades, obs, ret=30.0, pf=0.0):
        return {
            "total_trades": trades, "observation_days": obs,
            "total_return_rate": ret, "qqq_bench_return_rate": 12.0,
            "sharpe_ratio": 0.9, "sortino_ratio": 1.2, "calmar_ratio": 0.5,
            "profit_factor": pf, "mdd": -20.0,
        }

    def test_low_freq_hold_becomes_eligible(self):
        from app.backtests.backtest_metrics import assess_strategy_report
        # 보유형: 매도 0회·PF 0·관측 250거래일·+30% → 저빈도 판정 시 eligible
        res = assess_strategy_report("leveraged_regime", self._report(0, 250), low_frequency=True)
        assert res["selection_eligible"] is True

    def test_same_report_ineligible_under_trade_gate(self):
        from app.backtests.backtest_metrics import assess_strategy_report
        # 기본(거래횟수 게이트): 0회 << 15회 → ineligible (스캐너 동작 보존)
        res = assess_strategy_report("leveraged_regime", self._report(0, 250), low_frequency=False)
        assert res["selection_eligible"] is False

    def test_low_freq_requires_min_observation(self):
        from app.backtests.backtest_metrics import assess_strategy_report
        # 관측 기간이 짧으면(30 < 60거래일) 저빈도라도 ineligible
        res = assess_strategy_report("leveraged_regime", self._report(1, 30, pf=999.9), low_frequency=True)
        assert res["selection_eligible"] is False

    def test_low_freq_loss_ineligible(self):
        from app.backtests.backtest_metrics import assess_strategy_report
        # 손실이면 저빈도라도 ineligible
        res = assess_strategy_report("leveraged_regime", self._report(1, 250, ret=-5.0), low_frequency=True)
        assert res["selection_eligible"] is False


class TestTournamentTickerCap:
    """아레나 동적 종목 상한 — 1시간봉 대항전이 완주하도록 종목 수를 제한."""

    def test_dedup_and_priority_order(self):
        from app.admin.backtest_runner import _prioritize_and_cap_tickers
        # 보유 → 거래 → 관심 순, 중복 제거, 대문자화, 빈값 스킵
        res = _prioritize_and_cap_tickers(
            holding_tickers=["aapl", "MSFT"],
            trade_tickers=["MSFT", "nvda"],
            watch_tickers=["nvda", "TSLA", ""],
            max_n=10,
        )
        assert res == ["AAPL", "MSFT", "NVDA", "TSLA"]

    def test_cap_limits_count_preserving_order(self):
        from app.admin.backtest_runner import _prioritize_and_cap_tickers
        many = [f"T{i}" for i in range(100)]
        res = _prioritize_and_cap_tickers(many, [], [], max_n=40)
        assert len(res) == 40
        assert res[0] == "T0" and res[-1] == "T39"
