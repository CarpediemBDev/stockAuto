# Validation Protocol

Use this reference before reporting implementation completion.

## Validation Order

1. Run the narrowest check for the files changed.
2. Run relevant unit or integration tests.
3. Run static analysis or type checks.
4. Run build checks for deployable artifacts when applicable.
5. Run the project harness if one exists.
6. Record failures, skips, warnings, and residual risk in the task board.

## Harness Design

A project harness should:

- Avoid live production side effects.
- Fail closed for missing critical records or skipped safety checks.
- Include syntax, type, lint, unit, integration, contract, and domain-invariant checks appropriate to the project.
- Clearly report when infrastructure checks are skipped because a service is unavailable.

## Reporting

Report checks by exact command. Distinguish:

- Passed.
- Failed.
- Not run.
- Skipped by test design.
- Unverified because a dependency was unavailable.

Do not claim a command passed if it was not run.

## Encoding

When a project uses non-ASCII docs or source text, ensure files are saved in the project's expected encoding and normalization form. For Korean text, NFC is a safe default.
