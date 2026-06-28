# Change Impact Contract

Use this reference before changing behavior that can affect consumers, persisted state, or operational safety.

## Impact Map

Identify:

- Producer: source of the behavior or data.
- Consumers: APIs, UI, jobs, tests, scripts, docs, users, and integrations.
- Data boundary: persisted state, cache, tenant/user scope, public/private split.
- Contract: request, response, schema, auth, timing, error handling, retries.
- Verification: unit, integration, E2E, migration, static checks, manual checks.
- Docs: task board and long-lived documentation.

## Sensitive Change Categories

Treat these as contract-impacting by default:

- API routes, request fields, response fields, auth, permissions.
- Database schema, migrations, retention, default values.
- Scheduler cadence, retry, locking, idempotency, lifecycle state.
- Cache keys, cache invalidation, public/private cache boundaries.
- External services, credentials, provider modes, fallback behavior.
- Shared calculations, scoring, allocation, money movement, rounding.
- Frontend assumptions about state shape, polling, routing, and errors.
- Harness, CI, deployment, security defaults.

## Completion Rule

Do not change only the producer. Close at least one real consumer path and update tests/docs in the same work item.

## SSOT Rule

When adding or extending behavior:

1. Search for existing equivalent logic.
2. Choose or create one owner.
3. Route consumers through that owner.
4. Delete or avoid duplicate formulas, validation, request logic, and cache mutation logic.
5. Verify one real consumer path after extraction.
