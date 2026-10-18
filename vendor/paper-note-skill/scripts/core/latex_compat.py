from __future__ import annotations

import subprocess
from pathlib import Path

BINHEX_ASSET = Path(__file__).resolve().parents[1] / "assets" / "binhex.tex"


def ensure_binhex_compat(workspace: Path) -> str:
    workspace_binhex = workspace / "binhex.tex"
    if workspace_binhex.exists():
        return "workspace"

    try:
        result = subprocess.run(
            ["kpsewhich", "binhex.tex"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        result = None

    if result is not None and result.returncode == 0 and result.stdout.strip():
        return "system"

    workspace_binhex.write_text(
        BINHEX_ASSET.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return "created"
