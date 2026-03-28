#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run_codex_single.sh <prompt-file> <run-dir> [workdir]

Environment:
  CODEX_BIN                      default: codex
  CODEX_MODEL                    optional
  CODEX_PROFILE                  optional
  CODEX_SANDBOX                  optional; unset means inherit current Codex config
  CODEX_APPROVAL_POLICY          optional; unset means inherit current Codex config
  CODEX_WEB_SEARCH               optional; unset means inherit current Codex config
  CODEX_HISTORY_PERSISTENCE      optional; unset means inherit current Codex config
  CODEX_DISABLE_MULTI_AGENT      optional; unset means keep current feature/config behavior
  CODEX_COLOR                    optional; unset means inherit CLI default
  CODEX_OUTPUT_SCHEMA            optional JSON Schema path
  CODEX_ADDITIONAL_DIRS          optional colon-separated writable dirs
  CODEX_EXTRA_CONFIGS_FILE       optional file with one -c key=value per line
  CODEX_STATUS_INTERVAL          default: 5
  CODEX_OUTER_TIMEOUT            default: 0 (disabled)
  CODEX_OUTER_KILL_AFTER         default: 5m
  CODEX_CASE_OUTPUT_DIR          optional target case directory for logging and retry cleanup
  CODEX_BACKGROUND_TERMINAL_MAX_TIMEOUT optional config override
  CODEX_RUN_HOME                 optional dedicated CODEX_HOME for this worker
  CODEX_RUN_HOME_SEED            default: 1 when CODEX_RUN_HOME is set; symlink current config/skills/auth into the isolated home
  CODEX_TRACE_ENV_KEYS           optional env keys to record into run-meta.txt
EOF
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage >&2
  exit 2
fi

PROMPT_SOURCE="$1"
RUN_DIR="$2"
WORKDIR="${3:-${CODEX_WORKDIR:-$PWD}}"

if [[ ! -f "$PROMPT_SOURCE" ]]; then
  echo "missing prompt file: $PROMPT_SOURCE" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATUS_SCRIPT="$SCRIPT_DIR/codex_status.py"

CODEX_BIN="${CODEX_BIN:-codex}"
CODEX_STATUS_INTERVAL="${CODEX_STATUS_INTERVAL:-5}"
CODEX_OUTER_TIMEOUT="${CODEX_OUTER_TIMEOUT:-0}"
CODEX_OUTER_KILL_AFTER="${CODEX_OUTER_KILL_AFTER:-5m}"
SOURCE_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
CODEX_TRACE_ENV_KEYS="${CODEX_TRACE_ENV_KEYS:-http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY VIDEO_NOTE_PIPELINE_REPO VIDEO_NOTE_WORKSPACE_ROOT}"

if [[ ! -d "$WORKDIR" ]]; then
  echo "missing workdir: $WORKDIR" >&2
  exit 2
fi

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  echo "missing codex binary on PATH: $CODEX_BIN" >&2
  exit 2
fi

mkdir -p "$RUN_DIR"

PROMPT_COPY="$RUN_DIR/prompt.txt"
EVENTS_PATH="$RUN_DIR/events.jsonl"
STDERR_PATH="$RUN_DIR/stderr.log"
FINAL_PATH="$RUN_DIR/final.txt"
SUMMARY_PATH="$RUN_DIR/summary.json"
COMMAND_PATH="$RUN_DIR/command.txt"
META_PATH="$RUN_DIR/run-meta.txt"
EXIT_CODE_PATH="$RUN_DIR/exit_code.txt"
PID_PATH="$RUN_DIR/pid.txt"
RESULT_PATH="$RUN_DIR/result.txt"
STARTED_AT="$(date --iso-8601=seconds)"

if [[ "$PROMPT_SOURCE" != "$PROMPT_COPY" ]]; then
  cp "$PROMPT_SOURCE" "$PROMPT_COPY"
fi

cmd=(
  "$CODEX_BIN"
  exec
  --skip-git-repo-check
  --json
  -o "$FINAL_PATH"
  -C "$WORKDIR"
)

if [[ -n "${CODEX_COLOR:-}" ]]; then
  cmd+=( --color "$CODEX_COLOR" )
fi

