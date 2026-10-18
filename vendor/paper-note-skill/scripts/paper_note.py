#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Callable

from commands import build, config, doctor, fetch, lint, run, setup, visual_check

COMMAND_DESCRIPTION = (
    "Unified CLI for the paper-note workflow: fetch source, prepare the workspace, "
    "lint annotations, build the bilingual PDF, run visual checks, or execute the full pipeline."
)

SubcommandHandler = Callable[[argparse.Namespace], int]


def register_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    name: str,
    description: str,
    configure: Callable[[argparse.ArgumentParser], None],
    handler: SubcommandHandler,
) -> None:
    parser = subparsers.add_parser(name, help=description, description=description)
    configure(parser)
    parser.set_defaults(handler=handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-note", description=COMMAND_DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_subcommand(
        subparsers,
        name=config.COMMAND_NAME,
        description=config.COMMAND_DESCRIPTION,
        configure=config.configure_parser,
        handler=config.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=fetch.COMMAND_NAME,
        description=fetch.COMMAND_DESCRIPTION,
        configure=fetch.configure_parser,
        handler=fetch.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=setup.COMMAND_NAME,
        description=setup.COMMAND_DESCRIPTION,
        configure=setup.configure_parser,
        handler=setup.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=lint.COMMAND_NAME,
        description=lint.COMMAND_DESCRIPTION,
        configure=lint.configure_parser,
        handler=lint.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=build.COMMAND_NAME,
        description=build.COMMAND_DESCRIPTION,
        configure=build.configure_parser,
        handler=build.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=visual_check.COMMAND_NAME,
        description=visual_check.COMMAND_DESCRIPTION,
        configure=visual_check.configure_parser,
        handler=visual_check.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=run.COMMAND_NAME,
        description=run.COMMAND_DESCRIPTION,
        configure=run.configure_parser,
        handler=run.run_from_args,
    )
    register_subcommand(
        subparsers,
        name=doctor.COMMAND_NAME,
        description=doctor.COMMAND_DESCRIPTION,
        configure=doctor.configure_parser,
        handler=doctor.run_from_args,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
