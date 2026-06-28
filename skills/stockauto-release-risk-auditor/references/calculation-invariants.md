# StockAuto Calculation Invariants

Use this reference when auditing calculations, scoring, account values, fills, fees, FX, or backtests.

## Trading and Account Math

### Average Price

For partial fills:

```text
new_avg = (old_qty * old_avg + fill_qty * fill_price) / (old_qty + fill_qty)
```

Invariant:
- Never divide by zero.
- Do not round intermediate average price more aggressively than broker/account precision.
- Partial sell must reduce quantity without changing average buy price unless the domain explicitly records realized PnL separately.

### Realized PnL

```text
gross = sell_qty * sell_price - sell_qty * avg_buy_price
fees = buy_or_allocated_fee + sell_fee + sec_fee_when_applicable
realized_pnl = gross - fees
return_rate_pct = realized_pnl / cost_basis * 100
```

Invariant:
- Cost basis must be positive.
- Fees are subtracted once.
- SEC fee applies to sell side only.

### FX

Invariant:
- Account display conversions must state whether source is KRW or USD.
- Real broker balances should not reuse simulated initial FX assumptions.
- Cached FX must have stale/failure behavior visible to callers.

Inspect:
- `backend/app/bot/fx_cache.py`
- `backend/tests/test_fx_cache.py`
- `backend/app/trades/router_account.py`

## Scanner Math

### Percent Change

```text
pct = (new / old - 1) * 100
```

Invariant:
- If old value is zero or negative, return safe default or reject the candidate.
- NaN and infinite values must not enter API responses.
- Scores exposed to UI stay within 0..100.

### After-Hours Scoring

Invariant:
- Regular session and after-hours session must be separated by market calendar close time.
- Timezone must be America/New_York for US market session boundaries.
- Public scanner scoring should not trigger unrelated DB writes or external translation calls.

Inspect:
- `backend/app/scanner/after_hours_scanner.py`
- `backend/app/bot/us_market_calendar.py`
- `backend/tests/test_scanner_router.py`

### Backtest Metrics

Invariant:
- No lookahead: strategy cannot use future candles for current signal.
- Cash, holdings, and fees reconcile at the end of each trade.
- Drawdown is based on equity curve peak-to-trough, not trade-only PnL.

Inspect:
- `backend/app/bot/backtest_engine.py`
- `backend/app/bot/backtest_metrics.py`
- `backend/tests/test_backtest_metrics.py`
- `backend/tests/test_backtest_data_range.py`

## Required Golden Tests

For every changed formula, add or confirm tests with:
- explicit input numbers
- exact expected output
- zero/empty edge case
- at least one production-like non-round value

Do not accept “looks reasonable” as calculation verification.
