# StockAuto Release Runtime Checklist

Use this reference for production launch, Docker, Cloud Run, env, CI, Redis, auth, cookies, and deployability reviews.

## Backend Production Profile

Invariant:
- Container startup must set `APP_ENV=prod` unless the platform explicitly overrides to a safer equivalent.
- Missing prod env must fail closed for security and database settings.

Inspect:
- `backend/Dockerfile`
- `backend/.env.prod.example`
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/app/core/database.py`
- `backend/tests/test_release_artifacts.py`
- `backend/tests/test_config_security.py`

Must verify:
- `JWT_SECRET_KEY` is not default.
- `REFRESH_COOKIE_SECURE=true` in prod.
- `DATABASE_URL` exists and is not SQLite in prod.
- `REDIS_URL` exists for order locks.
- `ALLOWED_ORIGINS` is explicit and contains no wildcard.

## Frontend Runtime Contract

Invariant:
- Browser API base should be `/api/v1` for same-origin proxy.
- Server-side rewrite target should be `BACKEND_API_ORIGIN`.
- Build-time env examples should exist for local/dev/prod.

Inspect:
- `frontend/next.config.ts`
- `frontend/lib/api.ts`
- `frontend/Dockerfile`
- `frontend/.env.local.example`
- `frontend/.env.dev.example`
- `frontend/.env.prod.example`

## CI and Harness

Invariant:
- `scripts/verify_harness.py` must remain the minimum gate, not the only evidence for deployability.
- CI should not hide Redis/Docker/prod-startup gaps.

Inspect:
- `.github/workflows/harness.yml`
- `scripts/verify_harness.py`
- `backend/tests/test_redis_integration.py`
- `frontend/playwright.config.ts`

## Commands

Minimum local verification:

```bash
backend\venv\Scripts\python.exe scripts\verify_harness.py
npm run build
```

Production-like verification when environment allows:

```bash
docker build -t stockauto-backend ./backend
docker build -t stockauto-frontend ./frontend
docker run --rm --env-file backend/.env.prod -p 8000:8000 stockauto-backend
```

If Docker or Redis is unavailable, report those checks as not executed.
