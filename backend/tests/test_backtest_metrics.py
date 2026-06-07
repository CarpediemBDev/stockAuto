from app.bot.backtest_metrics import (
    assess_strategy_report,
    calculate_performance_metrics,
)


def test_calculate_performance_metrics_tracks_drawdown_recovery():
    equity_curve = [
        {"timestamp": "2025-01-02 16:00:00", "total": 10000.0},
        {"timestamp": "2025-01-03 16:00:00", "total": 10200.0},
        {"timestamp": "2025-01-06 16:00:00", "total": 9500.0},
        {"timestamp": "2025-01-10 16:00:00", "total": 10300.0},
    ]

    metrics = calculate_performance_metrics(equity_curve, initial_value=10000.0)

    assert metrics["max_drawdown"] == -6.8627
    assert metrics["mdd_recovered"] is True
    assert metrics["mdd_recovery_days"] == 7
    assert metrics["max_underwater_days"] == 4
    assert metrics["observation_days"] == 4
    assert metrics["sharpe_ratio"] > 0


def test_calculate_performance_metrics_marks_unrecovered_drawdown():
    equity_curve = [
        {"timestamp": "2025-01-02 16:00:00", "total": 10000.0},
        {"timestamp": "2025-01-03 16:00:00", "total": 9000.0},
        {"timestamp": "2025-01-06 16:00:00", "total": 9200.0},
    ]

    metrics = calculate_performance_metrics(equity_curve, initial_value=10000.0)

    assert metrics["mdd_recovered"] is False
    assert metrics["mdd_recovery_days"] is None
    assert metrics["max_underwater_days"] == 3


def test_strategy_assessment_excludes_proxy_and_small_samples():
    report = {
        "total_return_rate": 12.0,
        "qqq_bench_return_rate": 5.0,
        "total_trades": 20,
        "profit_factor": 1.8,
        "mdd": -8.0,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.6,
        "calmar_ratio": 1.1,
        "observation_days": 180,
    }

    direct = assess_strategy_report("ema_only", report, minimum_trades=15)
    proxy = assess_strategy_report("pdufa_calendar", report, minimum_trades=15)
    small_sample = assess_strategy_report(
        "ema_only",
        {**report, "total_trades": 4},
        minimum_trades=15,
    )

    assert direct["selection_eligible"] is True
    assert direct["confidence_grade"] == "B"
    assert proxy["selection_eligible"] is False
    assert proxy["confidence_grade"] == "D"
    assert proxy["selection_score"] < direct["selection_score"]
    assert small_sample["selection_eligible"] is False
    assert "최소 기준 15회" in small_sample["selection_exclusion_reasons"][0]
