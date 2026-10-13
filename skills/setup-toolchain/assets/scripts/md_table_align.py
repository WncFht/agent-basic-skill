#!/usr/bin/env python3
r"""md_table_align — MD060 "aligned" 表风格重排器。

markdownlint MD060 的 aligned 判定按**显示宽度**（CJK=2，wcwidth 口径）
而非字符数——手工补空格的表在 CJK 内容下几乎必歪。本工具把每个连续
表块（行首可选空白 + `|` 起）的所有行按列重排到统一显示列位：

  - 列分隔只认未转义的 `|`（cell 内 `\|` 不拆列）；
  - 分隔行（`| --- | :---: |`）保留对齐标记，破折号补足列宽；
  - cell 首尾空白归一化为单侧空格（`| cell |`）；
  - 显示宽度用 unicodedata.east_asian_width（W/F=2）+ combining=0，
    与 markdownlint 的 table 列宽口径一致。

用法：python3 scripts/md_table_align.py FILE [FILE ...]（原位改写，
只对真正错位的行产生 diff）。pre-commit 里作原地 fixer 钩——改写了
就 fail 一次、re-add 再交（同 markdownlint --fix 语义）。
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path


def dw(s: str) -> int:
    """Display width: W/F=2, combining/control=0, else 1."""
    w = 0
    for ch in s:
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Cc", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


_SPLIT_RE = re.compile(r"(?<!\\)\|")  # unescaped pipes only


def _is_table_line(line: str) -> bool:
    return bool(re.match(r"^\s*\|", line))


def _is_sep_cell(cell: str) -> bool:
    return bool(re.fullmatch(r":?-{3,}:?", cell.strip()))


def _split_row(line: str) -> list[str] | None:
    """Split a table row into trimmed cells; None if not a well-formed row."""
    body = line.strip()
    if not body.startswith("|"):
        return None
    # leading and trailing pipes are delimiters, not cells
    if body.endswith("\\|"):  # trailing escaped pipe = content, not delimiter
        pass
    elif body.endswith("|"):
        body = body[:-1]
    cells = _SPLIT_RE.split(body[1:])
    return [c.strip() for c in cells]


def _render(cells: list[str], widths: list[int], sep: bool) -> str:
    out = []
    for i, cell in enumerate(cells):
        w = widths[i]
        if sep:
            if cell.startswith(":") and cell.endswith(":"):
                inner = ":" + "-" * (w - 2) + ":"
            elif cell.startswith(":"):
                inner = ":" + "-" * (w - 1)
            elif cell.endswith(":"):
                inner = "-" * (w - 1) + ":"
            else:
                inner = "-" * w
            out.append(inner)
        else:
            out.append(cell + " " * (w - dw(cell)))
    return "| " + " | ".join(out) + " |"


def align_table(lines: list[str], start: int) -> tuple[list[str], int]:
    """Realign one table block starting at `start`; return (new_lines, end)."""
    end = start
    while end < len(lines) and _is_table_line(lines[end]):
        end += 1
    rows = [_split_row(lines[i]) for i in range(start, end)]
    if any(r is None for r in rows):
        return lines[start:end], end  # malformed — leave untouched
    ncol = max(len(r) for r in rows)
    # pad ragged rows
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    widths = [
        max(dw(r[i]) if not _is_sep_cell(r[i]) else 3 for r in rows)
        for i in range(ncol)
    ]
    out = []
    for r in rows:
        sep = all(_is_sep_cell(c) or c == "" for c in r) and any(
            _is_sep_cell(c) for c in r
        )
        out.append(_render(r, widths, sep))
    return out, end


def process(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[str] = []
    i = 0
    changed = False
    while i < len(lines):
        if _is_table_line(lines[i]) and (
            i + 1 < len(lines)
            and _is_table_line(lines[i + 1])
            and all(_is_sep_cell(c) for c in (_split_row(lines[i + 1]) or []))
        ):
            block, j = align_table(lines, i)
            out.extend(block)
            if block != lines[i:j]:
                changed = True
            i = j
        else:
            out.append(lines[i])
            i += 1
    if changed:
        path.write_text("\n".join(out), encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    for name in argv:
        p = Path(name)
        if process(p):
            print(f"realigned: {p}")
        else:
            print(f"clean: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
