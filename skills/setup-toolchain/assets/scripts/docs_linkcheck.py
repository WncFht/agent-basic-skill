#!/usr/bin/env python3
"""markdown 相对死链检查器：链接 / 图片引用的本地目标存在性校验。

跳过 code fence 与行内 code span 内容；http(s)/锚点/协议链接不查；
`%XX` 按 URL-decode 后解析。

用法：python3 scripts/docs_linkcheck.py [--root docs]

  --root      扫描根目录（默认 docs/）

退出码：0 全绿；1 有死链。pre-commit 里挂 `pass_filenames: false`
全量扫——删/改名目标件不触发文件钩的盲区由全量扫兜住。
"""

import os
import re
import sys
import urllib.parse

LINK_RX = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
SKIP_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^#|^//")
CODE_FENCE_RX = re.compile(r"^```")


def iter_md(root: str):
    for dirpath, _dirs, names in os.walk(root):
        for n in sorted(names):
            if n.endswith(".md"):
                yield os.path.join(dirpath, n)


def check_file(path: str):
    """返回 [(lineno, target, resolved)] 死链列表。"""
    dead = []
    in_fence = False
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return dead
    base = os.path.dirname(path)
    for i, line in enumerate(text.split("\n"), 1):
        if CODE_FENCE_RX.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = re.sub(r"`[^`]*`", "", line)
        for m in LINK_RX.finditer(stripped):
            target = m.group(1).strip()
            if SKIP_SCHEME.match(target) or not target:
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            resolved = os.path.normpath(
                os.path.join(base, urllib.parse.unquote(target))
            )
            if not os.path.exists(resolved):
                dead.append((i, target, resolved))
    return dead


def main():
    root = "docs"
    args = sys.argv[1:]
    if "--root" in args:
        root = args[args.index("--root") + 1]
    dead_total = []
    for f in iter_md(root):
        dead_total.extend((f, *d) for d in check_file(f))
    for f, ln, target, resolved in dead_total:
        print(f"{f}:{ln} 死链 -> {target}  （解到 {resolved}）")
    print(f"\n{len(dead_total)} dead link(s) across {sum(1 for _ in iter_md(root))} files")
    return 1 if dead_total else 0


if __name__ == "__main__":
    sys.exit(main())
