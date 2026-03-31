#!/usr/bin/env python3
"""
Manage frontend style packs for the frontend-style-mimic skill.

Supported commands:
  - list
  - init
  - lint
  - fork
"""

from __future__ import annotations

import argparse
import shutil
import re
import sys
from datetime import date
from pathlib import Path


REQUIRED_FILES = [
    "summary.md",
    "evidence.md",
    "tokens.md",
    "components.md",
    "layout.md",
    "motion.md",
    "implementation.md",
    "anti-patterns.md",
    "checklist.md",
    "examples.md",
]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def styles_root() -> Path:
    return skill_root() / "references" / "styles"


def template_root() -> Path:
    return skill_root() / "assets" / "style-pack-template"


def normalize_style_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    if not normalized:
        raise ValueError("style-id cannot be empty after normalization")
    return normalized


def render_template(text: str, style_id: str, title: str) -> str:
    return (
        text.replace("{{style_id}}", style_id)
        .replace("{{title}}", title)
        .replace("{{date}}", date.today().isoformat())
    )


def list_packs() -> int:
    root = styles_root()
    root.mkdir(parents=True, exist_ok=True)
    packs = sorted(path for path in root.iterdir() if path.is_dir())
    if not packs:
        print("No style packs found.")
        return 0

    for pack in packs:
        summary = pack / "summary.md"
        status = "ready" if summary.exists() else "missing-summary"
        print(f"{pack.name}\t{status}")
    return 0


def init_pack(style_id_raw: str, title: str, overwrite: bool) -> int:
    style_id = normalize_style_id(style_id_raw)
    destination = styles_root() / style_id
    destination.mkdir(parents=True, exist_ok=True)

    template_dir = template_root()
    template_files = sorted(path for path in template_dir.iterdir() if path.is_file())
    if not template_files:
        print(f"Template directory is empty: {template_dir}", file=sys.stderr)
        return 1

    created = []
    skipped = []
    for template_file in template_files:
        target = destination / template_file.name
        if target.exists() and not overwrite:
            skipped.append(target.name)
            continue
        rendered = render_template(template_file.read_text(), style_id=style_id, title=title)
        target.write_text(rendered)
        created.append(target.name)

    print(f"Initialized style pack: {destination}")
    if created:
        print("Created:")
        for name in created:
            print(f"  - {name}")
    if skipped:
        print("Skipped existing files:")
        for name in skipped:
            print(f"  - {name}")
    return 0


def lint_pack(style_id_raw: str) -> int:
    style_id = normalize_style_id(style_id_raw)
    pack_dir = styles_root() / style_id
    if not pack_dir.exists():
        print(f"Style pack not found: {pack_dir}", file=sys.stderr)
        return 1

    missing = []
    placeholders = []
    todos = []

    for filename in REQUIRED_FILES:
        path = pack_dir / filename
        if not path.exists():
            missing.append(filename)
            continue
        text = path.read_text()
        if "{{" in text or "}}" in text:
            placeholders.append(filename)
        if "TODO" in text:
            todos.append(filename)

    ok = True
    if missing:
        ok = False
        print("Missing files:")
        for name in missing:
            print(f"  - {name}")

    if placeholders:
        ok = False
        print("Unresolved placeholders:")
        for name in placeholders:
            print(f"  - {name}")

    if todos:
        ok = False
        print("TODO markers still present:")
        for name in todos:
            print(f"  - {name}")

    if ok:
        print(f"Style pack '{style_id}' passed structural lint.")
        return 0

    return 1


def fork_pack(from_style_raw: str, to_style_raw: str, title: str, overwrite: bool) -> int:
    from_style = normalize_style_id(from_style_raw)
    to_style = normalize_style_id(to_style_raw)

    source_dir = styles_root() / from_style
    if not source_dir.exists():
        print(f"Parent style pack not found: {source_dir}", file=sys.stderr)
        return 1

    destination_dir = styles_root() / to_style
    if destination_dir.exists() and any(destination_dir.iterdir()) and not overwrite:
        print(
            f"Destination style pack already exists and is not empty: {destination_dir}\n"
            "Use --overwrite to replace files.",
            file=sys.stderr,
        )
        return 1

    destination_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for filename in REQUIRED_FILES:
        source = source_dir / filename
        if not source.exists():
            continue
        target = destination_dir / filename
        if target.exists() and overwrite:
            target.unlink()
        shutil.copy2(source, target)
        copied.append(filename)

    summary_path = destination_dir / "summary.md"
    if summary_path.exists():
        text = summary_path.read_text()
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {title}"
        text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        text = re.sub(r"Style ID: `[^`]+`", f"Style ID: `{to_style}`", text)
        text = re.sub(r"Status: `[^`]+`", "Status: `draft-variant`", text)
        if "- Parent style id:" in text:
            text = re.sub(r"- Parent style id:.*", f"- Parent style id: `{from_style}`", text)
        if "- Deliberate changes:" in text:
            text = re.sub(r"- Deliberate changes:.*", "- Deliberate changes: TODO", text)
        summary_path.write_text(text)

    evidence_path = destination_dir / "evidence.md"
    if evidence_path.exists():
        text = evidence_path.read_text()
        text = re.sub(r"Extraction date: `[^`]+`", f"Extraction date: `{date.today().isoformat()}`", text)
        text += f"\n## Variant Origin\n\n- Forked from style pack: `{from_style}`\n"
        evidence_path.write_text(text)

    print(f"Forked style pack: {from_style} -> {to_style}")
    if copied:
        print("Copied:")
        for name in copied:
            print(f"  - {name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage frontend style packs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List known style packs.")

    init_parser = subparsers.add_parser("init", help="Initialize a style pack from the template.")
    init_parser.add_argument("--style-id", required=True, help="Hyphen-case style id.")
    init_parser.add_argument("--title", required=True, help="Human-readable style title.")
    init_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files in the target style pack.",
    )

    lint_parser = subparsers.add_parser("lint", help="Lint a style pack for missing files and placeholders.")
    lint_parser.add_argument("--style-id", required=True, help="Hyphen-case style id.")

    fork_parser = subparsers.add_parser("fork", help="Fork an existing style pack into a variant.")
    fork_parser.add_argument("--from-style", required=True, help="Parent style id.")
    fork_parser.add_argument("--to-style", required=True, help="Child style id.")
    fork_parser.add_argument("--title", required=True, help="Human-readable title for the child style.")
    fork_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite files in the destination style pack.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        return list_packs()
    if args.command == "init":
        return init_pack(args.style_id, args.title, args.overwrite)
    if args.command == "lint":
        return lint_pack(args.style_id)
    if args.command == "fork":
        return fork_pack(args.from_style, args.to_style, args.title, args.overwrite)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
