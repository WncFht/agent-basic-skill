# Runner Contract

This skill uses one file-backed contract for both single and batch `codex exec` orchestration.

## Single Run

Command:

```bash
bash scripts/run_codex_single.sh /abs/path/prompt.txt /abs/path/run-dir /abs/path/workdir
```

Standard files written under `run-dir`:

- `prompt.txt`
- `command.txt`
- `run-meta.txt`
- `events.jsonl`
- `stderr.log`
- `final.txt`
- `summary.json`
- `exit_code.txt`
- `pid.txt`
- `result.txt`
- `attempt-state.json`
- `attempt-history.jsonl`
- `attempts/attempt-XX/` when a timed-out attempt is archived before retry

## Batch Run

Command:

```bash
python scripts/run_codex_batch.py /abs/path/jobs.jsonl /abs/path/batch-root
```

Standard files written under `batch-root`:

- `jobs.jsonl`
- `manifest.input.txt`
- `batch-config.json`
- `batch-status.json`
- `batch-results.json`
- `launcher.log`
- `runs/<job-id>/...`

Each `runs/<job-id>/` directory also gets:

- `launcher.stdout.log`
- `launcher.stderr.log`

Optional detached-launch files:

- `batch.pid`
- `batch-launch.stdout.log`
- `batch-launch.stderr.log`
- `detach-info.json`
- `batch-error.txt`

## Environment Variables

These variables are consumed by `run_codex_single.sh`, and `run_codex_batch.py` maps per-job fields onto the same names.

Unless an override below is explicitly set, the worker inherits the active Codex environment from the current shell:

- current `CODEX_HOME` if present
- otherwise the normal `~/.codex`
- and therefore the current `config.toml`, installed skills, profiles, and auth material reachable from that home

- `CODEX_BIN`
  - Default: `codex`
  - Override when the binary is not on `PATH` or when pinning a specific build.

- `CODEX_MODEL`
  - Optional model override passed as `-m`.

- `CODEX_PROFILE`
  - Optional profile override passed as `-p`.

- `CODEX_SANDBOX`
  - Optional sandbox override.
  - If unset, the wrapper does not add `-s`, so Codex resolves sandboxing from the current config.

- `CODEX_APPROVAL_POLICY`
  - Optional approval override.
  - If unset, the wrapper does not add `-c 'approval_policy=...'`.

- `CODEX_WEB_SEARCH`
  - Optional web search override.
  - If unset, the wrapper does not add `-c 'web_search=...'`.

- `CODEX_HISTORY_PERSISTENCE`
  - Optional history persistence override.
  - If unset, the wrapper does not add `-c 'history.persistence=...'`.

- `CODEX_DISABLE_MULTI_AGENT`
  - Optional feature override.
  - When set to a nonzero value, the wrapper adds `--disable multi_agent`.
  - When unset, the wrapper leaves current feature/config behavior untouched.

- `CODEX_COLOR`
  - Optional CLI output override.
  - If unset, the wrapper does not add `--color`.

- `CODEX_OUTPUT_SCHEMA`
  - Optional path passed to `--output-schema`.

- `CODEX_ADDITIONAL_DIRS`
  - Optional colon-separated directory list.
  - Each entry becomes `--add-dir <dir>`.

- `CODEX_EXTRA_CONFIGS_FILE`
  - Optional file containing one `-c key=value` override per line.
  - Use this for extra config knobs that are not modeled as first-class env vars.

- `CODEX_BACKGROUND_TERMINAL_MAX_TIMEOUT`
  - Optional config override.
  - If set, the wrapper adds `-c background_terminal_max_timeout=<value>`.

- `CODEX_OUTER_TIMEOUT`
  - Default: `0`
  - Outer watchdog around the entire worker process.
  - `0` means disabled.

- `CODEX_OUTER_KILL_AFTER`
  - Default: `5m`
  - Used only when `CODEX_OUTER_TIMEOUT` is nonzero.

- `CODEX_CASE_OUTPUT_DIR`
  - Optional case output directory hint for one worker.
  - Used by the batch retry path so a timed-out attempt can archive partial case output before the next attempt starts.

