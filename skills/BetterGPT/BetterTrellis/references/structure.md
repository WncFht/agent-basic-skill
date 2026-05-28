# Structure

Use this when explaining what Trellis added to a project.

## Layers

- `.trellis/`: project workflow, specs, tasks, workspace logs, and helper scripts
- `AGENTS.md`: Codex entry context for the project
- `.agents/skills/`: shared agent skills usable beyond Codex
- `.codex/`: Codex-specific agents, skills, hooks, and platform config

Typical `.trellis/` contents:

- `workflow.md`
- `spec/`
- `workspace/`
- `tasks/`
- `scripts/task.py`

Typical `.codex/` contents:

- `config.toml`
- `agents/`
- `skills/`
- `hooks/`

## Explanation Rule

Say:

- `.trellis/` manages project knowledge and workflow.
- `AGENTS.md` exposes the project entry context.
- `.agents/skills/` stores shared capabilities.
- `.codex/` stores Codex-specific integration: agents, skills, hooks, and related config.

Do not describe all of these as generic prompt files. Do not claim hooks, preludes, or session injection are running unless runtime evidence verifies that behavior.
