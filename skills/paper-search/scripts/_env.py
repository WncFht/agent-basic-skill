"""Lightweight .env loader for the paper-search scripts.

Why: the source connectors read credentials via os.environ (e.g. OPENREVIEW_USER/PASS).
When these scripts are invoked directly by an LLM through bash, the shell has NOT sourced
any .env, so those vars are empty and the credentialed sources silently degrade. This module
walks up from the script directory to find a .env and loads it into os.environ BEFORE the
connectors run — no external dependency (not python-dotenv), shell-set vars take precedence.

Search order: the first .env in an ancestor directory of this script. Search
stops at the repository root so credentials from sibling skills are never
loaded implicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def _apply(env_path: Path) -> None:
    try:
        contents = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"could not read environment file {env_path}: {exc}"
        ) from exc
    for line_number, line in enumerate(contents.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key.replace("_", "a").isalnum() or key[0].isdigit():
            raise RuntimeError(f"invalid environment key at {env_path}:{line_number}")
        # A value already exported in the real shell wins over the .env file.
        os.environ.setdefault(key, val)


def load_env_once() -> Path | None:
    """Load the first .env found (see module docstring). Idempotent. Returns the path used."""
    global _loaded
    if _loaded:
        return None
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for parent in here.parents:
        candidates.append(parent / ".env")
        if (parent / ".git").exists():
            break

    for cand in candidates:
        if cand.is_file():
            _apply(cand)
            _loaded = True
            return cand
    _loaded = True
    return None
