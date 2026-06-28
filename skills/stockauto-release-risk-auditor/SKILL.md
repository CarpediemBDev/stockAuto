---
name: stockauto-release-risk-auditor
description: Audit StockAuto for production-readiness and SSOT design risks beyond syntax errors. Use when reviewing or building StockAuto features that could duplicate business logic across routers, services, hooks, components, schedulers, calculators, or tests; also use for process correctness, trading workflow safety, financial calculation accuracy, scheduler/order lifecycle risks, broker mode isolation, Redis lock behavior, API/frontend contract drift, scanner scoring errors, or release-blocking runtime and environment issues before production launch.
---

# StockAuto Release Risk Auditor

## Overview

Use this skill to audit StockAuto for failures that can pass lint and tests but still break production: workflow gaps, calculation mistakes, contract drift, isolation leaks, skipped infrastructure checks, and unsafe release configuration.

This skill is the StockAuto-specific layer on top of project-local `skills/common-ai-workflow/SKILL.md`. Use that file for reusable AI work governance, then use this skill for StockAuto domain paths, trading modes, broker boundaries, scanner contracts, and release-risk checks.

This skill is for auditing and hardening. Do not treat a green test suite as sufficient until the invariant checks below have been considered.

## Required Start Sequence

1. Read project `AGENTS.md`.
2. Read the latest `docs/tasks/YYYY-MM-DD.md`.
3. Run only `git status --short` for Git state unless the user explicitly authorizes other Git commands.
4. Identify whether the user asked for analysis only or implementation. If analysis only, do not edit files.
5. For implementation work, pre-register the task in the daily task file before editing.
6. Build an impact map before touching code: producer, consumers, data boundary, API contract, tests, docs.
7. For new or changed behavior, search for existing equivalent implementations before writing code.

## Audit Workflow

### 1. Release Runtime Audit

Read `references/release-checklist.md` when the request mentions production launch, deploy readiness, Cloud Run, Docker, env, CI, Redis, auth, or security defaults.

Run, when appropriate:

```bash
backend\venv\Scripts\python.exe skills\stockauto-release-risk-auditor\scripts\check_release_artifacts.py D:\dev\workspace\stockAuto
```

Check for:
- Backend container starts as `APP_ENV=prod`, not implicit `local`.
- Production rejects insecure JWT/cookie defaults.
- `DATABASE_URL` and `REDIS_URL` are required in prod.
- Frontend uses `/api/v1` plus `BACKEND_API_ORIGIN` rewrite.
- CI/harness does not silently skip deployable artifact validation.

### 2. Trading Process Audit

Read `references/process-flows.md` when reviewing scheduler, broker, order, holding, account, admin settings, auth, Redis locks, mode switching, or any trading workflow.

Check:
- Order lifecycle: intent -> broker request -> pending/partial/final fill -> holding/log reconciliation.
- Mode isolation: `SIMULATED`, `MOCK`, `REAL` never share mutable trading state accidentally.
- Broker capability: unsupported broker/mode combinations fail before persistence or execution.
- Redis/order locks fail closed for duplicate-order boundaries.
- User data is filtered by `user_id`; public market caches do not merge personal data.

### 3. Financial Math Audit

Read `references/calculation-invariants.md` when reviewing PnL, return rate, average price, fees, FX, account equity, scanner scores, backtests, allocation, or any numeric output.

Run, when appropriate:

```bash
backend\venv\Scripts\python.exe skills\stockauto-release-risk-auditor\scripts\check_numeric_invariants.py D:\dev\workspace\stockAuto
```

For any changed formula, require at least one golden test with explicit input numbers and expected output. Prefer edge cases: zero/negative values, partial fills, multi-currency conversion, insufficient cash, stale price, and rounding.

### 4. Contract Drift Audit

Read `references/critical-files.md` when reviewing API, frontend, DB model, migration, scanner, scheduler, or release harness changes.

Run, when appropriate:

```bash
backend\venv\Scripts\python.exe skills\stockauto-release-risk-auditor\scripts\check_contract_coverage.py D:\dev\workspace\stockAuto
```

Check:
- Backend route response shape matches frontend API/type assumptions after `SuccessResponseRoute` unwrapping.
- Cached/persisted legacy payloads are normalized before UI reads numeric fields.
- API docs and data-flow docs are updated for contract-impacting changes.
- `scripts/verify_harness.py` will fail when sensitive files change without daily impact records.

### 5. Feature SSOT Audit

Use this section when adding, extending, or refactoring a feature.

Search first:

```bash
rg "feature-name|endpoint|add|delete|toggle|calculate|mutate|fetch" backend frontend docs tests
```

Check:
- Identical validation, DB mutation, API call, cache mutation, toast/error handling, or numeric formula is not copied across files.
- Backend business mutations live in `backend/app/<domain>/services.py` or a focused domain module.
- Pure calculations live in a named calculator module, not inline in routers, schedulers, backtests, and admin flows.
- Frontend repeated actions live in a shared hook such as `frontend/hooks/use<Feature>Actions.ts`.
- API endpoint wrappers live in `frontend/lib/api.ts`; components call hooks or API wrappers instead of rebuilding request logic.
- FastAPI routers handle request parsing, dependency injection, and pure response data; they do not become the business-logic owner.
- Components render UI and call hooks; they do not independently own the same server mutation and cache invalidation flow.
- At least one real consumer path is verified after extracting the owner.

## Required Verification

For completed implementation work, run the narrowest relevant tests first, then the full harness:

```bash
backend\venv\Scripts\python.exe -m py_compile <changed-python-files>
backend\venv\Scripts\python.exe -m pytest <relevant-tests> -q
npm run lint
npx tsc --noEmit
npm run build
backend\venv\Scripts\python.exe scripts\verify_harness.py
```

If a command cannot run, report it as unverified with the exact reason. Do not phrase skipped Redis, Docker, network, broker, or production-startup checks as passed.

## Reporting Format

Lead with findings by severity:

- `P0`: can cause real-money loss, prod boot in wrong profile, auth/security failure, duplicate orders, cross-user leak.
- `P1`: can break a core page/API, corrupt persisted state, hide operational failure, or invalidate trading decisions.
- `P2`: important release hardening, missing coverage, or degraded observability.

For each finding include:
- file and line reference
- violated invariant
- production impact
- recommended fix
- exact verification to add or run

End with verification status and residual risks.
