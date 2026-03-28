#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil


QUERY_HEADERS = [
    "query_id",
    "objective",
    "platform",
    "search_surface",
    "query_text",
    "recency_days",
    "status",
    "notes",
]

SOURCE_HEADERS = [
    "source_id",
    "platform",
    "source_type",
    "title",
    "canonical_url",
    "author",
    "published_date",
    "accessed_date",
    "entity_candidates",
    "evidence_strength",
    "sensitivity",
    "notes",
]

ENTITY_HEADERS = [
    "entity_id",
    "canonical_name",
    "aliases",
    "entity_type",
    "discovery_sources",
    "official_site_url",
    "dashboard_url",
    "public_base_url",
    "auth_mode",
    "access_gate",
    "claimed_models",
    "observed_models",
    "current_status",
    "status_date",
    "confidence",
    "notes",
]

ACCESS_HEADERS = [
    "observation_id",
    "entity_id",
    "source_id",
    "observation_type",
    "public_base_url",
    "docs_url",
    "credential_observed",
    "credential_kind",
    "credential_visibility",
    "authorized_secret_ref",
    "model_scope",
    "raw_status",
    "last_seen_date",
    "notes",
]

STATUS_HEADERS = [
    "check_id",
    "entity_id",
    "target_kind",
    "target_value",
    "check_method",
    "check_date",
    "result",
    "evidence_url_or_path",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="初始化公开 AI 资源调研 case 目录。"
    )
    parser.add_argument("output_dir", help="要创建的 case 目录。")
    parser.add_argument("--scope", required=True, help="给人看的 case 范围说明。")
    parser.add_argument(
        "--platform",
        action="append",
        default=[],
        help="纳入范围的平台或域名。需要时可重复传入。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的 case 目录。",
    )
    return parser.parse_args()


def ensure_empty_dir(path: Path, force: bool) -> None:
    if path.exists():
        if not force:
            raise SystemExit(f"目标路径已存在，若要覆盖请传 --force：{path}")
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_notes(path: Path, scope: str, platforms: list[str]) -> None:
    platform_line = ", ".join(platforms) if platforms else "web"
    content = f"""# Case 说明

## 范围

- 调研范围：{scope}
- 平台：{platform_line}

## 检查清单

- 先锁定范围、时间线和输出要求。
- 搜索前先写查询矩阵。
- 把来源、实体、接入观察和状态检查分开记录。
- 遇到公开 base URL 时单独记录。
- 不要把第三方 live 凭据粘贴进这个 case。
- 只有在后续用户明确授权时，才使用 `authorized_secret_ref`。
"""
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    ensure_empty_dir(output_dir, args.force)

    manifest = {
        "scope": args.scope,
        "platforms": args.platform,
        "files": {
            "query_matrix": "query-matrix.csv",
            "source_ledger": "source-ledger.csv",
            "entity_ledger": "entity-ledger.csv",
            "access_observations": "access-observations.csv",
            "status_checks": "status-checks.csv",
            "notes": "notes.md",
        },
    }

    write_json(output_dir / "case.json", manifest)
    write_csv(output_dir / "query-matrix.csv", QUERY_HEADERS)
    write_csv(output_dir / "source-ledger.csv", SOURCE_HEADERS)
    write_csv(output_dir / "entity-ledger.csv", ENTITY_HEADERS)
    write_csv(output_dir / "access-observations.csv", ACCESS_HEADERS)
    write_csv(output_dir / "status-checks.csv", STATUS_HEADERS)
    write_notes(output_dir / "notes.md", args.scope, args.platform)

    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
