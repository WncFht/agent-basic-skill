from __future__ import annotations

import argparse
from pathlib import Path

from core.build_plan import detect_default_build_targets, detect_pdf_path
from core.models import ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.visual import run_visual_check
from core.workspace import resolve_existing_directory, resolve_workspace_file

COMMAND_NAME = "visual-check"
COMMAND_DESCRIPTION = (
    "Render preview pages and scan TeX sources for layout risk patterns."
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workspace", help="Paper workspace directory.")
    parser.add_argument(
        "--pdf",
        help="Explicit PDF path. Defaults to the PDF for the default build target.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=4,
        help="How many leading pages to render for preview.",
    )
    add_format_argument(parser)


def resolve_pdf_path(workspace: Path, raw_pdf: str | None) -> Path:
    if raw_pdf:
        return resolve_workspace_file(workspace, raw_pdf, label="pdf")
    target = detect_default_build_targets(workspace)[0]
    pdf_path = detect_pdf_path(workspace, target)
    if not pdf_path.exists():
        raise FileNotFoundError(f"pdf does not exist: {pdf_path}")
    return pdf_path


def run_from_args(args: argparse.Namespace) -> int:
    try:
        workspace = resolve_existing_directory(args.workspace, label="workspace")
        pdf_path = resolve_pdf_path(workspace, args.pdf)
        result = run_visual_check(workspace, pdf_path, pages=args.pages)
        emit_result(
            command_result(
                COMMAND_NAME,
                status=result.status,
                exit_code=ExitCode.SUCCESS,
                workspace=workspace,
                pdf=result.pdf,
                preview_dir=result.preview_dir,
                rendered_pages=result.rendered_pages,
                risky_floats=result.risky_floats,
                note=result.note,
            ),
            args.format,
        )
        return int(ExitCode.SUCCESS)
    except Exception as exc:
        emit_result(
            error_result(
                COMMAND_NAME,
                exit_code=ExitCode.INPUT_ERROR,
                error=str(exc),
            ),
            args.format,
        )
        return int(ExitCode.INPUT_ERROR)
