#!/usr/bin/env python3
"""yaml 散文注释宽度检查：纯注释行（首个非空白字符是 #）超 80 显示列报错。

East Asian Wide/Fullwidth 字符按 2 列计——终端与 diff 看到的是显示宽度，
不是字符数；yamllint 的 line-length 只数字符，管不了这条。无空格且无
宽字符的单 token 注释行（长 URL 之类不可断情形）豁免。注释断点该落在
标点/从句边界是语义判断，机检只把宽度这半段挂上；宽度重排用编辑器
reflow（vim gq / Emacs M-q / VS Code Rewrap）。

pre-commit 传暂存文件名作参数；CI 裸跑时检查 git ls-files 的全部
*.yaml/*.yml。
"""

import re
import subprocess
import sys
import unicodedata

LIMIT = 80

# 块标量 (|/>) 与多行引号标量内部，行首 # 是字面内容而非注释——如
# description 里嵌的 python 片段。只统计结构性行上的注释。
# BLOCK_OPEN 须兼容任意缩进的 key 与 `- key: |` 列映射形态（re.match
# 锚行首，键前的空白得在模式里吃掉）；裸 `- |` 归 LIST_BLOCK。
BLOCK_OPEN = re.compile(r"^\s*(?:-\s+)?[^\s#][^:]*:\s*[|>][+\-\d]{0,2}\s*(?:#.*)?$")
LIST_BLOCK = re.compile(r"^\s*-\s*[|>][+\-\d]{0,2}\s*(?:#.*)?$")
QUOTE_VAL = re.compile(r"[^\s#][^:]*:\s*([\"'])(.*)$")


def display_width(text):
    expanded = text.expandtabs(8)
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in expanded)


def unbreakable(text):
    body = text.lstrip().lstrip("#").strip()
    return " " not in body and display_width(body) == len(body)


def quote_closed(rest, q):
    """rest（首个引号字符之后）是否自带闭合引号。"""
    i = 0
    while i < len(rest):
        c = rest[i]
        if q == '"':
            if c == "\\":
                i += 2
                continue
            if c == '"':
                return True
        elif c == "'":
            if i + 1 < len(rest) and rest[i + 1] == "'":
                i += 2
                continue
            return True
        i += 1
    return False


def scalar_content_lines(lines):
    """标量内容行（块标量内部、多行引号标量内部）的行号集合。"""
    content = set()
    block_indent = None
    qchar = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if qchar is not None:
            content.add(i)
            if quote_closed(line, qchar):
                qchar = None
            continue
        if block_indent is not None:
            if stripped == "":
                content.add(i)
                continue
            if indent > block_indent:
                content.add(i)
                continue
            block_indent = None
        if BLOCK_OPEN.match(line) or LIST_BLOCK.match(line):
            block_indent = indent
            continue
        m = QUOTE_VAL.match(stripped)
        if m and not quote_closed(m.group(2), m.group(1)):
            qchar = m.group(1)
    return content


def main(paths):
    if not paths:
        # -z + quotepath=off：默认 quotepath 会把非 ASCII 文件名转成
        # \303\244 转义、含空格名也会被 .split() 切碎——NUL 分隔才是机器接口
        paths = [
            p
            for p in subprocess.check_output(
                [
                    "git",
                    "-c",
                    "core.quotepath=off",
                    "ls-files",
                    "-z",
                    "--",
                    "*.yaml",
                    "*.yml",
                ]
            )
            .decode("utf-8", "surrogateescape")
            .split("\0")
            if p
        ]
    bad = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
        content = scalar_content_lines(lines)
        for n, text in enumerate(lines, 1):
            if n - 1 in content or not text.lstrip().startswith("#"):
                continue
            width = display_width(text)
            if width > LIMIT and not unbreakable(text):
                bad.append(f"{path}:{n}: {width} display cols: {text.strip()}")
    for b in bad:
        print(b)
    if bad:
        print(
            f"{len(bad)} yaml comment line(s) exceed {LIMIT} display columns",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
