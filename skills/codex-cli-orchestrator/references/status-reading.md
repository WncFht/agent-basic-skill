# Status Reading

When another agent needs to understand a running or finished worker, inspect files in this order:

## Single Worker

1. `summary.json`
   - Best first stop.
   - Contains derived status, status reason, pid liveness, event count, last command, last agent message, final message excerpt, exit code, and stderr tail.

2. `final.txt`
   - The worker's last agent message after completion.

3. `run-meta.txt` and `command.txt`
   - Use these when you need to confirm which settings were inherited versus explicitly overridden.

4. `events.jsonl`
   - Primary raw trace.
   - For terminal reading, prefer `python scripts/events_tui.py ...`.
   - Use `python scripts/codex_status.py events ...` when you want a plain exported timeline.

5. `stderr.log`
   - Use for wrapper-level or CLI-level failures.

## Batch

1. `batch-status.json`
   - Live aggregate view.
   - Includes each run's status plus counts of `running`, `completed`, and `failed`.

2. `runs/<job-id>/summary.json`
   - Best per-worker drill-down.

3. `batch-results.json`
   - Final aggregate after the batch exits.

4. `launcher.log`
   - Start and finish times plus worker exit codes.

5. `runs/<job-id>/launcher.stderr.log`
   - Use when the batch wrapper itself failed before the worker produced useful Codex events.

6. `batch-error.txt`
   - Present when the batch launcher itself crashed before normal completion.
   - Best first stop for manifest parsing failures, duplicate run-dir errors, and other launcher exceptions.

## Helpful Commands

Refresh a single run summary:

```bash
python scripts/codex_status.py single /abs/path/run-dir
```

Refresh a batch summary:

```bash
python scripts/codex_status.py batch /abs/path/batch-root
```

Human-readable batch summary:

```bash
python scripts/codex_status.py batch /abs/path/batch-root --format text
```

Human-readable single-run summary:

```bash
python scripts/codex_status.py single /abs/path/run-dir --format text
```

Inspect the latest raw events:

```bash
tail -n 40 /abs/path/run-dir/events.jsonl
```

Open the latest events in the colorized terminal viewer:

```bash
python scripts/events_tui.py /abs/path/run-dir
```

Only show command executions and include short output previews:

```bash
python scripts/events_tui.py /abs/path/run-dir --item-type command_execution --show-output --output-lines 6
```

Include `item.started` noise when debugging a live run:

```bash
python scripts/events_tui.py /abs/path/run-dir --include-started --tail 120
```

Export a readable timeline without the TUI pager:

```bash
python scripts/codex_status.py events /abs/path/run-dir
```

Search for completed tool items:

```bash
rg -n '"type":"item.completed"' /abs/path/run-dir/events.jsonl
```

Inspect recent stderr:

```bash
tail -n 80 /abs/path/run-dir/stderr.log
```

## Event Reading Heuristics

- If `summary.json.status == "running"` and `last_command_status == "in_progress"`, the worker is still busy inside a tool call.
- If `summary.json.turn_completed == true` and `exit_code == 0`, treat the run as finished successfully.
- If `exit_code != 0`, inspect `stderr.log` and the last few `command_execution` items first.
- If `final.txt` is empty but `events.jsonl` has many lines, the worker probably has not reached the final response yet.
- If `pid_running == true` but the event counters are not moving, compare `events_age_seconds` and `stderr_age_seconds` before assuming the worker is dead.
- Default `events` view intentionally hides `item.started`; add `--include-started` only when you need to debug a hanging tool call.
- For large command outputs, start with `--show-output --output-lines 4` instead of opening the raw JSONL.

## What To Report Upstream

When summarizing one or many workers for a user or another agent, prefer:

- current status
- status reason and whether the pid is still alive
- last meaningful command
- final message path if present
- nonzero exit code if present
- the path to `summary.json` or `batch-status.json`

Do not paste entire JSONL logs unless the caller explicitly asks for them.
