from __future__ import annotations

from pathlib import Path

from core.models import BuildPlan
from core.workspace import (
    ENTRY_FILE_NAME,
    detect_main_tex,
    resolve_workspace_file,
)


def needs_bibtex(tex_file: Path) -> bool:
    text = tex_file.read_text(encoding="utf-8", errors="ignore")
    return r"\bibliography{" in text or r"\bibliographystyle{" in text


def detect_pdf_path(workspace: Path, tex_file: Path) -> Path:
    candidates = [
        tex_file.with_suffix(".pdf"),
        workspace / f"{tex_file.stem}.pdf",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def detect_log_path(workspace: Path, tex_file: Path) -> Path:
    return workspace / f"{tex_file.stem}.paper-note-build.log"


def cleanup_stale_aux_files(
    workspace: Path,
    tex_file: Path,
    *,
    include_aux: bool = False,
) -> list[Path]:
    removed: list[Path] = []
    for suffix in (".toc", ".lof", ".lot", ".out", ".loc"):
        candidate = workspace / f"{tex_file.stem}{suffix}"
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate)
    if include_aux:
        aux_candidate = workspace / f"{tex_file.stem}.aux"
        if aux_candidate.exists():
            aux_candidate.unlink()
            removed.append(aux_candidate)
    return removed


def detect_default_build_targets(workspace: Path) -> tuple[Path, ...]:
    entry_path = workspace / ENTRY_FILE_NAME
    if entry_path.exists():
        return (entry_path,)
    return (detect_main_tex(workspace),)


def make_build_plan(
    workspace: Path,
    *,
    tex: str | None = None,
    quick: bool = False,
    refresh_entry: bool = False,
    skip_lint: bool = False,
) -> BuildPlan:
    if tex:
        targets = (resolve_workspace_file(workspace, tex, label="tex"),)
    else:
        targets = detect_default_build_targets(workspace)
    return BuildPlan(
        workspace=workspace,
        targets=targets,
        quick=quick,
        refresh_entry=refresh_entry,
        skip_lint=skip_lint,
    )
