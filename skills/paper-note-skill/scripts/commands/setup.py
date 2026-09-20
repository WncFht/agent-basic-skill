from __future__ import annotations

import argparse

from core.entry import generated_entry_files, parse_toggle, prepare_workspace
from core.models import ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.workspace import (
    PREAMBLE_FILE_NAME,
    resolve_existing_directory,
    resolve_workspace_file,
)

COMMAND_NAME = "setup"
COMMAND_DESCRIPTION = (
    "Generate the bilingual entry file and shared LaTeX annotation assets."
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workspace", help="Paper workspace directory.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated paper-note files if they already exist.",
    )
    parser.add_argument(
        "--notes",
        choices=("on", "off"),
        default="on",
        help="Whether the generated entry enables function-block pnotes.",
    )
    parser.add_argument(
        "--main",
        help="Explicit top-level TeX file inside the workspace.",
    )
    add_format_argument(parser)


def run_from_args(args: argparse.Namespace) -> int:
    try:
        workspace = resolve_existing_directory(args.workspace, label="workspace")
        main_tex = (
            resolve_workspace_file(workspace, args.main, label="main tex")
            if args.main
            else None
        )
        result = prepare_workspace(
            workspace,
            force=args.force,
            notes_enabled=parse_toggle(args.notes, label="notes"),
            main_tex=main_tex,
        )
        emit_result(
            command_result(
                COMMAND_NAME,
                status="prepared",
                exit_code=ExitCode.SUCCESS,
                workspace=result.workspace,
                main_tex=result.main_tex,
                annotation_support=PREAMBLE_FILE_NAME,
                entry_files=list(generated_entry_files()),
                paired_translation_macros=(
                    r"\zhbgsent \zhgapsent \zhquestionsent "
                    r"\zhmethodsent \zhresultsent \zhclaimsent "
                    r"\zhstructsent \zhrelatedsent \zhkeysent"
                ),
                fallback_translation_macro=(
                    r"\zhtrans{...} (only for non-sentence or non-functional translated text)"
                ),
                notes_enabled="on" if result.notes_enabled else "off",
                notes_toggle=(
                    r"change \annotnotestrue / \annotnotesfalse in the entry file if needed"
                ),
                removed_generated_paths=result.removed_generated_paths,
                entry_path=result.entry_path,
                preamble_path=result.preamble_path,
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
