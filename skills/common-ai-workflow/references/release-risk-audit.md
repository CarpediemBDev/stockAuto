# Release Risk Audit

Use this reference when the user asks to inspect process errors, calculation errors, production readiness, safety, or hidden bugs that can pass normal tests.

## Severity

- `P0`: can cause money movement errors, security failure, data loss, cross-user leakage, duplicate destructive action, or production boot in the wrong mode.
- `P1`: can break a core workflow, corrupt state, hide operational failure, or invalidate important decisions.
- `P2`: hardening, missing coverage, observability, warnings, or maintainability risk.

## Audit Categories

### Process Correctness

Check lifecycle boundaries:
- Intent created before side effect.
- Pending, partial, final, canceled, and failed states.
- Idempotency and duplicate prevention.
- Lock acquisition and release.
- Retry and recovery behavior.
- Mode or provider capability checks before persistence or execution.

### Calculation Correctness

For formulas:
- Require explicit input numbers and expected outputs.
- Include zero, empty, negative, stale, partial, and rounding cases where relevant.
- Avoid duplicated formulas across routes, jobs, UI, and tests.
- Do not round intermediate values more aggressively than the domain allows.

### Contract Drift

Compare:
- Backend response shape.
- Frontend API wrappers and types.
- Cached or persisted legacy payloads.
- Docs and tests.

### Operations and Security

Check:
- Production environment defaults.
- Required secrets and URLs.
- Auth and cookie safety.
- External service failure modes.
- CI/harness coverage for deployable artifacts.

## Fix Pattern

When a repeatable risk is found:

1. Add or update a deterministic test or script.
2. Wire it into the project harness.
3. Document the invariant in the task board and long-lived docs if it changes project behavior.