if [[ -n "${CODEX_SANDBOX:-}" ]]; then
  cmd+=( -s "$CODEX_SANDBOX" )
fi

if [[ -n "${CODEX_DISABLE_MULTI_AGENT:-}" && "${CODEX_DISABLE_MULTI_AGENT:-}" != "0" ]]; then
  cmd+=( --disable multi_agent )
fi

if [[ -n "${CODEX_MODEL:-}" ]]; then
  cmd+=( -m "$CODEX_MODEL" )
fi

if [[ -n "${CODEX_PROFILE:-}" ]]; then
  cmd+=( -p "$CODEX_PROFILE" )
fi

if [[ -n "${CODEX_OUTPUT_SCHEMA:-}" ]]; then
  cmd+=( --output-schema "$CODEX_OUTPUT_SCHEMA" )
fi

IFS=':' read -r -a additional_dirs <<< "${CODEX_ADDITIONAL_DIRS:-}"
for dir in "${additional_dirs[@]}"; do
  if [[ -n "$dir" ]]; then
    cmd+=( --add-dir "$dir" )
  fi
done

if [[ -n "${CODEX_APPROVAL_POLICY:-}" ]]; then
  cmd+=( -c "approval_policy=\"$CODEX_APPROVAL_POLICY\"" )
fi

if [[ -n "${CODEX_WEB_SEARCH:-}" ]]; then
  cmd+=( -c "web_search=\"$CODEX_WEB_SEARCH\"" )
fi

if [[ -n "${CODEX_HISTORY_PERSISTENCE:-}" ]]; then
  cmd+=( -c "history.persistence=\"$CODEX_HISTORY_PERSISTENCE\"" )
fi

if [[ -n "${CODEX_BACKGROUND_TERMINAL_MAX_TIMEOUT:-}" ]]; then
  cmd+=( -c "background_terminal_max_timeout=$CODEX_BACKGROUND_TERMINAL_MAX_TIMEOUT" )
fi

if [[ -n "${CODEX_EXTRA_CONFIGS_FILE:-}" && -f "${CODEX_EXTRA_CONFIGS_FILE:-}" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ -z "$line" || "${line:0:1}" == "#" ]]; then
      continue
    fi
    cmd+=( -c "$line" )
  done < "$CODEX_EXTRA_CONFIGS_FILE"
fi

cmd+=( - )

meta_value() {
  local value="${1:-}"
  if [[ -n "$value" ]]; then
    printf '%s' "$value"
  else
    printf '<inherit>'
  fi
}

env_value() {
  local key="$1"
  if [[ -n "${!key+x}" ]]; then
    printf '%s' "${!key}"
  else
    printf '<unset>'
  fi
}

seed_run_home() {
  local source_home="$1"
  local target_home="$2"
  local seed_enabled="${CODEX_RUN_HOME_SEED:-1}"
  local name

  if [[ "$seed_enabled" == "0" ]]; then
    return
  fi

  if [[ "${target_home%/}" == "${source_home%/}" ]]; then
    return
  fi

  for name in config.toml auth.json skills profiles prompts rules; do
    if [[ ! -e "$source_home/$name" ]]; then
      continue
    fi
    if [[ -e "$target_home/$name" || -L "$target_home/$name" ]]; then
      continue
    fi
    ln -s "$source_home/$name" "$target_home/$name"
  done
}

