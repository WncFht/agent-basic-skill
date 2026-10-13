#!/usr/bin/env python3
"""firecrawl_lane — Firecrawl 云端渲染兜底 lane（zhihu-get firecrawl() L241-267）。

POST api.firecrawl.dev/v1/scrape → data.markdown → 产物。
荒原页 → permanent 墓碑；产物空/无字母数字 → transient。
无 FIRECRAWL_API_KEY 或 curl 缺席 → rc10（needs.env/tools 闸缺席外的兜底）。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

LANE = "firecrawl"


def main():
    req = _lib.read_req()
    ident = req["identity"]
    ctx = req["ctx"]
    url = ident["raw"]
    adir = ctx["artifact_dir"]

    if not shutil.which("curl"):
        _lib.skip("curl 缺席，firecrawl lane 跳过")
    key = os.environ.get("FIRECRAWL_API_KEY") or ""
    if not key:
        _lib.skip("无 FIRECRAWL_API_KEY，跳过 Firecrawl 兜底")

    proxy = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or "http://127.0.0.1:7890"
    )
    tmp = Path(adir) / ".firecrawl-tmp.md"
    body = json.dumps({"url": url, "formats": ["markdown"], "onlyMainContent": True})
    try:
        proc = subprocess.run(
            [
                "curl",
                "-s",
                "--proxy",
                proxy,
                "--max-time",
                "90",
                "-X",
                "POST",
                "https://api.firecrawl.dev/v1/scrape",
                "-H",
                f"Authorization: Bearer {key}",
                "-H",
                "Content-Type: application/json",
                "-d",
                body,
            ],
            check=False,
            timeout=105,
            stdout=subprocess.PIPE,
        )
        raw = proc.stdout
    except subprocess.TimeoutExpired:
        raw = b""  # || true

    # bash 管道段的 python3 -c 提取：json.load → data.markdown（缺 → ''）
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        obj = {}
    data_obj = obj.get("data") if isinstance(obj, dict) else {}
    md = (data_obj or {}).get("markdown") if isinstance(data_obj, dict) else ""
    md = md if isinstance(md, str) else ""
    tmp.write_text(md, encoding="utf-8")

    if _lib.WASTELAND_RE.search(md):
        try:
            tmp.unlink()
        except OSError:
            pass
        _lib.die("permanent", "内容不存在或已删除（荒原页）")
    # [ ! -s ] || ! grep -q '[[:alnum:]]' —— 空产物或无字母数字（含 CJK）判失败
    if not md or not any(ch.isalnum() for ch in md):
        try:
            tmp.unlink()
        except OSError:
            pass
        _lib.die("transient", "Firecrawl 抓取失败", retryable=True)

    final = _lib.finalize(tmp, adir, LANE, url)
    name = Path(final).name
    _lib.artifact(final, name)
    _lib.result([{"path": final, "name": name, "bytes": os.path.getsize(final)}])


if __name__ == "__main__":
    main()
