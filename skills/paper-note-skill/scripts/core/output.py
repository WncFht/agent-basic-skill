from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import IntEnum
from pathlib import Path

from core.models import CommandResult, ExitCode


def add_format_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )


def command_result(
    command: str,
    *,
    status: str,
    exit_code: int | ExitCode,
    **fields: object,
) -> CommandResult:
    return CommandResult(
        command=command,
        status=status,
        exit_code=int(exit_code),
        fields=fields,
    )


def error_result(
    command: str,
    *,
    exit_code: int | ExitCode,
    error: str,
    status: str = "error",
    **fields: object,
) -> CommandResult:
    return command_result(
        command,
        status=status,
        exit_code=exit_code,
        error=error,
        **fields,
    )


def _to_jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, IntEnum):
        return int(value)
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return value


def _format_scalar(value: object) -> str:
    normalized = _to_jsonable(value)
    if normalized is None:
        return "none"
    if isinstance(normalized, bool):
        return "true" if normalized else "false"
    if isinstance(normalized, (str, int, float)):
        return str(normalized)
    return json.dumps(normalized, ensure_ascii=False)


def _emit_text_mapping(mapping: dict[str, object]) -> None:
    for key, value in mapping.items():
        normalized = _to_jsonable(value)
        if isinstance(normalized, list):
            print(f"{key}:")
            if not normalized:
                print("  - none")
                continue
            for item in normalized:
                print(f"  - {_format_scalar(item)}")
            continue
        print(f"{key}: {_format_scalar(normalized)}")


def emit_result(result: CommandResult, output_format: str) -> None:
    payload = {
        "command": result.command,
        "status": result.status,
        "exit_code": result.exit_code,
        **result.fields,
    }
    if output_format == "json":
        print(json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2))
        return
    _emit_text_mapping(payload)
