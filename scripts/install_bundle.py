#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "bundle-manifest.json"


def load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or refresh one or more bundled Codex skills from this repository."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--skill", help="Install or refresh a single skill by name.")
    group.add_argument("--all", action="store_true", help="Install or refresh every bundled skill.")
    parser.add_argument(
        "--dest",
        default="~/.codex/skills",
        help="Destination skills directory. Defaults to ~/.codex/skills.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List resolved skills instead of copying files.",
    )
    return parser.parse_args()


def resolve_targets(manifest: dict, skill_name: str | None) -> list[dict]:
    skills = {item["name"]: item for item in manifest["skills"]}
    if skill_name is None:
        return list(skills.values())
    if skill_name not in skills:
        raise SystemExit(f"Unknown skill '{skill_name}'. Available: {', '.join(sorted(skills))}")
    return [skills[skill_name]]


def validate_required_files(skill: dict) -> None:
    skill_root = REPO_ROOT / skill["path"]
    if not skill_root.is_dir():
        raise SystemExit(f"Missing skill directory: {skill_root}")
    for relative_path in skill["required_files"]:
        if not (skill_root / relative_path).exists():
            raise SystemExit(
                f"Missing required file for {skill['name']}: {skill_root / relative_path}"
            )


def install_skill(skill: dict, destination_root: Path) -> None:
    source_root = REPO_ROOT / skill["path"]
    target_root = destination_root / skill["name"]
    if target_root.exists():
        shutil.rmtree(target_root)
    shutil.copytree(source_root, target_root, copy_function=shutil.copy2)


def main() -> int:
    args = parse_args()
    manifest = load_manifest()
    destination_root = Path(args.dest).expanduser().resolve()
    targets = resolve_targets(manifest, args.skill)

    for skill in targets:
        validate_required_files(skill)

    if args.list:
        for skill in targets:
            print(f"{skill['name']}: {skill['path']}")
        return 0

    destination_root.mkdir(parents=True, exist_ok=True)
    for skill in targets:
        install_skill(skill, destination_root)
        print(f"installed {skill['name']} -> {destination_root / skill['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
