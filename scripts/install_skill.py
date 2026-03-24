#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"


class InstallError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install skills from this repo into ~/.codex/skills.")
    parser.add_argument("skill_names", nargs="+", help="Skill names under skills/.")
    parser.add_argument("--dest-root", help="Destination skills root. Defaults to $CODEX_HOME/skills.")
    parser.add_argument("--override-file", help="Optional source override JSON.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser.parse_args()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def default_dest_root() -> Path:
    return codex_home() / "skills"


def default_override_file() -> Path:
    raw = os.environ.get(
        "AGENT_BASIC_SKILL_SOURCE_OVERRIDES",
        "~/.codex/state/agent-basic-skill/source-overrides.json",
    )
    return Path(raw).expanduser()


def expand_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return {str(key): str(value) for key, value in payload.get("sources", {}).items()}


def load_external_repos(skill_dir: Path) -> list[dict[str, Any]]:
    manifest_path = skill_dir / "external-repos.json"
    if not manifest_path.exists():
        return []
    payload = load_json(manifest_path)
    version = payload.get("version")
    repositories = payload.get("repositories")
    if version != 1 or not isinstance(repositories, list):
        raise InstallError(f"Invalid external repo manifest: {manifest_path}")
    return repositories


def markers_ok(path: Path, markers: list[str]) -> bool:
    return all((path / marker).exists() for marker in markers)


def inspect_candidate(path: Path, markers: list[str]) -> tuple[bool, bool]:
    if not path.exists():
        return False, False
    return True, markers_ok(path, markers)


def resolve_from_candidates(
    candidates: list[tuple[str, Path | None]],
    markers: list[str],
) -> tuple[str | None, Path | None]:
    for source, path in candidates:
        if path is None:
            continue
        exists, valid = inspect_candidate(path, markers)
        if not exists:
            continue
        if valid:
            return source, path
        raise InstallError(
            f"Dependency path exists but does not match markers: {path}"
        )
    return None, None


def git_clone(clone_url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", clone_url, str(dest)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git clone failed"
        raise InstallError(message)


def ensure_dependency(repo_spec: dict[str, Any], overrides: dict[str, str]) -> dict[str, str]:
    markers = [str(value) for value in repo_spec.get("markers", [])]
    if not markers:
        raise InstallError(f"Missing markers for dependency {repo_spec.get('id')}")

    env_var = str(repo_spec["env_var"])
    override_key = str(repo_spec["override_key"])
    default_clone_dir = expand_path(str(repo_spec["default_clone_dir"]))
    default_detect_paths = [
        expand_path(str(raw_path))
        for raw_path in repo_spec.get("default_detect_paths", [])
    ]

    candidates: list[tuple[str, Path | None]] = [
        (f"env:{env_var}", expand_path(os.environ[env_var]) if os.environ.get(env_var) else None),
        ("local-override", expand_path(overrides[override_key]) if overrides.get(override_key) else None),
    ]
    candidates.extend(("default-detect", path) for path in default_detect_paths)

    resolution, existing_path = resolve_from_candidates(candidates, markers)
    if existing_path is not None and resolution is not None:
        return {
            "id": str(repo_spec["id"]),
            "repo": str(repo_spec["repo"]),
            "path": str(existing_path),
            "status": "already_present",
            "resolution": resolution,
        }

    if default_clone_dir.exists() and not markers_ok(default_clone_dir, markers):
        raise InstallError(
            f"Default clone dir exists but is not a valid repo: {default_clone_dir}"
        )

    if not default_clone_dir.exists():
        git_clone(str(repo_spec["clone_url"]), default_clone_dir)

    if not markers_ok(default_clone_dir, markers):
        raise InstallError(f"Cloned repo is missing required markers: {default_clone_dir}")

    return {
        "id": str(repo_spec["id"]),
        "repo": str(repo_spec["repo"]),
        "path": str(default_clone_dir),
        "status": "cloned",
        "resolution": "default-clone-dir",
    }


def replace_tree(src: Path, dest: Path) -> None:
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)


def install_skill(skill_name: str, dest_root: Path, overrides: dict[str, str]) -> dict[str, Any]:
    skill_dir = SKILLS_ROOT / skill_name
    if not skill_dir.is_dir():
        raise InstallError(f"Unknown skill: {skill_name}")
    if not (skill_dir / "SKILL.md").exists():
        raise InstallError(f"Missing SKILL.md for skill: {skill_name}")

    dependencies = [
        ensure_dependency(repo_spec, overrides)
        for repo_spec in load_external_repos(skill_dir)
    ]
    destination = dest_root / skill_name
    replace_tree(skill_dir, destination)
    return {
        "skill": skill_name,
        "installed_to": str(destination),
        "dependencies": dependencies,
    }


def main() -> int:
    args = parse_args()
    dest_root = expand_path(args.dest_root) if args.dest_root else default_dest_root().resolve()
    override_path = expand_path(args.override_file) if args.override_file else default_override_file().resolve()
    overrides = load_overrides(override_path)

    try:
        results = [install_skill(skill_name, dest_root, overrides) for skill_name in args.skill_names]
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "dest_root": str(dest_root),
            "override_file": str(override_path),
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for result in results:
        print(f"installed {result['skill']} -> {result['installed_to']}")
        for dependency in result["dependencies"]:
            print(
                f"  dependency {dependency['repo']}: {dependency['status']} "
                f"({dependency['resolution']}) -> {dependency['path']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
