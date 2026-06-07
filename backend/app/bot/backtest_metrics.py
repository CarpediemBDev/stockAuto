from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.strategies.strategy_catalog import (
    StrategyDataBasis,
    get_strategy_data_profile,
)


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PerformanceMetrics:
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    mdd_recovery_days: int | None
    mdd_recovered: bool
    max_underwater_days: int
    observation_days: int


def _safe_ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) < 1e-12:
        return 0.0
    return numerator / denominator


def _prepare_daily_equity(equity_curve: Iterable[dict[str, Any]]) -> pd.Series:
    frame = pd.DataFrame(equity_curve)
    if frame.empty or "timestamp" not in frame or "total" not in frame:
        return pd.Series(dtype=float)

    frame = frame.loc[:, ["timestamp", "total"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["total"] = pd.to_numeric(frame["total"], errors="coerce")
    frame = frame.dropna().sort_values("timestamp")
    if frame.empty:
        return pd.Series(dtype=float)

    frame["date"] = frame["timestamp"].dt.normalize()
    return frame.groupby("date", sort=True)["total"].last()


def _calculate_drawdown_recovery(equity: pd.Series) -> tuple[int | None, bool, int]:
    if equity.empty:
        return None, False, 0

    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    trough_time = drawdown.idxmin()
    peak_value = running_peak.loc[trough_time]

    prior_equity = equity.loc[:trough_time]
    peak_candidates = prior_equity[prior_equity >= peak_value - 1e-9]
    peak_time = peak_candidates.index[-1]

    recovery_candidates = equity.loc[trough_time:]
    recovery_candidates = recovery_candidates[recovery_candidates >= peak_value - 1e-9]
    if recovery_candidates.empty:
        mdd_recovery_days = None
        mdd_recovered = False
    else:
        recovery_time = recovery_candidates.index[0]
        mdd_recovery_days = int((recovery_time - peak_time).days)
        mdd_recovered = True

    max_underwater_days = 0
    underwater_start = None
    for timestamp, value in equity.items():
        peak = running_peak.loc[timestamp]
        if value < peak - 1e-9:
            if underwater_start is None:
                underwater_start = timestamp
        elif underwater_start is not None:
            max_underwater_days = max(
                max_underwater_days,
                int((timestamp - underwater_start).days),
            )
            underwater_start = None

    if underwater_start is not None:
        max_underwater_days = max(
            max_underwater_days,
            int((equity.index[-1] - underwater_start).days),
        )

    return mdd_recovery_days, mdd_recovered, max_underwater_days


def calculate_performance_metrics(
    equity_curve: Iterable[dict[str, Any]],
    initial_value: float | None = None,
) -> dict[str, Any]:
    daily_equity = _prepare_daily_equity(equity_curve)
    if daily_equity.empty:
        return asdict(
            PerformanceMetrics(
                annualized_return=0.0,
                annualized_volatility=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                max_drawdown=0.0,
                mdd_recovery_days=None,
                mdd_recovered=False,
                max_underwater_days=0,
                observation_days=0,
            )
        )

    start_value = float(initial_value or daily_equity.iloc[0])
    end_value = float(daily_equity.iloc[-1])
    returns = daily_equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    elapsed_days = max(1, int((daily_equity.index[-1] - daily_equity.index[0]).days))

    if start_value > 0 and end_value > 0:
        annualized_return = (end_value / start_value) ** (365.25 / elapsed_days) - 1.0
    else:
        annualized_return = 0.0

    if len(returns) >= 2:
        return_std = float(returns.std(ddof=1))
        annualized_volatility = return_std * sqrt(TRADING_DAYS_PER_YEAR)
        sharpe_ratio = _safe_ratio(
            float(returns.mean()) * sqrt(TRADING_DAYS_PER_YEAR),
            return_std,
        )
        downside_returns = returns[returns < 0]
        if len(downside_returns) >= 2:
            sortino_ratio = _safe_ratio(
                float(returns.mean()) * sqrt(TRADING_DAYS_PER_YEAR),
                float(downside_returns.std(ddof=1)),
            )
        else:
            sortino_ratio = 0.0
    else:
        annualized_volatility = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

    drawdown = daily_equity / daily_equity.cummax() - 1.0
    max_drawdown = float(drawdown.min()) * 100.0
    calmar_ratio = _safe_ratio(annualized_return, abs(max_drawdown) / 100.0)
    recovery_days, recovered, max_underwater_days = _calculate_drawdown_recovery(
        daily_equity
    )

    metrics = PerformanceMetrics(
        annualized_return=round(annualized_return * 100.0, 4),
        annualized_volatility=round(annualized_volatility * 100.0, 4),
        sharpe_ratio=round(sharpe_ratio, 4),
        sortino_ratio=round(sortino_ratio, 4),
        calmar_ratio=round(calmar_ratio, 4),
        max_drawdown=round(max_drawdown, 4),
        mdd_recovery_days=recovery_days,
        mdd_recovered=recovered,
        max_underwater_days=max_underwater_days,
        observation_days=len(daily_equity),
    )
    return asdict(metrics)


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.0
    clipped = min(max(value, minimum), maximum)
    return (clipped - minimum) / (maximum - minimum)


def assess_strategy_report(
    strategy_type: str,
    report: dict[str, Any],
    minimum_trades: int = 15,
) -> dict[str, Any]:
    profile = get_strategy_data_profile(strategy_type)
    total_trades = int(report.get("total_trades", 0))
    sample_score = min(total_trades / max(minimum_trades, 1), 1.0)

    total_return = float(report.get("total_return_rate", 0.0))
    benchmark_return = float(report.get("qqq_bench_return_rate", 0.0))
    sharpe = float(report.get("sharpe_ratio", 0.0))
    sortino = float(report.get("sortino_ratio", 0.0))
    calmar = float(report.get("calmar_ratio", 0.0))
    profit_factor = min(float(report.get("profit_factor", 0.0)), 5.0)
    max_drawdown = abs(float(report.get("mdd", report.get("max_drawdown", 0.0))))

    score = (
        20.0 * _normalize(total_return, -20.0, 40.0)
        + 20.0 * _normalize(sharpe, -1.0, 2.0)
        + 15.0 * _normalize(sortino, -1.0, 3.0)
        + 15.0 * _normalize(calmar, -1.0, 3.0)
        + 10.0 * _normalize(profit_factor, 0.0, 3.0)
        + 10.0 * (1.0 - _normalize(max_drawdown, 0.0, 40.0))
        + 10.0 * _normalize(total_return - benchmark_return, -20.0, 20.0)
    )

    basis_multiplier = {
        StrategyDataBasis.MARKET_DATA: 1.0,
        StrategyDataBasis.OHLCV_PROXY: 0.6,
        StrategyDataBasis.SYNTHETIC: 0.25,
    }[profile.basis]
    selection_score = score * basis_multiplier * (0.5 + 0.5 * sample_score)
    eligible = profile.selection_eligible and total_trades >= minimum_trades

    observation_days = int(report.get("observation_days", 0))
    if eligible and total_trades >= 30 and observation_days >= 120:
        confidence_grade = "A"
    elif eligible:
        confidence_grade = "B"
    elif profile.basis == StrategyDataBasis.MARKET_DATA:
        confidence_grade = "C"
    else:
        confidence_grade = "D"

    exclusion_reasons = []
    if not profile.selection_eligible:
        exclusion_reasons.append(profile.reason)
    if total_trades < minimum_trades:
        exclusion_reasons.append(
            f"청산 거래 {total_trades}회로 최소 기준 {minimum_trades}회에 미달합니다."
        )

    return {
        "selection_score": round(selection_score, 2),
        "selection_eligible": eligible,
        "confidence_grade": confidence_grade,
        "data_basis": profile.basis.value,
        "data_quality_reason": profile.reason,
        "selection_exclusion_reasons": exclusion_reasons,
        "minimum_required_trades": minimum_trades,
    }
