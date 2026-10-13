#!/usr/bin/env python3
"""jina_lane — r.jina.ai 免 key 快读 lane（zhihu-get jina() L207-239 移植）。

判据：荒原页 → permanent 墓碑；产物须非空且含 'Title:'，否则 3s 后重试，
3 次耗尽 → transient（不交判据不干净的劣货）。成功 → head -40 进 stderr
（lane stdout 是协议面，预览走 stderr 副通道）+ finalize → result。
curl 缺席 → rc10（needs.tools 闸缺席外的兜底）。
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

LANE = "jina"


def main():
    req = _lib.read_req()
    ident = req["identity"]
    ctx = req["ctx"]
    url = ident["raw"]
    adir = ctx["artifact_dir"]

    if not shutil.which("curl"):
        _lib.skip("curl 缺席，jina lane 跳过")

    proxy = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or "http://127.0.0.1:7890"
    )
    nc = []
    if _lib.truthy((ident.get("params") or {}).get("refresh")):
        nc = ["-H", "X-No-Cache: true"]

    tmp = Path(adir) / ".jina-tmp.md"
    got = False
    for attempt in (1, 2, 3):
        try:
            subprocess.run(
                [
                    "curl",
                    "-sL",
                    "--proxy",
                    proxy,
                    "--max-time",
                    "60",
                    *nc,
                    f"https://r.jina.ai/{url}",
                    "-o",
                    str(tmp),
                ],
                check=False,
                timeout=75,
            )
        except subprocess.TimeoutExpired:
            pass  # || true —— 计入失败重试
        content = (
            tmp.read_text(encoding="utf-8", errors="replace") if tmp.is_file() else ""
        )
        if _lib.WASTELAND_RE.search(content):
            try:
                tmp.unlink()
            except OSError:
                pass
            _lib.die("permanent", "内容不存在或已删除（荒原页）")
        if content and "Title:" in content:
            got = True
            break
        _lib.progress(f"jina 第 {attempt}/3 次未得干净页")
        time.sleep(3)

    if not got:
        try:
            tmp.unlink()
        except OSError:
            pass
        _lib.die("transient", "Jina 3 次重试均失败", retryable=True)

    # head -40 → stderr 预览（zhihu-get 打 stdout；lane stdout 只能走 JSONL）
    for line in content.splitlines()[:40]:
        _lib.eprint(line)

    final = _lib.finalize(tmp, adir, LANE, url)
    name = Path(final).name
    _lib.artifact(final, name)
    _lib.result([{"path": final, "name": name, "bytes": os.path.getsize(final)}])


if __name__ == "__main__":
    main()
