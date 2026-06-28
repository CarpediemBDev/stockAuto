# Task Board Protocol

Use this reference when a project needs durable AI handoff and approval tracking.

## Minimum Fields

Each implementation task should record:

- Status.
- Task description.
- Change classification.
- Producer.
- Consumers.
- Data boundary.
- API or external contract impact.
- Docs impact.
- Regression tests.
- Residual risk.
- Handoff.

## Status Model

Recommended states:

- `[ ]`: waiting or registered.
- `[/]`: in progress.
- `[R]`: implemented and verified, awaiting user approval.
- `[x]`: user-approved complete.
- `[-]`: canceled, duplicate, or superseded.

Do not mark `[x]` without explicit user approval.

## Daily File Convention

For projects that do not already have a convention, prefer:

```text
docs/tasks/YYYY-MM-DD.md
```

Use the user's or runtime's local project date. If the project already has another tracker, follow that tracker and record the mapping in `AGENTS.md`.

## Before Editing

Register the task before source edits when the user has approved implementation. If the user asked only for analysis, do not register implementation work unless the project explicitly tracks analysis tasks too.

## Handoff Quality

The next agent should know:

- What was attempted.
- What changed.
- What passed.
- What failed or remained unverified.
- Where to start next.
