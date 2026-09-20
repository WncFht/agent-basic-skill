from __future__ import annotations

import argparse
from pathlib import Path

from core.models import ExitCode
from core.output import add_format_argument, command_result, emit_result, error_result
from core.user_config import (
    OUTPUT_ROOT_ENV_VAR,
    PaperNoteConfig,
    config_path,
    load_config,
    normalize_output_root,
    resolve_output_root,
    save_config,
)
from core.workspace import DEFAULT_PAPER_ROOT_FALLBACK, REPO_ROOT

COMMAND_NAME = "config"
COMMAND_DESCRIPTION = "Show or configure the default paper workspace root."


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show the resolved default output root and config source.",
    )
    parser.add_argument(
        "--set-root",
        help="Persist a new default output root into ~/.paper-note-skill/config.yaml.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the saved output root from ~/.paper-note-skill/config.yaml.",
    )
    add_format_argument(parser)


def resolved_payload() -> dict[str, object]:
    resolved = resolve_output_root(
        repo_root=REPO_ROOT,
        fallback_root=DEFAULT_PAPER_ROOT_FALLBACK,
    )
    stored = load_config()
    return {
        "resolved_output_root": resolved.root,
        "resolved_source": resolved.source,
        "env_var": OUTPUT_ROOT_ENV_VAR,
        "config_path": resolved.config_path,
        "configured_output_root": stored.output_root,
        "fallback_output_root": DEFAULT_PAPER_ROOT_FALLBACK,
    }


def normalize_and_prepare_root(raw_path: str) -> Path:
    root = normalize_output_root(raw_path, repo_root=REPO_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_show(args: argparse.Namespace) -> int:
    emit_result(
        command_result(
            COMMAND_NAME,
            status="ok",
            exit_code=ExitCode.SUCCESS,
            **resolved_payload(),
        ),
        args.format,
    )
    return int(ExitCode.SUCCESS)


def run_set_root(args: argparse.Namespace, raw_path: str) -> int:
    root = normalize_and_prepare_root(raw_path)
    target = save_config(PaperNoteConfig(output_root=str(root)))
    emit_result(
        command_result(
            COMMAND_NAME,
            status="saved",
            exit_code=ExitCode.SUCCESS,
            output_root=root,
            config_path=target,
            resolved_source="config",
            env_var=OUTPUT_ROOT_ENV_VAR,
        ),
        args.format,
    )
    return int(ExitCode.SUCCESS)


def run_clear(args: argparse.Namespace) -> int:
    target = save_config(PaperNoteConfig())
    payload = resolved_payload()
    emit_result(
        command_result(
            COMMAND_NAME,
            status="cleared",
            exit_code=ExitCode.SUCCESS,
            config_path=target,
            **payload,
        ),
        args.format,
    )
    return int(ExitCode.SUCCESS)


def run_interactive(args: argparse.Namespace) -> int:
    payload = resolved_payload()
    configured_output_root = payload["configured_output_root"]
    resolved_root = payload["resolved_output_root"]
    resolved_source = payload["resolved_source"]
    config_file = payload["config_path"]

    if configured_output_root:
        print(f"Current configured output root: {configured_output_root}")
        print(f"Config path: {config_file}")
        raw_path = input("Enter new output root (or press Enter to keep current): ")
    else:
        print(f"Current resolved output root: {resolved_root}")
        print(f"Current source: {resolved_source}")
        print(f"Config path: {config_file}")
        raw_path = input("Enter output root to save (or press Enter to keep current): ")

    raw_path = raw_path.strip()
    if not raw_path:
        emit_result(
            command_result(
                COMMAND_NAME,
                status="unchanged",
                exit_code=ExitCode.SUCCESS,
                **payload,
            ),
            args.format,
        )
        return int(ExitCode.SUCCESS)

    return run_set_root(args, raw_path)


def run_from_args(args: argparse.Namespace) -> int:
    try:
        if args.show:
            return run_show(args)
        if args.set_root:
            return run_set_root(args, args.set_root)
        if args.clear:
            return run_clear(args)
        return run_interactive(args)
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