- `CODEX_STATUS_INTERVAL`
  - Default: `5`
  - Seconds between `summary.json` refreshes.

- `CODEX_RUN_HOME`
  - Optional dedicated `CODEX_HOME` for one worker.
  - Useful when the caller wants isolated sessions and logs per worker.
  - By default the wrapper seeds a fresh run home from the current home by symlinking shared non-state assets such as `config.toml`, `auth.json`, `skills/`, `profiles/`, `prompts/`, and `rules/`.

- `--isolate-home`
  - Batch-only CLI flag on `run_codex_batch.py`.
  - Assigns `CODEX_RUN_HOME=<batch-root>/codex-home/<job-id>` unless the job already provides `run_home`.
  - Default behavior is the opposite: reuse the inherited `CODEX_HOME`.

- `CODEX_ISOLATE_HOME`
  - Deprecated environment flag.
  - The batch launcher ignores this ambient env var by default to avoid surprising `codex-home/` directories.
  - Use `--isolate-home` or per-job `run_home` instead.

- `CODEX_RUN_HOME_SEED`
  - Default: `1` when `CODEX_RUN_HOME` is used.
  - If nonzero, seed a fresh run home from the current one.
  - Set to `0` only when you intentionally want a blank custom home.

- `CODEX_PARALLELISM`
  - Batch-only default for `--parallelism`.

- `CODEX_TRACE_ENV_KEYS`
  - Optional space/comma/colon-separated list of environment keys to record into `batch-config.json` and `run-meta.txt`.
  - Useful for proxy, workspace, runtime repo, or other launch-context debugging.
  - Default keys include common proxy vars plus `VIDEO_NOTE_PIPELINE_REPO` and `VIDEO_NOTE_WORKSPACE_ROOT`.

## Manifest Schema

Use JSONL by default. One object per line.

Required:

- `id`
- one of `prompt` or `prompt_file`

Common optional fields:

- `workdir`
- `model`
- `profile`
- `sandbox`
- `approval_policy`
- `web_search`
- `history_persistence`
- `output_schema`
- `additional_dirs`
- `disable_multi_agent`
- `background_terminal_max_timeout`
- `outer_timeout`
- `outer_kill_after`
- `retry_on_timeout_max`
- `case_output_dir`
- `extra_configs`
- `env`
- `run_home`

Notes:

- `batch-root/jobs.jsonl` is the normalized launcher view after prompt expansion and path resolution.
- `batch-root/manifest.input.txt` keeps the original manifest text that was passed to the launcher.

Example:

```json
{"id":"case-a","prompt_file":"/abs/prompts/a.txt","workdir":"/abs/repo-a","sandbox":"workspace-write","approval_policy":"never","web_search":"disabled"}
{"id":"case-b","prompt":"只输出 OK","workdir":"/tmp","disable_multi_agent":true,"extra_configs":["background_terminal_max_timeout=14400"]}
```

Timeout retry behavior:

- `retry_on_timeout_max=0` means do not retry.
- `retry_on_timeout_max=1` means at most two total attempts.
- A retry is triggered only when the wrapper marks the attempt as `timed_out=true` in `result.txt`.
- Before retrying, the launcher archives the attempt's run files into `attempts/attempt-XX/`.
- If `case_output_dir` is set and exists, the partial case output is moved into `attempts/attempt-XX/case-output/` before the next attempt starts.

## Recommended CLI Shape

Minimal wrapper shape that inherits the current Codex config:

```bash
codex exec \
  --skip-git-repo-check \
  --json \
  -o /abs/run/final.txt \
  -C /abs/workdir \
  -
```

Explicit override shape when the caller asks for it:

```bash
codex exec \
  --skip-git-repo-check \
  --json \
  --color never \
  -o /abs/run/final.txt \
  -C /abs/workdir \
  -s workspace-write \
  --disable multi_agent \
  -c 'approval_policy="never"' \
  -c 'web_search="disabled"' \
  -c 'history.persistence="none"' \
  -
```

Prefer `-c` config overrides over top-level global flags when you intentionally need overrides.

Detached launcher shape:

```bash
python scripts/run_codex_batch.py /abs/path/jobs.jsonl /abs/path/batch-root --detach
```
