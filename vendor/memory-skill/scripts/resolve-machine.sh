#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME="$SCRIPT_DIR/../runtime/memory_runtime.py"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$RUNTIME" machine "$@"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$RUNTIME" machine "$@"
fi

cat >&2 <<'EOF'
memory runtime error
What happened: Could not find a Python 3 interpreter for memory-skill.
Why it matters: The memory runtime is implemented in Python so it can behave consistently on Windows, Linux, and macOS.
How to fix: Install Python 3 and ensure `python3` or `python` is available on PATH, then retry this command.
EOF
exit 1
