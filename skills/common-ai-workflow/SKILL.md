---
name: common-ai-workflow
description: Reusable AI work governance for software projects. Use when creating or updating project AGENTS.md files, splitting common vs project-specific directives, defining task-board workflows, change-impact records, validation harness expectations, release-risk audits, or handoff rules for Codex/AI agents across multiple repositories.
---

# Common AI Workflow

## Overview

Use this skill to establish project-agnostic AI engineering rules that can be reused across repositories. Keep this layer focused on how an AI agent works; keep repository-specific architecture, commands, domain invariants, and harness scripts in the project's own `AGENTS.md`, docs, and scripts.

## Layering Model

Apply rules in this order:

1. System/developer instructions from the active Codex runtime.
2. This common workflow skill for reusable agent behavior.
3. Project-level `AGENTS.md` or equivalent for repository-specific rules.
4. Project task board, issue tracker, domain docs, source code, and tests.

When layers conflict, prefer the narrower and more recent authority unless it violates a higher-level instruction.

## Start Sequence

Before implementation work:

1. Read the project's top-level agent directive such as `AGENTS.md`.
2. Read the current task board or latest handoff note.
3. Inspect the worktree with a non-mutating status command when the project allows it.
4. Decide whether the user asked for analysis only or implementation.
5. For implementation, pre-register the task according to the project task-board convention.
6. Build an impact map before touching code.
7. Search for existing equivalent logic before adding new behavior.

For details, read:
- `references/project-layering.md` when creating or splitting common and project-specific directives.
- `references/task-board-protocol.md` when defining or using daily task tracking.
- `references/change-impact-contract.md` before changing contracts, data flow, APIs, schemas, schedulers, auth, caches, external integrations, or shared business logic.
- `references/validation-protocol.md` before final reporting.
- `references/release-risk-audit.md` when the request involves process correctness, calculations, production readiness, safety, or harness design.

## Core Rules

- Do not speculate about source APIs, schemas, commands, or test behavior. Read the actual files first.
- Do not modify code for analysis-only questions.
- Do not overwrite or revert unrelated user changes.
- Keep common rules project-agnostic. Move domain names, exact paths, package managers, deployment targets, and business invariants into the project layer.
- Treat tests and harnesses as evidence, not decoration. If a check cannot run, report it as unverified with the reason.
- For repeated mistakes, convert the invariant into a deterministic test, script, or harness check in the project layer.

## Output Expectations

When finishing work, report:

- What changed.
- Which files or skill folders matter.
- Which validations passed or could not run.
- Residual risks and the next starting point.

Do not mark a task approved or done unless the user explicitly approves under the project workflow.
