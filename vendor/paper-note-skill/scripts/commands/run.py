from __future__ import annotations

import argparse

from core.arxiv import fetch_source_to_workspace
from core.build_exec import build_workspace
from core.entry import parse_toggle, prepare_workspace
from core.models import BuildResult, ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.visual import run_visual_check
from core.workspace import DEFAULT_PAPER_ROOT, resolve_directory

COMMAND_NAME = "run"
COMMAND_DESCRIPTION = (
    "Run fetch, setup, build, and visual-check as one paper-note workflow."
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "input",
        help="arXiv abs URL, pdf URL, or arXiv ID such as 2604.13737 / 2604.13737v1",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_PAPER_ROOT),
        help="Root directory where the paper workspace will be created or reused.",
    )
    parser.add_argument(
        "--version",
        help="Optional arXiv version override such as 2 or v2.",
    )
    parser.add_argument(
        "--notes",
        choices=("on", "off"),
        default="on",
        help="Whether the generated bilingual entry enables function-block pnotes.",
    )
    parser.add_argument(
        "--skip-full-build",
        action="store_true",
        help="Stop after setup + quick build, without running the full compile or visual check.",
    )
    add_format_argument(parser)


def summarize_build(result: BuildResult) -> dict[str, object]:
    first_target = result.targets[0] if result.targets else None
    return {
        "status": result.status,
        "exit_code": result.exit_code,
        "targets": [path.name for path in result.plan.targets],
        "lint_status": (
            "skipped"
            if result.lint_result is None
            else ("failed" if result.lint_result.issues else "clean")
        ),
        "lint_issue_count": 0
        if result.lint_result is None
        else len(result.lint_result.issues),
        "entry_refresh": result.refresh_reason,
        "pdf": first_target.pdf.name if first_target and first_target.pdf else None,
        "log": first_target.log.name if first_target else None,
        "warnings": [] if first_target is None else list(first_target.warnings),
    }


def run_from_args(args: argparse.Namespace) -> int:
    try:
        root = resolve_directory(args.root, label="root", create=True)
        fetch_result = fetch_source_to_workspace(
            args.input,
            root=root,
            version=args.version,
            keep_archive=False,
            clean_source=True,
        )
        workspace = fetch_result.workspace
        setup_result = prepare_workspace(
            workspace,
            force=False,
            notes_enabled=parse_toggle(args.notes, label="notes"),
        )
        quick_build = build_workspace(
            workspace,
            tex=setup_result.entry_path.name,
            quick=True,
            refresh_entry=True,
            skip_lint=False,
        )
        if quick_build.exit_code != int(ExitCode.SUCCESS):
            emit_result(
                command_result(
                    COMMAND_NAME,
                    status="quick_build_failed",
                    exit_code=quick_build.exit_code,
                    workspace=workspace,
                    paper_id_with_version=fetch_result.paper_id_with_version,
                    source_url=fetch_result.source_url,
                    quick_build=summarize_build(quick_build),
                ),
                args.format,
            )
            return int(quick_build.exit_code)

        if args.skip_full_build:
            emit_result(
                command_result(
                    COMMAND_NAME,
                    status="quick_checked",
                    exit_code=ExitCode.SUCCESS,
                    workspace=workspace,
                    paper_id_with_version=fetch_result.paper_id_with_version,
                    source_url=fetch_result.source_url,
                    notes_enabled="on" if setup_result.notes_enabled else "off",
                    quick_build=summarize_build(quick_build),
                ),
                args.format,
            )
            return int(ExitCode.SUCCESS)

        full_build = build_workspace(
            workspace,
            tex=setup_result.entry_path.name,
            quick=False,
            refresh_entry=False,
            skip_lint=True,
        )
        if full_build.exit_code != int(ExitCode.SUCCESS):
            emit_result(
                command_result(
                    COMMAND_NAME,
                    status="full_build_failed",
                    exit_code=full_build.exit_code,
                    workspace=workspace,
                    paper_id_with_version=fetch_result.paper_id_with_version,
                    source_url=fetch_result.source_url,
                    quick_build=summarize_build(quick_build),
                    full_build=summarize_build(full_build),
                ),
                args.format,
            )
            return int(full_build.exit_code)

        pdf_path = full_build.targets[0].pdf
        if pdf_path is None:
            raise FileNotFoundError("full build finished without a PDF output path")
        visual_result = run_visual_check(workspace, pdf_path)
        emit_result(
            command_result(
                COMMAND_NAME,
                status="compiled",
                exit_code=ExitCode.SUCCESS,
                workspace=workspace,
                paper_id_with_version=fetch_result.paper_id_with_version,
                source_url=fetch_result.source_url,
                notes_enabled="on" if setup_result.notes_enabled else "off",
                pdf=pdf_path,
                preview_dir=visual_result.preview_dir,
                visual_check_status=visual_result.status,
                visual_check_note=visual_result.note,
                quick_build=summarize_build(quick_build),
                full_build=summarize_build(full_build),
            ),
            args.format,
        )
        return int(ExitCode.SUCCESS)
    except RuntimeError as exc:
        emit_result(
            error_result(
                COMMAND_NAME,
                exit_code=ExitCode.DEPENDENCY_MISSING,
                error=str(exc),
            ),
            args.format,
        )
        return int(ExitCode.DEPENDENCY_MISSING)
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
