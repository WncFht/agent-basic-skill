#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SOURCE_KEYS = ("repo:WncFht/BiliNote/backend", "repo:WncFht/BiliNote")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve local BiliNote repository paths.")
    parser.add_argument("--repo-root", help="Explicit BiliNote repository root.")
    parser.add_argument("--backend-root", help="Explicit BiliNote backend root.")
    parser.add_argument("--override-file", help="Optional local source override JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--print",
        dest="print_field",
        choices=("repo_root", "backend_root"),
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


def normalize_paths(path: Path) -> tuple[Path, Path] | None:
    path = path.expanduser().resolve()
    if path.name == "backend" and (path / "pyproject.toml").exists():
        return path.parent, path
    backend_root = path / "backend"
    if backend_root.is_dir() and (backend_root / "pyproject.toml").exists():
        return path, backend_root
    return None


def resolve_from_override(overrides: dict[str, str]) -> tuple[Path, Path] | None:
    for key in SOURCE_KEYS:
        raw = overrides.get(key)
        if not raw:
            continue
        resolved = normalize_paths(Path(raw))
        if resolved is not None:
            return resolved
    return None


def resolve_default_candidates() -> tuple[Path, Path] | None:
    home = Path.home()
    candidates = [
        home / "Desktop" / "src" / "BiliNote" / "backend",
        home / "Desktop" / "src" / "BiliNote",
    ]
    for candidate in candidates:
        resolved = normalize_paths(candidate)
        if resolved is not None:
            return resolved
    return None


def emit_error(override_path: Path) -> int:
    message = [
        "无法定位外部 BiliNote 仓。",
        "可选做法：",
        "1. 传入 --backend-root 或 --repo-root",
        "2. 设置 BILINOTE_BACKEND_ROOT 或 BILINOTE_REPO",
        f"3. 在 {override_path} 中为 {SOURCE_KEYS[-1]} 配置本地路径",
        "4. 将仓库放到 $HOME/Desktop/src/BiliNote",
    ]
    print("\n".join(message), file=sys.stderr)
    return 1


def main() -> int:
    args = parse_args()
    override_path = Path(args.override_file).expanduser() if args.override_file else default_override_file()
    overrides = load_overrides(override_path)

    resolved: tuple[Path, Path] | None = None
    resolution = ""

    if args.backend_root:
        resolved = normalize_paths(Path(args.backend_root))
        resolution = "explicit-backend-root"
    if resolved is None and args.repo_root:
        resolved = normalize_paths(Path(args.repo_root))
        resolution = "explicit-repo-root"
    if resolved is None and os.environ.get("BILINOTE_BACKEND_ROOT"):
        resolved = normalize_paths(Path(os.environ["BILINOTE_BACKEND_ROOT"]))
        resolution = "env:BILINOTE_BACKEND_ROOT"
    if resolved is None and os.environ.get("BILINOTE_REPO"):
        resolved = normalize_paths(Path(os.environ["BILINOTE_REPO"]))
        resolution = "env:BILINOTE_REPO"
    if resolved is None:
        resolved = resolve_from_override(overrides)
        if resolved is not None:
            resolution = "local-override"
    if resolved is None:
        resolved = resolve_default_candidates()
        if resolved is not None:
            resolution = "default-candidate"

    if resolved is None:
        return emit_error(override_path)

    repo_root, backend_root = resolved
    payload = {
        "source_id": SOURCE_KEYS[-1],
        "repo_root": str(repo_root),
        "backend_root": str(backend_root),
        "resolution": resolution,
        "override_file": str(override_path),
    }
    if args.print_field:
        print(payload[args.print_field])
        return 0
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(str(backend_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
