from __future__ import annotations

import argparse

from core.lint_rules import format_issue, lint_workspace
from core.models import ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.workspace import resolve_existing_directory, resolve_workspace_file

COMMAND_NAME = "lint"
COMMAND_DESCRIPTION = "Lint paper-note annotation rules before compiling the workspace."


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workspace", help="Paper workspace directory.")
    parser.add_argument(
        "--tex",
        help="Lint a specific TeX file instead of scanning the whole workspace.",
    )
    add_format_argument(parser)


def run_from_args(args: argparse.Namespace) -> int:
    try:
        workspace = resolve_existing_directory(args.workspace, label="workspace")
        tex_file = (
            resolve_workspace_file(workspace, args.tex, label="tex")
            if args.tex
            else None
        )
        result = lint_workspace(workspace, tex_file=tex_file)
        has_issues = bool(result.issues)
        emit_result(
            command_result(
                COMMAND_NAME,
                status="failed" if has_issues else "clean",
                exit_code=ExitCode.LINT_FAILED if has_issues else ExitCode.SUCCESS,
                workspace=workspace,
                checked_files=[
                    path.relative_to(workspace).as_posix()
                    for path in result.checked_files
                ],
                issue_count=len(result.issues),
                issues=[format_issue(issue, workspace) for issue in result.issues],
            ),
            args.format,
        )
        return int(ExitCode.LINT_FAILED if has_issues else ExitCode.SUCCESS)
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
