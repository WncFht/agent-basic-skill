"""Resolve the shared root for persistent reports and run logs.

PAPER_SEARCH_ROOT is an explicit override. The default is independent of cwd
and repository layout, so searches never scatter artifacts across projects.
"""

from __future__ import annotations

import os
from pathlib import Path


def artifact_root() -> Path:
    env = os.environ.get("PAPER_SEARCH_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".local" / "share" / "paper-search"
