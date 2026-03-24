#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PAPERFLOW_SOURCE_ID = "repo:WncFht/paperflow"
NOTES_SOURCE_ID = "workspace:research-notes"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve paperflow and research-notes paths.")
    parser.add_argument("--paperflow-repo", help="Explicit paperflow repository root.")
    parser.add_argument("--research-notes-root", help="Explicit research-notes root.")
    parser.add_argument("--override-file", help="Optional local source override JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--print",
        dest="print_field",
        choices=("paperflow_repo", "research_notes_root"),
        help="Print a single resolved field.",
    )
    return parser.parse_args()


def default_override_file() -> Path:
    raw = os.environ.get(
        "AGENT_BASIC_SKILL_SOURCE_OVERRIDES",
        "~/.codex/state/agent-basic-skill/source-overrides.json",
    )
    return Path(raw).expanduser()


def load_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return {str(key): str(value) for key, value in payload.get("sources", {}).items()}


def resolve_repo_path(raw: str | None, must_have_pyproject: bool) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        return None
    if must_have_pyproject and not (path / "pyproject.toml").exists():
        return None
    return path


def resolve_default_path(name: str) -> Path:
    return Path.home() / "Desktop" / "src" / name


def resolve_value(
    explicit: str | None,
    env_var: str,
    override_key: str,
    overrides: dict[str, str],
    default_name: str,
    must_have_pyproject: bool,
) -> tuple[Path | None, str]:
    path = resolve_repo_path(explicit, must_have_pyproject)
    if path is not None:
        return path, "explicit"
    path = resolve_repo_path(os.environ.get(env_var), must_have_pyproject)
    if path is not None:
        return path, f"env:{env_var}"
    path = resolve_repo_path(overrides.get(override_key), must_have_pyproject)
    if path is not None:
        return path, "local-override"
    path = resolve_repo_path(str(resolve_default_path(default_name)), must_have_pyproject)
    if path is not None:
        return path, "default-candidate"
    return None, ""


def main() -> int:
    args = parse_args()
    override_path = Path(args.override_file).expanduser() if args.override_file else default_override_file()
    overrides = load_overrides(override_path)

    paperflow_repo, paperflow_resolution = resolve_value(
        explicit=args.paperflow_repo,
        env_var="PAPERFLOW_REPO",
        override_key=PAPERFLOW_SOURCE_ID,
        overrides=overrides,
        default_name="paperflow",
        must_have_pyproject=True,
    )
    research_notes_root, notes_resolution = resolve_value(
        explicit=args.research_notes_root,
        env_var="RESEARCH_NOTES_ROOT",
        override_key=NOTES_SOURCE_ID,
        overrides=overrides,
        default_name="research-notes",
        must_have_pyproject=False,
    )

    if paperflow_repo is None or research_notes_root is None:
        message = [
            "无法定位 paperflow 或 research-notes 路径。",
            "请使用以下任一方式补齐：",
            "1. 传入 --paperflow-repo 和 --research-notes-root",
            "2. 设置 PAPERFLOW_REPO 和 RESEARCH_NOTES_ROOT",
            f"3. 在 {override_path} 中配置 {PAPERFLOW_SOURCE_ID} 与 {NOTES_SOURCE_ID}",
            "4. 将仓库放到 $HOME/Desktop/src/paperflow 和 $HOME/Desktop/src/research-notes",
        ]
        print("\n".join(message), file=sys.stderr)
        return 1

    payload = {
        "paperflow_repo": str(paperflow_repo),
        "research_notes_root": str(research_notes_root),
        "resolution": {
          "paperflow_repo": paperflow_resolution,
          "research_notes_root": notes_resolution
        },
        "override_file": str(override_path),
    }
    if args.print_field:
        print(payload[args.print_field])
        return 0
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(str(paperflow_repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
