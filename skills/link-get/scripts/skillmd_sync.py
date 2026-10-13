#!/usr/bin/env python3
"""skillmd_sync.py — pack manifest → SKILL.md 路由表注入（PLAN §4.6 方向反转）。

pack.toml 是唯一事实源：读 packs/*/pack.toml 的 [pack] name/desc/label 与
[match].hosts，生成 `| URL | 连接器 / 车道 |` 表，替换
<!-- pack-table:start --> / <!-- pack-table:end --> 之间的内容（标记保留）。

用法：
  skillmd_sync.py [SKILL.md ...]   # 缺省 = 本 skill 的 SKILL.md
  skillmd_sync.py --check          # 只校验：漂移 → rc1 + unified diff（pre-commit/CI）
"""

import argparse
import difflib
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "packs"
SKILLMD = ROOT / "SKILL.md"
START = "<!-- pack-table:start -->"
END = "<!-- pack-table:end -->"


def load_rows():
    packs = []
    for ptoml in sorted(PACKS.glob("*/pack.toml")):
        try:
            doc = tomllib.loads(ptoml.read_text(encoding="utf-8"))
        except Exception as e:
            # 与 engine load_packs 同政策：坏 toml 警告跳过——表格缺行会
            # 以 drift 形态被 --check 抓住，不是崩在半路
            sys.stderr.write(f"pack {ptoml}: {e}\n")
            continue
        p = doc.get("pack", {})
        m = doc.get("match", {})
        hosts = m.get("hosts") or ["*"]
        lanes = [ln.get("name", "?") for ln in doc.get("lanes") or []]
        packs.append(
            {
                "name": p.get("name") or ptoml.parent.name,
                "hosts": hosts,
                "desc": p.get("desc", ""),
                "label": p.get("label"),
                "lanes": lanes,
                "catchall": hosts == ["*"],
            }
        )
    # 与 engine 同序：具体 host 先、catch-all 殿后，组内按 name
    packs.sort(key=lambda x: (x["catchall"], x["name"]))
    return packs


def render(packs):
    # prettier-ignore：pre-commit 的 prettier 会 padding 表列，生成物须
    # 以 compact 形态落盘才扛得住 --check（range-ignore 经实测 prettier 3.9 认）
    out = [
        "<!-- prettier-ignore-start -->",
        "",
        "| URL | 连接器 / 车道 |",
        "| --- | --- |",
    ]
    for p in packs:
        if p["catchall"]:
            label = p["label"] or "其他 http(s)"
        else:
            label = "、".join(f"`{h}`" for h in p["hosts"])
        desc = f"：{p['desc']}" if p["desc"] else ""
        # 单车道包显示 connector CLI 名（可直接独调）；多车道包显示 pack 名
        who = p["lanes"][0] if len(p["lanes"]) == 1 else p["name"]
        out.append(f"| {label} | `{who}`{desc} |")
    out += ["", "<!-- prettier-ignore-end -->"]
    return "\n".join(out)


def sync(path, check):
    text = path.read_text(encoding="utf-8")
    # 恰好各一对：find() 只命中首对，第二对会在 --check 绿灯下腐坏
    if (
        text.count(START) != 1
        or text.count(END) != 1
        or text.find(END) <= text.find(START)
    ):
        print(f"{path}: {START}/{END} 标记须恰好各一且序正确", file=sys.stderr)
        return 2
    i, j = text.find(START), text.find(END)
    body = render(load_rows())
    new = text[: i + len(START)] + "\n\n" + body + "\n\n" + text[j:]
    if check:
        if new == text:
            return 0
        diff = difflib.unified_diff(
            text.splitlines(),
            new.splitlines(),
            str(path),
            "generated",
            lineterm="",
        )
        print("\n".join(diff))
        return 1
    if new != text:
        path.write_text(new, encoding="utf-8")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    rc = 0
    for f in args.files or [SKILLMD]:
        rc = max(rc, sync(f, args.check))
    return rc


if __name__ == "__main__":
    sys.exit(main())
