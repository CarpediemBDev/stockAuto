# StockAuto Critical Files and Consumer Map

Use this reference to build an impact map before changing sensitive files.

## Backend Core

- `backend/app/core/models.py`: DB schema source. Consumers: routers, scheduler, tests, migrations.
- `backend/alembic/versions/*`: schema migration history. Consumers: startup migrator, existing DBs.
- `backend/app/core/database.py`: DB connection and prod database safety.
- `backend/app/core/config.py`: runtime profile, Redis, cookies, trading constants.
- `backend/app/core/security.py`: JWT and auth token safety.
- `backend/app/core/response.py`: global API response wrapper.

## Trading

- `backend/app/bot/scheduler.py`: automated trading orchestration.
- `backend/app/bot/broker_factory.py`: broker/mode capability gate.
- `backend/app/bot/kis_api.py`, `kis_broker.py`: KIS live/mock integration.
- `backend/app/bot/toss_api.py`, `toss_broker.py`: Toss integration.
- `backend/app/bot/order_reconciler.py`: pending/partial/final fill handling.
- `backend/app/bot/order_discovery.py`: recovery of unresolved broker orders.
- `backend/app/core/locks.py`: duplicate order boundary.

## Scanner

- `backend/app/scanner/router.py`: scanner API surface.
- `backend/app/scanner/data_provider.py`: yfinance shared external data boundary.
- `backend/app/scanner/swing_prediction_cache.py`: public swing snapshot contract.
- `backend/app/scanner/after_hours_scanner.py`: public after-hours scanner contract.
- `frontend/components/OverseasScanner.tsx`: 15m scanner consumer.
- `frontend/components/SwingPredictorCard.tsx`: swing consumer.
- `frontend/components/AfterHoursScanner.tsx`: after-hours consumer.
- `frontend/lib/api.ts`: frontend response unwrapping and endpoint map.

## Admin and Auth

- `backend/app/admin/router.py`: settings, credential verification, trade mode safety.
- `frontend/app/admin/settings/page.tsx`: admin/settings consumer.
- `backend/app/auth/router.py`: login/session/me flow.
- `frontend/store/authStore.ts`, `frontend/lib/api.ts`: token refresh behavior.

## Release

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `.github/workflows/harness.yml`
- `scripts/verify_harness.py`
- `docs/tasks/YYYY-MM-DD.md`
- `docs/API_STANDARD.md`
- `docs/SCANNER_DATA_FLOW.md`
- `docs/SYSTEM_MANUAL.md`

## Impact Rule

For any file above, confirm:
- producer and every consumer
- persisted data or cache boundary
- API request/response shape
- user isolation requirement
- scheduler/background-task interaction
- relevant tests and docs
