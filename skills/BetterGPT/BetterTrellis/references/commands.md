# Commands

Do not dump this table unless the user asks for a command reference. Pick the command that matches the current stage.

## Install / Init

```bash
npm install -g @mindfoldhq/trellis@latest
trellis --version
trellis init --codex -u <name>
```

Other init targets exist (`trellis init`, `--cursor`, `--claude`), but prefer `--codex` for Codex integration.

## Codex Workflow Entries

These are workflow entry names, not shell commands:

```text
$start
continue
$finish-work
record-session
```

Prefer stage-based wording: choose the entry that matches context restore, workflow advance, checking, or finish/journal work. Do not present these as a required sequence for every small edit.

## Update

```bash
trellis update
trellis update --dry-run
trellis update --force
trellis update --migrate
```

Use `--dry-run` before risky template updates. `--force` overwrites managed files; do not use it casually.

## Tasks

```bash
python .trellis/scripts/task.py create "task-name" --assignee <name>
python .trellis/scripts/task.py start <task-id>
python .trellis/scripts/task.py list
python .trellis/scripts/task.py finish
python .trellis/scripts/task.py archive <task-id>
```

## Preference

- missing project setup -> `trellis init --codex -u <name>`
- current Codex session needs context -> `$start`
- current Trellis task needs the next workflow step -> `continue`
- work is done and needs journaling -> `$finish-work` / `record-session`
- stale managed files -> `trellis update --dry-run`, then update if safe
- work needs explicit task state -> `task.py`
