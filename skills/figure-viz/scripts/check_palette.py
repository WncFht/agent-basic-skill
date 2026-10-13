#!/usr/bin/env python3
"""check_palette.py — 校验 assets/tikz/vizstyle.tex 与 assets/mpl/fvstyle.py 的调色板一致。

vizstyle.tex 的 \\definecolor{vNAME}{HTML}{HEX} 必须等于 fvstyle.py 的
HUES + NEUTRALS（后者多出的 paper/baseline 语义别名豁免）。两边都是手工
维护的 hex，这个脚本防漂移。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEX = SKILL_DIR / "assets" / "tikz" / "vizstyle.tex"
PY = SKILL_DIR / "assets" / "mpl" / "fvstyle.py"

# fvstyle 里有语义别名/纯背景色，不强制出现在 tex 侧
PY_ONLY_OK = {"paper", "baseline"}


def tex_palette() -> dict[str, str]:
    out = {}
    for m in re.finditer(
        r"\\definecolor\{(v\w+)\}\{HTML\}\{([0-9A-Fa-f]{6})\}", TEX.read_text()
    ):
        out[m.group(1)] = "#" + m.group(2).upper()
    return out


def py_palette() -> dict[str, str]:
    """ast 提取 HUES/NEUTRALS 字典字面量——不 import，避免依赖 matplotlib。"""
    tree = ast.parse(PY.read_text())
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id in ("HUES", "NEUTRALS")
            for t in node.targets
        ):
            continue
        d = ast.literal_eval(node.value)
        out.update(d)
    return {k: v.upper() for k, v in out.items()}


def main() -> int:
    tex, py = tex_palette(), py_palette()
    problems = []
    for name, hexv in tex.items():
        if name not in py:
            problems.append(f"{name}: tex-only {hexv}")
        elif py[name] != hexv:
            problems.append(f"{name}: tex={hexv} py={py[name]}")
    for name, hexv in py.items():
        short = name.lstrip("v")  # vink->ink 等语义别名宽容
        if name not in tex and name not in PY_ONLY_OK and short not in PY_ONLY_OK:
            problems.append(f"{name}: py-only {hexv}")
    for p in problems:
        print("PALETTE", p)
    if problems:
        return 1
    print(f"ok: {len(tex)} colors match between vizstyle.tex and fvstyle.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
