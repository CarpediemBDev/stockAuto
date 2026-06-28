# Project Layering Reference

Use this reference when creating a new project's AI directive or splitting an existing directive into reusable and project-specific layers.

## Recommended Layers

1. Common AI workflow skill:
   - Agent behavior.
   - Task registration pattern.
   - Change-impact reasoning.
   - Validation discipline.
   - Release-risk audit categories.

2. Project `AGENTS.md`:
   - Repository structure.
   - Domain architecture.
   - Exact commands.
   - Project-specific status board path.
   - Domain invariants and safety rules.
   - Harness scripts and CI expectations.

3. Long-lived project docs:
   - API contracts.
   - Data flow.
   - Schema.
   - Deployment.
   - Framework guides.

4. Daily or current task board:
   - Active work.
   - Approval state.
   - Validation results.
   - Handoff notes.

## Split Decision

Move a rule to the common layer if it is true across most software repositories:
- Read before editing.
- Ask or plan for analysis-only requests.
- Register work before implementation.
- Build an impact map.
- Verify before reporting.
- Preserve unrelated user changes.

Keep a rule in the project layer if it names:
- A domain concept.
- A framework version.
- A repository path.
- A command.
- A database, queue, broker, cache, or external service.
- A business calculation.
- A project-specific approval or issue workflow.

## New Project Bootstrap

When starting a new repository:

1. Create a concise `AGENTS.md`.
2. Reference the common workflow skill as the reusable baseline.
3. Add only project-specific architecture, commands, and verification rules.
4. Choose a task-board convention.
5. Define the minimum harness that can run locally and in CI.
6. Add domain-specific invariant checks only after the real code shape is known.
