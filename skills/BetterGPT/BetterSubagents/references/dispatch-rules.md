# Dispatch Rules

Use subagents only when delegation shortens the path or improves evidence quality.

## Dispatch When

- The subtask is independent and can run while the main agent continues.
- Several read-only investigations can run in parallel.
- The task needs a current callable type's narrow role: docs verification, repo exploration, risk review, or scoped implementation.

Keep the work in the main agent when the next step depends on the answer, the boundary is unclear, the write set may conflict, or the task is small enough to do directly.

## Callable Type Map

- Evidence summary -> `default`
- Code path, config, call-chain, repo map -> `explorer`
- Official OpenAI / Codex docs -> `docs_researcher`
- Bugs, regressions, security, missing tests -> `reviewer`
- Scoped implementation -> `worker`

Old labels map only to intent:

- `code-mapper` -> `explorer`
- `search-specialist` -> `explorer` or light `default`
- `frontend-developer` -> `worker` + `BetterFrontend`
- `refactoring-specialist` -> `worker` + `BetterVibe`
- `browser-debugger` -> main agent reproduction; read-only evidence may go to `explorer`

Framework labels also map only to intent unless currently exposed by `spawn_agent`:

- `trellis-implement` -> `worker` + `BetterTrellis`; add `BetterFrontend` for UI work
- `trellis-check` -> `reviewer` + `BetterTrellis`
- `trellis-research` -> `explorer` for local evidence, or `docs_researcher` for official docs

## Dispatch Prompt

Include only what the subagent needs:

```text
Task type:
Goal:
Boundary:
Expected output:
Verification:
Skill / tool constraints:
Exit condition:
```

For `worker`, state the files or modules it may edit. For `explorer`, request concrete file/symbol/call-site evidence. For `docs_researcher`, require official sources.

## Runtime Limits

Respect current Codex agent limits from the active tool surface and config. If `agents.max_depth = 1`, keep orchestration in the main thread and do not ask subagents to spawn follow-on agents. Keep fan-out bounded by the current concurrent-thread limit and by review capacity.

## Skill Binding

- UI implementation or visual polish -> `BetterFrontend`
- Boundary or layering refactor -> `BetterVibe`
- Trellis workflow, specs, tasks, hooks -> `BetterTrellis`

Name these bindings in the dispatch prompt when they apply.

## Waiting And Takeover

- Use `wait_agent` only when the main thread is blocked.
- If useful non-overlapping work remains, continue locally before waiting.
- On timeout, check progress once; then send a clarifying boundary or goal if needed.
- Do not send empty "hurry up" messages.
- If a child result or validation exposes a clear in-scope, low-risk, verifiable fix, the main agent implements and verifies it in the current turn.
- After repeated timeout, wrong direction, write conflict, external blocker, or conflicting results, close or stop relying on the subagent and take over in the main thread.

## Cleanup

Close a completed agent after its result is absorbed. Reuse an agent only when the next question is tightly continuous and the boundary/tooling is unchanged.
