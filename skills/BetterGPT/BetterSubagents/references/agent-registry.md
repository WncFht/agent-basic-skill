# Agent Registry

Only use `agent_type` values that the current `spawn_agent` tool exposes. Old capability labels are task intents, not callable agent names.

## Current Callable Types

- `default`: lightweight read-only evidence gathering or summary
- `explorer`: read-only codebase, config, path, and execution-flow investigation
- `docs_researcher`: read-only official documentation verification, especially OpenAI / Codex behavior
- `reviewer`: read-only correctness, regression, security, and missing-test review
- `worker`: implementation after the main agent has scoped files, boundaries, and success criteria

## Old Label Mapping

- `code-mapper` -> `explorer`
- `search-specialist` -> `explorer`, or `default` for light non-code prefiltering
- `frontend-developer` -> `worker` with `BetterFrontend`
- `refactoring-specialist` -> `worker` with `BetterVibe`
- `browser-debugger` -> main agent handles browser reproduction; split read-only code/log evidence to `explorer`

## Framework Label Mapping

Framework-provided labels are also intents, not callable names unless the current `spawn_agent` tool exposes them.

- `trellis-implement` -> `worker` with `BetterTrellis`; add `BetterFrontend` for UI work
- `trellis-check` -> `reviewer` with `BetterTrellis`
- `trellis-research` -> `explorer` for local evidence, or `docs_researcher` for official docs

## Selection Rules

- Official docs -> `docs_researcher`.
- Risk review -> `reviewer`.
- Call-chain or repo mapping -> `explorer`.
- Small evidence summary -> `default`.
- Scoped implementation -> `worker`.

Respect current runtime limits. If `agents.max_depth = 1`, only the main agent should spawn subagents; child agents should not be asked to spawn more children.

Do not let a `worker` self-review important changes; use `reviewer` or main-agent verification.
