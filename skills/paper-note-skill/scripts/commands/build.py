from __future__ import annotations

import argparse

from core.build_exec import build_workspace
from core.lint_rules import format_issue
from core.models import BuildTargetResult, ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.workspace import relative_to_workspace, resolve_existing_directory

COMMAND_NAME = "build"
COMMAND_DESCRIPTION = (
    "Compile the bilingual paper-note TeX entry and summarize diagnostics."
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workspace", help="Paper workspace directory.")
    parser.add_argument(
        "--tex",
        help="Explicit TeX file to compile. Defaults to the generated bilingual entry or detected main file.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Only run the preflight LaTeX pass.",
    )
    parser.add_argument(
        "--refresh-entry",
        action="store_true",
        help="Regenerate paper_note_bilingual.tex from the detected main TeX file before building.",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip the lint phase before compiling.",
    )
    add_format_argument(parser)


def target_payload(workspace, target: BuildTargetResult) -> dict[str, object]:
    return {
        "tex": relative_to_workspace(workspace, target.tex),
        "pdf": relative_to_workspace(workspace, target.pdf) if target.pdf else None,
        "log": relative_to_workspace(workspace, target.log),
        "compiler": target.compiler,
        "mode": target.mode,
        "has_bibtex": target.has_bibtex,
        "binhex_status": target.binhex_status,
        "removed_stale_aux": [
            relative_to_workspace(workspace, path) for path in target.removed_stale_aux
        ],
        "warnings": list(target.warnings),
        "fatal": target.fatal,
        "status": target.status,
    }


def run_from_args(args: argparse.Namespace) -> int:
    try:
        workspace = resolve_existing_directory(args.workspace, label="workspace")
        result = build_workspace(
            workspace,
            tex=args.tex,
            quick=args.quick,
            refresh_entry=args.refresh_entry,
            skip_lint=args.skip_lint,
        )
        lint_issues = []
        if result.lint_result is not None:
            lint_issues = [
                format_issue(issue, workspace) for issue in result.lint_result.issues
            ]
        emit_result(
            command_result(
                COMMAND_NAME,
                status=result.status,
                exit_code=result.exit_code,
                workspace=workspace,
                targets=[
                    relative_to_workspace(workspace, path)
                    for path in result.plan.targets
                ],
                entry_refresh=(
                    f"paper_note_bilingual.tex regenerated from {result.refreshed_entry.main_tex.name} ({result.refresh_reason})"
                    if result.refreshed_entry is not None
                    and result.refresh_reason is not None
                    else "skipped"
                ),
                lint_status=(
                    "skipped"
                    if result.lint_result is None
                    else ("failed" if result.lint_result.issues else "clean")
                ),
                lint_issue_count=len(lint_issues),
                lint_issues=lint_issues,
                results=[
                    target_payload(workspace, target) for target in result.targets
                ],
            ),
            args.format,
        )
        return int(result.exit_code)
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
