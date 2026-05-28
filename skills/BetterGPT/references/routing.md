# Routing

`BetterGPT` is the entry router. It applies the default language layer, adds execution discipline for real work, then loads only the sub-skill needed by the task.

## Route Order

1. Start with `BetterLanguage`.
2. If the task changes code, config, workflow files, tests, or local state, apply entry execution discipline.
3. If the project has `.trellis/` and the task is implementation work, decide whether Trellis workflow is active.
4. If the main agent will actually call `spawn_agent`, `wait_agent`, `send_message`, `followup_task`, or `close_agent`, load `BetterSubagents`.
5. Add `BetterFrontend` for visible UI work.
6. Add `BetterVibe` for boundary, layering, or coupling work.
7. Add `BetterTrellis` for Trellis init, task/spec workflow, hooks, or Codex integration.

Multiple sub-skills may apply, but do not load one only because another loaded.

## Sub-Skill Roles

- `BetterLanguage`: English-first technical work, concise Chinese delivery, preserved technical tokens
- `BetterFrontend`: production-ready UI, no demo leakage, no developer commentary in visible surfaces
- `BetterVibe`: presentation/domain/persistence boundaries, cross-layer contracts, low-risk structure changes
- `BetterTrellis`: project workflow entry, spec/task state, hooks, Trellis command mapping
- `BetterSubagents`: callable agent mapping, scoped delegation, waits, steering, cleanup, fallback takeover

## Trellis Gate

Enter Trellis directly when the user mentions `Trellis`, `start`, `task.py`, `record-session`, `/trellis:*`, or repository instructions require Trellis workflow.

If `.trellis/` exists but neither the user nor repo instructions specify the workflow, ask once before using Trellis for implementation work. Pure analysis, review, or architecture discussion does not enter Trellis just because `.trellis/` exists.

## Subagent Gate

Load `BetterSubagents` only when subagents will be used or the user asks about subagent orchestration. Do not load it for ordinary local exploration.

## Boundaries

- The entry skill may route and enforce broad execution discipline.
- It should not duplicate the detailed rules of child skills.
- Child skills should not redefine entry routing.
- If inspection or validation finds a clear in-scope, low-risk, verifiable fix, implement it in the same turn instead of parking it as a next-round suggestion.
- New child skills must be added here only if they represent a distinct recurring job.
