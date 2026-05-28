# Load Policy

Keep the default layer small. The entry skill should route work; it should not preload every BetterGPT sub-skill.

## Default Layer

- `BetterLanguage`

For implementation or configuration work, also apply the entry-level execution discipline in `BetterGPT`: verify local facts, state important assumptions, keep edits small, and run narrow validation. This is not a separate sub-skill.

## On-Demand Layers

Load these only when the current task needs them:

- `BetterFrontend`: visible UI, product polish, frontend presentation review
- `BetterVibe`: frontend/backend boundaries, coupling, layering, responsibility splits
- `BetterTrellis`: Trellis init, workflow, spec/task handling, hooks, Codex integration
- `BetterSubagents`: actual subagent dispatch, waiting, steering, cleanup, fallback takeover

## Control Rules

- Put always-on behavior in the entry skill or higher-level instructions, not in a sub-skill that might not trigger.
- Keep domain detail in the relevant sub-skill or reference file.
- Make `description` narrow enough to trigger reliably without pulling unrelated work into context.
- Decide whether a project should enter Trellis at the entry layer; let `BetterTrellis` handle the workflow after entry.
- Decide whether subagents will actually be used before loading `BetterSubagents`.

If `BetterGPT` must always be active, wire it through AGENTS or another higher-level entry point. A folder on disk is only discoverable; it is not a guarantee of activation.
