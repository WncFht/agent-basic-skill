#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


RUNTIME_SOURCE_ID = "repo:WncFht/video-note-pipeline"
WORKSPACE_SOURCE_ID = "workspace:video-notes"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve video-note runtime repo and workspace paths.")
    parser.add_argument("--runtime-repo", help="Explicit runtime repository root.")
    parser.add_argument("--workspace-root", help="Explicit case workspace root.")
    parser.add_argument("--override-file", help="Optional local source override JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--print",
        dest="print_field",
        choices=("runtime_repo", "workspace_root"),
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


def resolve_existing_dir(raw: str | None, markers: list[str] | None = None) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        return None
    if markers and not all((path / marker).exists() for marker in markers):
        return None
    return path


def resolve_value(
    explicit: str | None,
    env_var: str,
    override_key: str,
    overrides: dict[str, str],
    default_candidates: list[str],
    markers: list[str] | None = None,
) -> tuple[Path | None, str]:
    path = resolve_existing_dir(explicit, markers)
    if path is not None:
        return path, "explicit"
    path = resolve_existing_dir(os.environ.get(env_var), markers)
    if path is not None:
        return path, f"env:{env_var}"
    path = resolve_existing_dir(overrides.get(override_key), markers)
    if path is not None:
        return path, "local-override"
    for candidate in default_candidates:
        path = resolve_existing_dir(candidate, markers)
        if path is not None:
            return path, "default-candidate"
    return None, ""


def emit_error(override_path: Path) -> int:
    message = [
        "无法定位 video-note runtime repo 或 case workspace。",
        "请使用以下任一方式补齐：",
        "1. 传入 --runtime-repo 和 --workspace-root",
        "2. 设置 VIDEO_NOTE_PIPELINE_REPO 和 VIDEO_NOTE_WORKSPACE_ROOT",
        f"3. 在 {override_path} 中配置 {RUNTIME_SOURCE_ID} 与 {WORKSPACE_SOURCE_ID}",
        "4. 将 runtime repo 放到 $HOME/Desktop/src/video-note-pipeline，workspace 放到 $HOME/Desktop/src/video_notes",
    ]
    print("\n".join(message), file=sys.stderr)
    return 1


def main() -> int:
    args = parse_args()
    override_path = Path(args.override_file).expanduser() if args.override_file else default_override_file()
    overrides = load_overrides(override_path)

    runtime_repo, runtime_resolution = resolve_value(
        explicit=args.runtime_repo,
        env_var="VIDEO_NOTE_PIPELINE_REPO",
        override_key=RUNTIME_SOURCE_ID,
        overrides=overrides,
        default_candidates=[
            str(Path.home() / "Desktop" / "src" / "video-note-pipeline"),
            str(Path.home() / "Desktop" / "src" / "video_note_pipeline"),
        ],
        markers=["pyproject.toml"],
    )
    workspace_root, workspace_resolution = resolve_value(
        explicit=args.workspace_root,
        env_var="VIDEO_NOTE_WORKSPACE_ROOT",
        override_key=WORKSPACE_SOURCE_ID,
        overrides=overrides,
        default_candidates=[
            str(Path.home() / "Desktop" / "src" / "video_notes"),
            str(Path.home() / "Desktop" / "src" / "video-notes"),
        ],
        markers=None,
    )

    if runtime_repo is None or workspace_root is None:
        return emit_error(override_path)

    payload = {
        "runtime_repo": str(runtime_repo),
        "workspace_root": str(workspace_root),
        "resolution": {
            "runtime_repo": runtime_resolution,
            "workspace_root": workspace_resolution,
        },
        "override_file": str(override_path),
    }
    if args.print_field:
        print(payload[args.print_field])
        return 0
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(str(runtime_repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
