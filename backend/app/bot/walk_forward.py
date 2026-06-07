from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Awaitable, Callable, Iterable

from app.bot.backtest_metrics import assess_strategy_report


SimulationRunner = Callable[
    [str, date, date],
    dict[str, Any] | Awaitable[dict[str, Any]],
]


@dataclass(frozen=True)
class WalkForwardConfig:
    train_days: int = 180
    test_days: int = 60
    step_days: int = 60
    select_count: int = 10
    minimum_trades: int = 15


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def build_walk_forward_windows(
    start_date: date,
    end_date: date,
    config: WalkForwardConfig,
) -> list[WalkForwardWindow]:
    if config.train_days <= 0 or config.test_days <= 0 or config.step_days <= 0:
        raise ValueError("Walk-Forward 기간은 모두 1일 이상이어야 합니다.")
    if config.select_count <= 0:
        raise ValueError("선발 전략 수는 1개 이상이어야 합니다.")
    if start_date >= end_date:
        raise ValueError("시작일은 종료일보다 빨라야 합니다.")

    windows = []
    cursor = start_date
    index = 1
    while True:
        train_end = cursor + timedelta(days=config.train_days - 1)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=config.test_days - 1)
        if test_end > end_date:
            break

        windows.append(
            WalkForwardWindow(
                index=index,
                train_start=cursor,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        cursor += timedelta(days=config.step_days)
        index += 1

    return windows


async def _run_simulation(
    runner: SimulationRunner,
    strategy_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    result = runner(strategy_type, start_date, end_date)
    if inspect.isawaitable(result):
        return await result
    return result


async def run_walk_forward_evaluation(
    strategy_types: Iterable[str],
    start_date: date,
    end_date: date,
    runner: SimulationRunner,
    config: WalkForwardConfig | None = None,
) -> dict[str, Any]:
    active_config = config or WalkForwardConfig()
    strategies = list(dict.fromkeys(strategy_types))
    if not strategies:
        raise ValueError("평가할 전략이 하나 이상 필요합니다.")

    windows = build_walk_forward_windows(start_date, end_date, active_config)
    if not windows:
        raise ValueError("설정한 기간 안에서 Walk-Forward 창을 만들 수 없습니다.")

    strategy_results: dict[str, dict[str, Any]] = {
        strategy: {
            "strategy_type": strategy,
            "selected_windows": 0,
            "test_returns": [],
            "test_selection_scores": [],
            "profitable_windows": 0,
        }
        for strategy in strategies
    }
    window_results = []

    for window in windows:
        training_results = []
        for strategy in strategies:
            report = await _run_simulation(
                runner,
                strategy,
                window.train_start,
                window.train_end,
            )
            assessment = assess_strategy_report(
                strategy,
                report,
                minimum_trades=active_config.minimum_trades,
            )
            training_results.append(
                {
                    "strategy_type": strategy,
                    **report,
                    **assessment,
                }
            )

        eligible_training_results = [
            result for result in training_results if result["selection_eligible"]
        ]
        eligible_training_results.sort(
            key=lambda result: result["selection_score"],
            reverse=True,
        )
        selected = eligible_training_results[: active_config.select_count]

        test_results = []
        for training_result in selected:
            strategy = training_result["strategy_type"]
            test_report = await _run_simulation(
                runner,
                strategy,
                window.test_start,
                window.test_end,
            )
            test_assessment = assess_strategy_report(
                strategy,
                test_report,
                minimum_trades=active_config.minimum_trades,
            )
            test_result = {
                "strategy_type": strategy,
                "training_selection_score": training_result["selection_score"],
                **test_report,
                **test_assessment,
            }
            test_results.append(test_result)

            aggregate = strategy_results[strategy]
            aggregate["selected_windows"] += 1
            aggregate["test_returns"].append(
                float(test_report.get("total_return_rate", 0.0))
            )
            aggregate["test_selection_scores"].append(
                float(test_assessment["selection_score"])
            )
            if float(test_report.get("total_return_rate", 0.0)) > 0:
                aggregate["profitable_windows"] += 1

        window_results.append(
            {
                **asdict(window),
                "selected_strategies": [
                    result["strategy_type"] for result in selected
                ],
                "training_results": training_results,
                "test_results": test_results,
            }
        )

    leaderboard = []
    for aggregate in strategy_results.values():
        selected_windows = aggregate["selected_windows"]
        if selected_windows == 0:
            continue

        test_returns = aggregate.pop("test_returns")
        test_scores = aggregate.pop("test_selection_scores")
        leaderboard.append(
            {
                **aggregate,
                "selection_rate": round(
                    selected_windows / len(windows) * 100.0,
                    2,
                ),
                "profitable_window_rate": round(
                    aggregate["profitable_windows"] / selected_windows * 100.0,
                    2,
                ),
                "average_test_return": round(mean(test_returns), 4),
                "median_test_return": round(median(test_returns), 4),
                "worst_test_return": round(min(test_returns), 4),
                "average_test_selection_score": round(mean(test_scores), 2),
            }
        )

    leaderboard.sort(
        key=lambda result: (
            result["profitable_window_rate"],
            result["median_test_return"],
            result["average_test_selection_score"],
        ),
        reverse=True,
    )

    return {
        "config": asdict(active_config),
        "window_count": len(windows),
        "windows": window_results,
        "leaderboard": leaderboard,
    }
