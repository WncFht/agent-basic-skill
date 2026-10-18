from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

from core.models import DoctorResult, ToolCheck
from core.workspace import validate_workspace


def check_tool(name: str) -> ToolCheck:
    path = shutil.which(name)
    return ToolCheck(name=name, found=path is not None, path=path)


def check_python_module(name: str) -> ToolCheck:
    spec = importlib.util.find_spec(name)
    return ToolCheck(
        name=name,
        found=spec is not None,
        path=getattr(spec, "origin", None) if spec is not None else None,
    )


def run_doctor(workspace: Path | None = None) -> DoctorResult:
    tools = tuple(
        check_tool(name) for name in ("pdflatex", "bibtex", "pdftoppm", "kpsewhich")
    )
    python_modules = (check_python_module("requests"),)

    workspace_status = None
    notes: list[str] = []
    if workspace is not None:
        is_valid, workspace_notes = validate_workspace(workspace)
        workspace_status = "ok" if is_valid else "invalid"
        notes.extend(workspace_notes)

    return DoctorResult(
        workspace=workspace,
        tools=tools,
        python_modules=python_modules,
        workspace_status=workspace_status,
        notes=tuple(notes),
    )
