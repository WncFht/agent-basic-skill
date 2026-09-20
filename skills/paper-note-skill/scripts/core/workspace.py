from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.user_config import OUTPUT_ROOT_ENV_VAR, resolve_output_root

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PAPER_ROOT_FALLBACK = REPO_ROOT / "paper"
PREAMBLE_FILE_NAME = "paper_note_annotations.tex"
ENTRY_FILE_NAME = "paper_note_bilingual.tex"
STALE_GENERATED_FILE_NAMES = (
    "paper_note_english.tex",
    "paper_note_english_clean.tex",
    "paper_note_chinese.tex",
)
STALE_GENERATED_DIR_NAMES = ("paper_note_zh",)
GENERATED_ENTRY_FILE_NAMES = (ENTRY_FILE_NAME,)

DEFAULT_PAPER_ROOT_ENV_VAR = OUTPUT_ROOT_ENV_VAR
DEFAULT_PAPER_ROOT = resolve_output_root(
    repo_root=REPO_ROOT,
    fallback_root=DEFAULT_PAPER_ROOT_FALLBACK,
).root


def resolve_existing_directory(raw_path: str, *, label: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise NotADirectoryError(f"{label} does not exist: {path}")
    return path


def resolve_directory(raw_path: str, *, label: str, create: bool) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise NotADirectoryError(f"{label} does not exist: {path}")
    return path


def resolve_workspace_file(workspace: Path, raw_path: str, *, label: str) -> Path:
    candidate = Path(raw_path).expanduser()
    path = candidate if candidate.is_absolute() else workspace / candidate
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def detect_main_tex(workspace: Path) -> Path:
    readme_path = workspace / "00README.json"
    if readme_path.exists():
        data = json.loads(readme_path.read_text(encoding="utf-8"))
        for source in data.get("sources", []):
            if source.get("usage") == "toplevel":
                candidate = workspace / source["filename"]
                if candidate.exists():
                    return candidate

    main_tex = workspace / "main.tex"
    if main_tex.exists():
        return main_tex

    for candidate in sorted(workspace.glob("*.tex")):
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        if r"\documentclass" in text and r"\begin{document}" in text:
            return candidate
    raise FileNotFoundError(f"Could not detect top-level TeX file under {workspace}")


def detect_existing_generated_paths(workspace: Path) -> list[Path]:
    candidates = [workspace / PREAMBLE_FILE_NAME]
    candidates.extend(workspace / name for name in GENERATED_ENTRY_FILE_NAMES)
    candidates.extend(workspace / name for name in STALE_GENERATED_FILE_NAMES)
    candidates.extend(workspace / name for name in STALE_GENERATED_DIR_NAMES)
    return [path for path in candidates if path.exists()]


def remove_generated_paths(paths: list[Path]) -> list[Path]:
    removed: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path)
    return removed


def needs_entry_refresh(entry_path: Path, main_tex: Path) -> bool:
    if not entry_path.exists():
        return False
    return main_tex.stat().st_mtime > entry_path.stat().st_mtime


def relative_to_workspace(workspace: Path, path: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


def detect_compiler(workspace: Path) -> str:
    readme_path = workspace / "00README.json"
    if not readme_path.exists():
        return "pdflatex"
    data = json.loads(readme_path.read_text(encoding="utf-8"))
    return data.get("process", {}).get("compiler", "pdflatex")


def workspace_notes(workspace: Path) -> list[str]:
    notes: list[str] = []
    try:
        main_tex = detect_main_tex(workspace)
        notes.append(f"detected main tex: {main_tex.name}")
    except FileNotFoundError as exc:
        notes.append(str(exc))
        return notes

    entry_path = workspace / ENTRY_FILE_NAME
    if entry_path.exists():
        notes.append(f"found generated entry: {entry_path.name}")
    else:
        notes.append("generated entry missing")

    preamble_path = workspace / PREAMBLE_FILE_NAME
    if preamble_path.exists():
        notes.append(f"found annotation preamble: {preamble_path.name}")
    else:
        notes.append("annotation preamble missing")

    return notes


def validate_workspace(workspace: Path) -> tuple[bool, list[str]]:
    notes = workspace_notes(workspace)
    is_valid = not any("Could not detect top-level TeX file" in note for note in notes)
    return is_valid, notes