{
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'prompt_source=%s\n' "$PROMPT_SOURCE"
  printf 'workdir=%s\n' "$WORKDIR"
  printf 'codex_bin=%s\n' "$CODEX_BIN"
  printf 'source_codex_home=%s\n' "$SOURCE_CODEX_HOME"
  printf 'sandbox=%s\n' "$(meta_value "${CODEX_SANDBOX:-}")"
  printf 'approval_policy=%s\n' "$(meta_value "${CODEX_APPROVAL_POLICY:-}")"
  printf 'web_search=%s\n' "$(meta_value "${CODEX_WEB_SEARCH:-}")"
  printf 'history_persistence=%s\n' "$(meta_value "${CODEX_HISTORY_PERSISTENCE:-}")"
  printf 'disable_multi_agent=%s\n' "$(meta_value "${CODEX_DISABLE_MULTI_AGENT:-}")"
  printf 'color=%s\n' "$(meta_value "${CODEX_COLOR:-}")"
  printf 'outer_timeout=%s\n' "$CODEX_OUTER_TIMEOUT"
  printf 'outer_kill_after=%s\n' "$CODEX_OUTER_KILL_AFTER"
  printf 'case_output_dir=%s\n' "$(meta_value "${CODEX_CASE_OUTPUT_DIR:-}")"
  printf 'attempt_number=%s\n' "${CODEX_ATTEMPT_NUMBER:-1}"
  printf 'max_attempts=%s\n' "${CODEX_MAX_ATTEMPTS:-1}"
  printf 'retry_on_timeout_max=%s\n' "${CODEX_RETRY_ON_TIMEOUT_MAX:-0}"
  printf 'run_home_seed=%s\n' "${CODEX_RUN_HOME_SEED:-1}"
  printf 'codex_home=%s\n' "${CODEX_RUN_HOME:-${CODEX_HOME:-<default>}}"
  printf 'trace_env_keys=%s\n' "$CODEX_TRACE_ENV_KEYS"
  for key in $CODEX_TRACE_ENV_KEYS; do
    printf 'env[%s]=%s\n' "$key" "$(env_value "$key")"
  done
} > "$META_PATH"

{
  printf 'attempt_number=%s\n' "${CODEX_ATTEMPT_NUMBER:-1}"
  printf 'max_attempts=%s\n' "${CODEX_MAX_ATTEMPTS:-1}"
  printf 'retry_on_timeout_max=%s\n' "${CODEX_RETRY_ON_TIMEOUT_MAX:-0}"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'outer_timeout=%s\n' "$CODEX_OUTER_TIMEOUT"
  printf 'outer_kill_after=%s\n' "$CODEX_OUTER_KILL_AFTER"
  printf 'timed_out=false\n'
} > "$RESULT_PATH"

printf '%q ' "${cmd[@]}" > "$COMMAND_PATH"
printf '\n' >> "$COMMAND_PATH"

if [[ -n "${CODEX_RUN_HOME:-}" ]]; then
  mkdir -p "$CODEX_RUN_HOME"
  seed_run_home "$SOURCE_CODEX_HOME" "$CODEX_RUN_HOME"
  export CODEX_HOME="$CODEX_RUN_HOME"
fi

(
  set +e
  if [[ "$CODEX_OUTER_TIMEOUT" == "0" ]]; then
    "${cmd[@]}" < "$PROMPT_COPY" > "$EVENTS_PATH" 2> "$STDERR_PATH"
    rc=$?
    timed_out=false
  else
    timeout -k "$CODEX_OUTER_KILL_AFTER" "$CODEX_OUTER_TIMEOUT" "${cmd[@]}" < "$PROMPT_COPY" > "$EVENTS_PATH" 2> "$STDERR_PATH"
    rc=$?
    if [[ "$rc" == "124" || "$rc" == "137" ]]; then
      timed_out=true
    else
      timed_out=false
    fi
  fi
  printf '%s\n' "$rc" > "$EXIT_CODE_PATH"
  {
    printf 'finished_at=%s\n' "$(date --iso-8601=seconds)"
    printf 'exit_code=%s\n' "$rc"
    printf 'timed_out=%s\n' "$timed_out"
  } >> "$RESULT_PATH"
) &
runner_pid=$!
printf '%s\n' "$runner_pid" > "$PID_PATH"

while kill -0 "$runner_pid" 2>/dev/null; do
  python "$STATUS_SCRIPT" single "$RUN_DIR" --write "$SUMMARY_PATH" >/dev/null 2>&1 || true
  sleep "$CODEX_STATUS_INTERVAL"
done

set +e
wait "$runner_pid"
wait_rc=$?
set -e

if [[ ! -f "$EXIT_CODE_PATH" ]]; then
  printf '%s\n' "$wait_rc" > "$EXIT_CODE_PATH"
fi

python "$STATUS_SCRIPT" single "$RUN_DIR" --write "$SUMMARY_PATH" >/dev/null

exit_code="$(cat "$EXIT_CODE_PATH")"
{
  printf 'finished_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'final_exit_code=%s\n' "$exit_code"
} >> "$META_PATH"
exit "$exit_code"
