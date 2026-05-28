# Codex Workflow

Use this when a Codex session should follow Trellis project workflow.

## Integration Baseline

`trellis init --codex -u <name>` may create or update:

- `AGENTS.md`
- `.trellis/`
- `.agents/skills/`
- `.codex/config.toml`
- `.codex/agents/`
- `.codex/skills/`
- `.codex/hooks/session-start.py`
- `.codex/hooks.json`

Treat these as integration files, not proof that hook runtime behavior is active on every platform.

## Activation

Enter Trellis workflow when:

- the user mentions `Trellis`, `$start`, `start`, `continue`, `task.py`, `record-session`, or another platform-native Trellis entry
- repo or global instructions require Trellis workflow
- the user confirms Trellis use after `.trellis/` is detected for implementation work

Do not enter Trellis only because `.trellis/` exists for pure analysis, review, or architecture discussion.

## Stage Rhythm

- Natural-language task request -> describe the task directly, then let Trellis route by stage
- Session/context restore -> `$start` / `start`
- Advance current workflow step -> `continue`
- Before implementation -> `before-dev`
- During work -> follow current task and relevant specs
- Quality check -> `check`
- Cross-layer work -> `check-cross-layer`
- Finish current work -> `$finish-work` / `finish-work`
- Persist session notes -> `record-session`

When the user asks which command to use, answer by current stage first, then name the command.

## Boundary

Trellis is a workflow and project-memory layer. Do not reduce it to a command list, and do not claim hooks or session injection are active unless runtime evidence confirms them.
