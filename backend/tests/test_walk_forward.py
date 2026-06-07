import asyncio
from datetime import date

import pytest

from app.bot.walk_forward import (
    WalkForwardConfig,
    build_walk_forward_windows,
    run_walk_forward_evaluation,
)


def _report(
    total_return: float,
    sharpe: float,
    total_trades: int = 20,
) -> dict:
    return {
        "total_return_rate": total_return,
        "qqq_bench_return_rate": 2.0,
        "total_trades": total_trades,
        "profit_factor": 1.5,
        "mdd": -6.0,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sharpe + 0.3,
        "calmar_ratio": 1.2,
        "observation_days": 45,
    }


def test_build_walk_forward_windows_rejects_invalid_periods():
    with pytest.raises(ValueError, match="1일 이상"):
        build_walk_forward_windows(
            date(2025, 1, 1),
            date(2025, 6, 1),
            WalkForwardConfig(train_days=0),
        )


def test_walk_forward_selects_on_training_and_scores_out_of_sample():
    calls = []

    async def runner(strategy_type: str, start_date: date, end_date: date) -> dict:
        calls.append((strategy_type, start_date, end_date))
        if strategy_type == "ema_only":
            return _report(total_return=12.0, sharpe=1.4)
        if strategy_type == "rsi2_connors":
            return _report(total_return=4.0, sharpe=0.4)
        return _report(total_return=30.0, sharpe=2.0)

    result = asyncio.run(
        run_walk_forward_evaluation(
            strategy_types=["ema_only", "rsi2_connors", "pdufa_calendar"],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 5, 31),
            runner=runner,
            config=WalkForwardConfig(
                train_days=60,
                test_days=30,
                step_days=30,
                select_count=1,
                minimum_trades=15,
            ),
        )
    )

    assert result["window_count"] == 3
    assert all(
        window["selected_strategies"] == ["ema_only"]
        for window in result["windows"]
    )
    assert result["leaderboard"][0]["strategy_type"] == "ema_only"
    assert result["leaderboard"][0]["selection_rate"] == 100.0
    assert result["leaderboard"][0]["profitable_window_rate"] == 100.0

    pdufa_calls = [call for call in calls if call[0] == "pdufa_calendar"]
    ema_calls = [call for call in calls if call[0] == "ema_only"]
    assert len(pdufa_calls) == result["window_count"]
    assert len(ema_calls) == result["window_count"] * 2
