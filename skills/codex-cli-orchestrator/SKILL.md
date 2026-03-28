---
name: codex-cli-orchestrator
description: Use when the user wants Codex to launch one or many `codex exec` workers from prompts or prompt files, keep JSONL/stderr/final-message logs on disk, monitor live run status from files, and collect batch results. Best for orchestration, automation, and parallel case execution. Focus on CLI flags, config overrides, environment variables, run directories, and status files; do not spend time on Codex DB internals or memory internals.
---

# Codex CLI Orchestrator

## Overview

Use this skill to treat `codex exec` as a worker process with a file-backed run contract.

It supports two main cases:

1. Launch one Codex worker for one prompt and keep `events.jsonl`, `stderr.log`, `final.txt`, and `summary.json` in one run directory.
2. Launch many Codex workers in parallel from a manifest, keep each worker isolated in its own run directory, and maintain a live `batch-status.json` plus final `batch-results.json`.

By default, the wrapper inherits the current Codex environment:

- the active `CODEX_HOME` if it is already set
- otherwise the normal home at `~/.codex`
- and therefore the current `config.toml`, installed skills, profiles, and auth material available from that home

## When To Use This Skill

Use this skill when the user wants any of the following:

- "Start a codex cli / codex exec and run this prompt"
- "Run many cases in parallel"
- "Put logs on disk so another agent can inspect progress"
- "Collect final results from multiple codex workers"
- "Build a reusable batch runner around Codex CLI"

Do not use this skill when the user only wants the current agent to solve the task directly without launching new Codex workers.

## Default Run Contract

Prefer a stable on-disk layout so other agents can inspect progress without reverse-engineering ad hoc logs.

For a single run, use one run directory with at least:

- `prompt.txt`
- `command.txt`
- `run-meta.txt`
- `events.jsonl`
- `stderr.log`
- `final.txt`
- `summary.json`
- `exit_code.txt`

For a batch run, use one batch directory with at least:

- `jobs.jsonl`
- `manifest.input.txt`
- `batch-config.json`
- `batch-status.json`
- `batch-results.json`
- `launcher.log`
- `runs/<job-id>/...` for each worker

The helper scripts in `scripts/` implement this layout.

## Quick Start

For one worker:

1. Write the prompt to a file.
2. Choose a run directory.
3. Run `scripts/run_codex_single.sh`.
4. Read `summary.json` for the current state and `final.txt` for the final message.

Example:

```bash
bash scripts/run_codex_single.sh /abs/path/prompt.txt /abs/path/run-dir /abs/path/workdir
```

For many workers:

1. Create a JSONL manifest with one job per line.
2. Choose a batch root directory.
3. Run `scripts/run_codex_batch.py`.
4. Inspect `batch-status.json` while jobs are running.
5. Read `batch-results.json` after completion.

Example:

```bash
python scripts/run_codex_batch.py /abs/path/jobs.jsonl /abs/path/batch-root
```

If the batch should keep running after the current shell exits:

```bash
python scripts/run_codex_batch.py /abs/path/jobs.jsonl /abs/path/batch-root --detach
```

## Default Wrapper Behavior

The wrapper always enforces the file-backed run contract:

- `--json`
- `-o <run-dir>/final.txt`
- `--skip-git-repo-check`

Beyond that, prefer inheritance over override:

- do not pass `-s`, `-m`, `-p`, `--disable multi_agent`, or `--color` unless the caller explicitly asks
- do not pass `-c approval_policy=...`, `web_search=...`, or `history.persistence=...` unless the caller explicitly asks
- let the worker resolve its normal config from the current Codex home by default

By default, the wrapper keeps using the inherited `CODEX_HOME` and does not create `batch-root/codex-home/`. If the caller sets `CODEX_RUN_HOME`, or explicitly starts the batch with `--isolate-home`, the wrapper seeds the fresh home from the current Codex home so the worker still sees the current config and local skills. This seeding covers shared non-state assets such as `config.toml`, `auth.json`, `skills/`, `profiles/`, `prompts/`, and `rules/`. Set `CODEX_RUN_HOME_SEED=0` only if you intentionally want an empty custom home.

Prefer `-c key=value` overrides over top-level global CLI flags when you are writing automation wrappers.

Before internet-dependent workers, make the network assumptions explicit. In this environment that usually means exporting proxy variables in the same shell that launches the batch, or passing them through each job's `env` field. The wrapper now records traced environment hints in `batch-config.json` and `run-meta.txt` so failures are easier to diagnose later.

## Single-Run Workflow

When launching one worker:

1. Put the prompt into `prompt.txt`.
2. Pick a dedicated run directory.
3. If the user wants isolated Codex session/log state for that worker, set `CODEX_RUN_HOME` before launch. By default the wrapper seeds that home from the current one so config and skills still match the current Codex environment.
4. Start `scripts/run_codex_single.sh`.
5. While it runs, read `summary.json` or rerun `python scripts/codex_status.py single <run-dir>`.
6. After completion, use `final.txt`, `summary.json`, and `events.jsonl` as the primary outputs.

If the user wants structured final output, set `CODEX_OUTPUT_SCHEMA` to a JSON Schema file path.

## Batch Workflow

When launching multiple workers:

1. Create a JSONL manifest. Each job should provide `id` plus either `prompt` or `prompt_file`.
2. Use a dedicated batch root directory.
3. Default to one run directory per job under `runs/`.
4. If job isolation matters, start the batch with `--isolate-home` so each worker gets its own `CODEX_HOME` under the batch root. Otherwise the default is to reuse the inherited home. The wrapper seeds each isolated home from the current Codex home unless you disable seeding.
5. Start `scripts/run_codex_batch.py`.
6. Inspect `batch-status.json` during execution.
7. Read each worker's `runs/<job-id>/summary.json` for details.
8. After completion, read `batch-results.json`.

Implementation detail:

- `batch-root/jobs.jsonl` is the normalized manifest actually used by the launcher.
- `batch-root/manifest.input.txt` keeps the original input manifest text for audit and reruns.
- `batch-root/batch.pid`, `batch-launch.stdout.log`, and `batch-launch.stderr.log` are written when `--detach` is used.

## Parameters And Environment

Read [references/runner-contract.md](./references/runner-contract.md) when you need:

- the full environment variable list
- the job manifest schema
- advanced config override patterns
- timeout and isolation knobs

Read [references/status-reading.md](./references/status-reading.md) when you need:

- how to inspect live progress
- which files matter first
- how to debug a stuck or failed worker
- how to use the human-readable `--format text` status view
- how to inspect `events.jsonl` in the colorized terminal viewer

## Writing Rules For This Skill

When using this skill:

- Keep orchestration deterministic and file-backed.
- Prefer helper scripts in `scripts/` over hand-written one-off shell snippets.
- Do preflight for shell-lifetime assumptions that commonly bite batch runs: `codex` on `PATH`, working directories, proxy env, and whether the batch needs to survive the current shell.
- Do not focus on Codex SQLite files, migration details, or memory repo internals unless the user explicitly asks.
- When reporting status, summarize from `summary.json` or `batch-status.json` first; only dive into raw `events.jsonl` when debugging.
- For batch jobs, keep prompts and outputs separated by job id. Do not mix worker logs in one shared file.
