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


def test_strategy_assessment_excludes_unprofitable_high_frequency():
    """거래 표본·데이터 출처가 정상이라도 손실/저효율 전략은 자동선정에서 제외한다.

    트리아지에서 selection_eligible 게이트가 수익성을 안 봐서 -85% 전략도
    통과하던 결함을 회귀로 고정한다.
    """
    losing = {
        "total_return_rate": -85.0,
        "qqq_bench_return_rate": 29.0,
        "total_trades": 4033,
        "profit_factor": 0.31,
        "mdd": -85.0,
        "sharpe_ratio": -1.5,
        "sortino_ratio": -1.8,
        "calmar_ratio": -0.9,
        "observation_days": 250,
    }
    assessment = assess_strategy_report("supertrend", losing, minimum_trades=15)

    assert assessment["selection_eligible"] is False
    assert assessment["is_profitable"] is False
    assert assessment["beats_benchmark"] is False
    assert any(
        "수익성 미달" in reason
        for reason in assessment["selection_exclusion_reasons"]
    )

    # PF는 1을 넘지만 순수익이 음(手수료 잠식)인 경계도 제외되어야 한다.
    flat_but_costly = {**losing, "total_return_rate": -0.5, "profit_factor": 1.05}
    edge = assess_strategy_report("supertrend", flat_but_costly, minimum_trades=15)
    assert edge["selection_eligible"] is False
    assert edge["is_profitable"] is False


def test_strategy_assessment_flags_benchmark_underperformance():
    """수익은 나지만 벤치마크(QQQ)를 못 이기면 beats_benchmark=False로 표기.

    다만 수익성 게이트는 통과하므로 selection_eligible은 유지된다
    (강세장에서 선정기가 굶지 않도록 벤치마크초과는 하드 배제 아님)."""
    profitable_laggard = {
        "total_return_rate": 12.0,
        "qqq_bench_return_rate": 29.0,
        "total_trades": 100,
        "profit_factor": 1.5,
        "mdd": -6.0,
        "sharpe_ratio": 1.1,
        "sortino_ratio": 1.4,
        "calmar_ratio": 1.0,
        "observation_days": 250,
    }
    assessment = assess_strategy_report("ema_only", profitable_laggard, minimum_trades=15)
    assert assessment["is_profitable"] is True
    assert assessment["beats_benchmark"] is False
    assert assessment["selection_eligible"] is True
