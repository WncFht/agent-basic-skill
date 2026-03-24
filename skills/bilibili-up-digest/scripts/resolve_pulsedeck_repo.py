#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SOURCE_ID = "repo:WncFht/PulseDeck"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve PulseDeck repository and runtime paths.")
    parser.add_argument("--repo-root", help="Explicit PulseDeck repository root.")
    parser.add_argument("--vault-root", help="Explicit Obsidian bilibili vault root.")
    parser.add_argument("--config", help="Explicit digest config path.")
    parser.add_argument("--override-file", help="Optional local source override JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--print",
        dest="print_field",
        choices=("repo_root", "vault_root", "config"),
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
    return path


def main() -> int:
    args = parse_args()
    override_path = Path(args.override_file).expanduser() if args.override_file else default_override_file()
    overrides = load_overrides(override_path)

    repo_root = (
        resolve_repo_path(args.repo_root)
        or resolve_repo_path(os.environ.get("BILIBILI_UP_DIGEST_REPO"))
        or resolve_repo_path(overrides.get(SOURCE_ID))
        or resolve_repo_path(str(Path.home() / "Desktop" / "src" / "PulseDeck"))
        or resolve_repo_path(str(Path.home() / "Desktop" / "src" / "pulsedeck"))
    )

    if repo_root is None:
        message = [
            "无法定位外部 PulseDeck 仓。",
            "可选做法：",
            "1. 传入 --repo-root",
            "2. 设置 BILIBILI_UP_DIGEST_REPO",
            f"3. 在 {override_path} 中配置 {SOURCE_ID}",
            "4. 将仓库放到 $HOME/Desktop/src/PulseDeck",
        ]
        print("\n".join(message), file=sys.stderr)
        return 1

    vault_root = Path(
        args.vault_root
        or os.environ.get("BILIBILI_DIGEST_VAULT_ROOT")
        or "~/Desktop/obsidian/bilibili"
    ).expanduser().resolve()
    config = Path(
        args.config
        or os.environ.get("BILIBILI_DIGEST_CONFIG")
        or (vault_root / "配置" / "关注UP.yaml")
    ).expanduser().resolve()

    payload = {
        "source_id": SOURCE_ID,
        "repo_root": str(repo_root),
        "vault_root": str(vault_root),
        "config": str(config),
        "vault_root_exists": vault_root.exists(),
        "config_exists": config.exists(),
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
