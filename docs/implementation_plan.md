# [Implementation Plan] Phase 24: System Resilience & High-Performance Optimization

This plan details the implementation of the remaining three core pillars of **Phase 24 (System Resilience & High-Performance Optimization)**. We will transform the Telegram communication bridge into a purely non-blocking async architecture, implement a self-healing auto-recovery mechanism inside the background trading scheduler, and build an intelligent rate-limiter defense in the data provider.

## User Review Required

> [!IMPORTANT]
> **No Thread Blockages:**
> By changing the Telegram sender to a purely non-blocking `asyncio` task architecture, we eliminate all `ThreadPoolExecutor` context switches.
>
> **Self-Healing Scheduler:**
> If a network outage occurs or the KIS servers go down for maintenance, the scheduler will not crash. It will log a warning, pause trading operations for that specific user, and automatically resume once the connection is restored.
>
> **Rate Limit Shields:**
> The `DataProvider` will introduce cache windows (10-second hot cache) for single stock requests, preventing duplicate `yf.download` network triggers.

---

## Proposed Changes

### [Component 1] Telegram Async Refactoring

#### ⚙️ [MODIFY] [telegram.py](file:///d:/dev/workspace/stockAuto/backend/app/core/telegram.py)
* **Deprecate Sync Sender:** Convert `send_message_sync` to a purely asynchronous `send_message_async` using `httpx.AsyncClient` instead of the blocking `requests` library.
* **Remove ThreadPoolExecutor:** Replace the old `ThreadPoolExecutor` and background thread workers with standard, lightweight `asyncio.create_task()` executions.

---

### [Component 2] Scheduler Auto-Recovery & Resilience

#### ⚙️ [MODIFY] [scheduler.py](file:///d:/dev/workspace/stockAuto/backend/app/bot/scheduler.py)
* **Wrap User Loops:** Wrap each user's trading execution loop in a strict `try-except` block.
* **Auto-Recovery:** If a network-related API error (e.g., KIS API timeout or DNS name resolution failure) is caught:
  1. Log a warning with the user context.
  2. Send a Telegram warning alert to the user notifying them of the connection disruption.
  3. Keep the scheduler running smoothly, bypass the current cycle, and try again in the next 1-minute cycle.
* **State Coherence:** Ensure that database sessions are always properly rolled back and closed in a `finally` block during any scheduler crash, preventing connection pool leaks.

---

### [Component 3] Data Provider Caching & Rate-Limit Shield

#### ⚙️ [MODIFY] [data_provider.py](file:///d:/dev/workspace/stockAuto/backend/app/scanner/data_provider.py)
* **Hot Cache:** Introduce a dictionary-based `HotCache` for recent stock data requests.
* **Rate-Limit Guard:** If a ticker's OHLCV data was successfully fetched within the last 10 seconds, return the cached result instead of hitting the `yfinance` network server. This reduces duplicate calls during rapid page reloads or simultaneous scheduler/watchlist checks.

---

## Verification Plan

### Automated Verification
1. **Compilation Check:** Run `python -m py_compile backend/app/core/telegram.py backend/app/bot/scheduler.py backend/app/scanner/data_provider.py` to verify syntax.
2. **Resilience Emulation Test:**
   * Run the server locally.
   * Disconnect or block outbound internet connections (or point the API URL to a dummy domain).
   * Verify that the scheduler outputs a descriptive connection warning and stays running, rather than crashing the background daemon.

### Manual Verification
* Start the Next.js UI, navigate around the dashboard, trigger a manual watchlist check, and verify that the logs show no duplicate `yfinance` network downloads for the same stock ticker within a 10-second window.
