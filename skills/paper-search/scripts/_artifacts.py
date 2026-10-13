"""Resolve where run artifacts (reports, logs) are written.

Why: the CLI used to always write under Path.cwd(), so invoking it from a
repository subdirectory scattered paper-search-reports/ and paper-search-logs/
at every level of the tree. Now the artifact root is, in order:

1. PAPER_SEARCH_ROOT environment variable (explicit override)
2. nearest ancestor of cwd containing .git (project root)
3. cwd (fallback, preserves behavior outside repos)
"""

from __future__ import annotations

import os
from pathlib import Path


def artifact_root() -> Path:
    env = os.environ.get("PAPER_SEARCH_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / ".git").exists():
            return parent
    return cwd
