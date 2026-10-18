from __future__ import annotations

import argparse

from core.arxiv import fetch_source_to_workspace
from core.entry import parse_toggle
from core.models import ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.workspace import DEFAULT_PAPER_ROOT, resolve_directory

COMMAND_NAME = "fetch"
COMMAND_DESCRIPTION = "Download arXiv source tarball and initialize a paper workspace."


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
        "--keep-archive",
        action="store_true",
        help="Keep source.tar in the workspace after extraction.",
    )
    parser.add_argument(
        "--clean-source",
        choices=("on", "off"),
        default="on",
        help="Whether to normalize LaTeX sources after extraction.",
    )
    add_format_argument(parser)


def run_from_args(args: argparse.Namespace) -> int:
    try:
        root = resolve_directory(args.root, label="root", create=True)
        result = fetch_source_to_workspace(
            args.input,
            root=root,
            version=args.version,
            keep_archive=args.keep_archive,
            clean_source=parse_toggle(args.clean_source, label="clean-source"),
        )
        emit_result(
            command_result(
                COMMAND_NAME,
                status="extracted",
                exit_code=ExitCode.SUCCESS,
                workspace=result.workspace,
                arxiv_id=result.arxiv_id,
                paper_id_with_version=result.paper_id_with_version,
                title=result.title,
                source_url=result.source_url,
                archive_path=result.archive_path,
                preprocessed_tex_files=result.preprocessed_tex_files,
                removed_comment_lines=result.removed_comment_lines,
                collapsed_blank_lines=result.collapsed_blank_lines,
                binhex_status=result.binhex_status,
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
