#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SOURCE_ID = "repo:WncFht/shuiyuan_exporter"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve shuiyuan_exporter repository paths.")
    parser.add_argument("--repo-root", help="Explicit shuiyuan_exporter repository root.")
    parser.add_argument("--cache-root", help="Explicit runtime cache root.")
    parser.add_argument("--override-file", help="Optional local source override JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--print",
        dest="print_field",
        choices=("repo_root", "cache_root"),
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


def resolve_repo_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        return None
    if not (path / "pyproject.toml").exists():
        return None
    return path


def main() -> int:
    args = parse_args()
    override_path = Path(args.override_file).expanduser() if args.override_file else default_override_file()
    overrides = load_overrides(override_path)

    repo_root = (
        resolve_repo_path(args.repo_root)
        or resolve_repo_path(os.environ.get("SHUIYUAN_EXPORTER_REPO"))
        or resolve_repo_path(overrides.get(SOURCE_ID))
        or resolve_repo_path(str(Path.home() / "Desktop" / "src" / "shuiyuan_exporter"))
    )

    if repo_root is None:
        message = [
            "无法定位外部 shuiyuan_exporter 仓。",
            "可选做法：",
            "1. 传入 --repo-root",
            "2. 设置 SHUIYUAN_EXPORTER_REPO",
            f"3. 在 {override_path} 中配置 {SOURCE_ID}",
            "4. 将仓库放到 $HOME/Desktop/src/shuiyuan_exporter",
        ]
        print("\n".join(message), file=sys.stderr)
        return 1

    cache_root = Path(
        args.cache_root
        or os.environ.get("SHUIYUAN_CACHE_ROOT")
        or "~/.local/share/shuiyuan-cache-skill"
    ).expanduser().resolve()

    payload = {
        "source_id": SOURCE_ID,
        "repo_root": str(repo_root),
        "cache_root": str(cache_root),
        "override_file": str(override_path),
    }
    if args.print_field:
        print(payload[args.print_field])
        return 0
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(str(repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
