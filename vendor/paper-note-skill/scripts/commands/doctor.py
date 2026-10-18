from __future__ import annotations

import argparse

from core.doctor import run_doctor
from core.models import ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.workspace import resolve_existing_directory

COMMAND_NAME = "doctor"
COMMAND_DESCRIPTION = (
    "Check local paper-note dependencies and optional workspace readiness."
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        help="Optional workspace to validate.",
    )
    add_format_argument(parser)


def run_from_args(args: argparse.Namespace) -> int:
    try:
        workspace = (
            resolve_existing_directory(args.workspace, label="workspace")
            if args.workspace
            else None
        )
        result = run_doctor(workspace)
        missing_dependencies = [
            check.name
            for check in (*result.tools, *result.python_modules)
            if not check.found
        ]
        if workspace is not None and result.workspace_status == "invalid":
            status = "workspace_invalid"
            exit_code = ExitCode.INPUT_ERROR
        elif missing_dependencies:
            status = "missing_dependency"
            exit_code = ExitCode.DEPENDENCY_MISSING
        else:
            status = "ok"
            exit_code = ExitCode.SUCCESS

        emit_result(
            command_result(
                COMMAND_NAME,
                status=status,
                exit_code=exit_code,
                workspace=workspace,
                tools=result.tools,
                python_modules=result.python_modules,
                workspace_status=result.workspace_status,
                missing_dependencies=missing_dependencies,
                notes=list(result.notes),
            ),
            args.format,
        )
        return int(exit_code)
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
