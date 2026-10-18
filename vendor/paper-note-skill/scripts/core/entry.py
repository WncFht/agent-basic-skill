from __future__ import annotations

from pathlib import Path

from core.models import GeneratedEntryResult, SetupResult
from core.workspace import (
    ENTRY_FILE_NAME,
    GENERATED_ENTRY_FILE_NAMES,
    PREAMBLE_FILE_NAME,
    detect_existing_generated_paths,
    detect_main_tex,
    remove_generated_paths,
)

PREAMBLE_ASSET = Path(__file__).resolve().parents[1] / "assets" / PREAMBLE_FILE_NAME

GENERATED_LINE_MARKERS = {
    rf"\input{{{PREAMBLE_FILE_NAME}}}",
    r"\annotnotestrue",
    r"\annotnotesfalse",
    r"\begin{CJK*}{UTF8}{gbsn}",
    r"\end{CJK*}",
    r"\setcounter{footnote}{0}",
    r"\renewcommand{\thefootnote}{\arabic{footnote}}",
}


def parse_toggle(value: str | bool, *, label: str) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered == "on":
        return True
    if lowered == "off":
        return False
    raise ValueError(f"Unsupported {label} toggle: {value}")


def read_existing_notes_enabled(entry_path: Path) -> bool | None:
    if not entry_path.exists():
        return None
    text = entry_path.read_text(encoding="utf-8", errors="ignore")
    if r"\annotnotestrue" in text:
        return True
    if r"\annotnotesfalse" in text:
        return False
    return None


def sanitize_main_text(text: str) -> str:
    trailing_newline = text.endswith("\n")
    kept_lines = [
        line for line in text.splitlines() if line.strip() not in GENERATED_LINE_MARKERS
    ]
    sanitized = "\n".join(kept_lines)
    if trailing_newline:
        sanitized += "\n"
    return sanitized


def ensure_annotation_preamble(text: str, *, notes_enabled: bool) -> str:
    marker_line = rf"\input{{{PREAMBLE_FILE_NAME}}}"
    toggle_line = r"\annotnotestrue" if notes_enabled else r"\annotnotesfalse"
    if marker_line in text:
        text = text.replace(marker_line, "").replace("\n\n\n", "\n\n")
    if toggle_line not in text:
        text = text.replace(
            r"\begin{document}",
            toggle_line + "\n" + r"\begin{document}",
            1,
        )
    if marker_line in text:
        return text

    insertion_markers = (
        r"\bipapertitle{",
        r"\title{",
        r"\begin{abstract}",
        r"\begin{document}",
    )
    for marker in insertion_markers:
        if marker in text:
            return text.replace(marker, marker_line + "\n" + marker, 1)
    raise ValueError(
        "Top-level TeX file does not contain a supported insertion marker for "
        "\\input{paper_note_annotations.tex}"
    )


def ensure_cjk_wrapper(text: str) -> str:
    if r"\begin{CJK*}" not in text:
        text = text.replace(
            r"\begin{document}",
            "\\begin{document}\n\\begin{CJK*}{UTF8}{gbsn}",
            1,
        )
    if r"\end{CJK*}" not in text:
        text = text.replace(r"\end{document}", "\\end{CJK*}\n\\end{document}", 1)
    return text


def maybe_reset_footnotes(text: str) -> str:
    if (
        r"\maketitle" not in text
        or r"\renewcommand{\thefootnote}{\arabic{footnote}}" in text
    ):
        return text
    reset = (
        "\\maketitle\n"
        "\\setcounter{footnote}{0}\n"
        "\\renewcommand{\\thefootnote}{\\arabic{footnote}}"
    )
    return text.replace(r"\maketitle", reset, 1)


def build_entry_text(text: str, *, notes_enabled: bool) -> str:
    entry = sanitize_main_text(text)
    entry = ensure_annotation_preamble(entry, notes_enabled=notes_enabled)
    entry = ensure_cjk_wrapper(entry)
    entry = maybe_reset_footnotes(entry)
    return entry


def refresh_generated_entry(
    workspace: Path,
    *,
    main_tex: Path | None = None,
    notes_enabled: bool | None = None,
) -> GeneratedEntryResult:
    main_tex = main_tex or detect_main_tex(workspace)
    entry_path = workspace / ENTRY_FILE_NAME
    preamble_path = workspace / PREAMBLE_FILE_NAME

    if notes_enabled is None:
        inferred_notes_enabled = read_existing_notes_enabled(entry_path)
        notes_enabled = (
            True if inferred_notes_enabled is None else inferred_notes_enabled
        )

    preamble_path.write_text(
        PREAMBLE_ASSET.read_text(encoding="utf-8"), encoding="utf-8"
    )
    normalized_main_text = main_tex.read_text(encoding="utf-8", errors="ignore")
    entry_path.write_text(
        build_entry_text(normalized_main_text, notes_enabled=notes_enabled),
        encoding="utf-8",
    )
    return GeneratedEntryResult(
        main_tex=main_tex,
        entry_path=entry_path,
        preamble_path=preamble_path,
        notes_enabled=notes_enabled,
    )


def prepare_workspace(
    workspace: Path,
    *,
    force: bool,
    notes_enabled: bool,
    main_tex: Path | None = None,
) -> SetupResult:
    existing_generated_paths = detect_existing_generated_paths(workspace)
    if existing_generated_paths and not force:
        existing_text = "\n".join(f"  - {path}" for path in existing_generated_paths)
        raise FileExistsError(
            "Generated paper-note files already exist:\n"
            f"{existing_text}\n"
            "Re-run with --force if you really want to overwrite them."
        )

    removed_generated_paths = tuple(
        remove_generated_paths(existing_generated_paths) if force else []
    )
    refresh_result = refresh_generated_entry(
        workspace,
        main_tex=main_tex,
        notes_enabled=notes_enabled,
    )
    return SetupResult(
        workspace=workspace,
        main_tex=refresh_result.main_tex,
        entry_path=refresh_result.entry_path,
        preamble_path=refresh_result.preamble_path,
        notes_enabled=refresh_result.notes_enabled,
        removed_generated_paths=removed_generated_paths,
    )


def generated_entry_files() -> tuple[str, ...]:
    return GENERATED_ENTRY_FILE_NAMES
