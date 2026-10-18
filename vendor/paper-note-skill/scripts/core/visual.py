from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from core.models import FloatHit, VisualCheckResult

RISKY_FLOAT_RE = re.compile(r"\\begin\{(wrapfigure|wraptable)\}")


def line_number_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def collect_tex_files(workspace: Path) -> list[Path]:
    return sorted(path for path in workspace.rglob("*.tex") if path.is_file())


def scan_risky_floats(workspace: Path) -> tuple[FloatHit, ...]:
    hits: list[FloatHit] = []
    for tex_path in collect_tex_files(workspace):
        text = tex_path.read_text(encoding="utf-8", errors="ignore")
        for match in RISKY_FLOAT_RE.finditer(text):
            hits.append(
                FloatHit(
                    path=tex_path.relative_to(workspace),
                    line=line_number_at(text, match.start()),
                    env_name=match.group(1),
                )
            )
    return tuple(hits)


def render_preview_pages(
    workspace: Path,
    pdf_path: Path,
    *,
    pages: int,
) -> tuple[Path | None, int, str]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return None, 0, "skipped: pdftoppm not found"

    preview_dir = workspace / ".paper_note_visual_check" / pdf_path.stem
    preview_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = preview_dir / "page"
    command = [
        pdftoppm,
        "-png",
        "-f",
        "1",
        "-l",
        str(max(1, pages)),
        str(pdf_path),
        str(output_prefix),
    ]
    result = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        note = (result.stdout + result.stderr).strip() or "pdftoppm failed"
        return preview_dir, 0, f"failed: {note}"

    rendered = len(sorted(preview_dir.glob("page-*.png")))
    if rendered:
        return preview_dir, rendered, "rendered"
    return preview_dir, rendered, "failed: no preview pages"


def run_visual_check(
    workspace: Path,
    pdf_path: Path,
    *,
    pages: int = 4,
) -> VisualCheckResult:
    risky_floats = scan_risky_floats(workspace)
    preview_dir, rendered_pages, render_note = render_preview_pages(
        workspace,
        pdf_path,
        pages=pages,
    )

    status = "ok"
    notes: list[str] = []
    if risky_floats:
        status = "needs_review"
        notes.append("detected wrapfigure/wraptable in TeX sources")
    if render_note != "rendered":
        if status == "ok":
            status = "needs_review"
        notes.append(render_note)
    elif rendered_pages:
        notes.append(f"rendered {rendered_pages} preview pages")

    if not notes:
        notes.append("visual check clean")

    return VisualCheckResult(
        pdf=pdf_path,
        preview_dir=preview_dir,
        rendered_pages=rendered_pages,
        risky_floats=risky_floats,
        status=status,
        note="; ".join(notes),
    )
