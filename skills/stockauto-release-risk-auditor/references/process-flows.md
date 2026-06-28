# StockAuto Process Flow Audit

Use this reference when auditing process correctness, scheduler behavior, order lifecycle, broker boundaries, or multi-user isolation.

## Critical Workflows

### Trading Mode Change

Invariant:
- `SIMULATED`, `MOCK`, and `REAL` are explicit modes.
- Unsupported broker/mode pairs must fail before saving settings.
- Mode changes must be blocked while unresolved orders exist.
- `REAL` must require verified credentials for the same broker and same trade mode.

Inspect:
- `backend/app/admin/router.py`
- `backend/app/bot/broker_factory.py`
- `backend/tests/test_admin_settings_safety.py`
- `backend/tests/test_trading_catalog.py`

### Order Lifecycle

Invariant:
- Every broker order has a recoverable intent or persisted broker order record.
- Pending and partial fills do not create duplicate holdings.
- Mode changes during unresolved orders are detected and handled.
- Reconciliation is idempotent.

Inspect:
- `backend/app/bot/scheduler.py`
- `backend/app/bot/order_reconciler.py`
- `backend/app/bot/order_discovery.py`
- `backend/app/core/locks.py`
- `backend/tests/test_trading_flow_scenarios.py`
- `backend/tests/test_order_reconciler.py`
- `backend/tests/test_partial_fill_edge_cases.py`

### Redis Lock Boundary

Invariant:
- Production duplicate-order protection must not silently degrade to no lock.
- Redis connectivity and timeout behavior must be explicitly verified.
- If Redis is unavailable, order execution should fail closed where money movement is possible.

Inspect:
- `backend/app/core/redis_client.py`
- `backend/app/core/locks.py`
- `backend/tests/test_redis_integration.py`
- CI workflow service definitions

### Scanner and Public Cache Boundary

Invariant:
- Public market caches may be shared by all authenticated users.
- User watchlists, holdings, settings, credentials, and trade logs must stay user-scoped.
- Public scanner refreshes must not perform unexpected writes to personal or operational tables.

Inspect:
- `backend/app/scanner/router.py`
- `backend/app/scanner/swing_prediction_cache.py`
- `backend/app/scanner/after_hours_scanner.py`
- `backend/tests/test_scanner_multitenancy.py`
- `backend/tests/test_scanner_tenant_isolation.py`

## Red Flags

- Background thread creates DB sessions without clear close/rollback behavior.
- A route accepts any authenticated user for a global heavy operation without cooldown.
- Tests assert only status code, not persisted state transitions.
- A process uses global mutable state without lock or tenant key.
- A failure path logs and continues when the safe behavior should be blocking.
