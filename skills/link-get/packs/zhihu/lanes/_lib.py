#!/usr/bin/env python3
"""_lib.py — zhihu pack 原生 lane 共享助手（Lane ABI v1，references/lane-abi.md）。

- stdin：恰好一行 JSON {job_id, identity:{raw,key,kind,params,...},
  ctx:{artifact_dir,journal_dir,budget_ms,cred_handle,key}}。
- stdout：JSONL —— progress / artifact / 终态 result|data|error 恰好一条。
- rc10 + 无终态行 = dep 缺席静默跳过；产物只写 ctx.artifact_dir 内。
- '==> 已存' 行归 engine 打，lane 不打（lane-abi §7）。
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# 荒原页 = 内容不存在/已删除的墓碑证据（zhihu-get grep -qE 判据原样）
WASTELAND_RE = re.compile("知识荒原|没有知识存在的荒原")


def read_req():
    """读 stdin 单行 JSON 请求（engine 写完一行即关 stdin）。"""
    return json.loads(sys.stdin.readline())


def emit(ev):
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def eprint(msg):
    """stderr 自由文本副通道（runner 收进 <lane>.stderr.log）。"""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def progress(msg, **kw):
    emit({"type": "progress", "msg": msg, **kw})


def artifact(path, name):
    emit({"type": "artifact", "path": str(path), "name": name})


def result(items):
    emit({"type": "result", "items": items})


def data(payload):
    emit({"type": "data", "payload": payload})


def error(cls, evidence, retryable=False, retry_after=None, **kw):
    ev = {
        "type": "error",
        "class": cls,
        "evidence": evidence,
        "retryable": bool(retryable),
    }
    if retry_after is not None:
        ev["retry_after"] = retry_after
    ev.update(kw)
    emit(ev)


def die(cls, evidence, retryable=False, **kw):
    """终态 error + rc0 —— 终态行优先于 rc，runner 不再合成 lane_crash。"""
    eprint(evidence)
    error(cls, evidence, retryable=retryable, **kw)
    sys.exit(0)


def skip(msg=""):
    """dep 缺席静默跳过：无终态行 + rc10。"""
    if msg:
        eprint(msg)
    sys.exit(10)


def truthy(v):
    """engine _truthy 同则：bool 原样 / 数字非零 / '1/true/yes/on'（不分大小写）。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


# ---- finalize：zhihu-get L178-205（slug+finalize）的忠实移植 ----------------
# GNU tr 按字节删集只放 ASCII '/\:*?"<>|'——全角标点入会切碎 CJK 字节。
_SLUG_DELETE = {ord(c): None for c in '/\\:*?"<>|'}


def slug(title):
    """tr -d '/\\:*?"<>|' | tr ' ' '-' | tr -s '-' → ${s:0:60}。"""
    s = title.translate(_SLUG_DELETE).replace(" ", "-")
    return re.sub(r"-+", "-", s)[:60]


def _title_of(tmp_path):
    """sed -n 's/^Title: //p; s/^# //p' | head -1 —— 首个命中行去前缀。"""
    try:
        with open(tmp_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Title: "):
                    return line[len("Title: ") :].rstrip("\n")
                if line.startswith("# "):
                    return line[2:].rstrip("\n")
    except OSError:
        pass
    return ""


def finalize(tmp_path, out_dir, lane, target):
    """tmp → out_dir/<slug>--<id>.md（无标题 → <lane>-<id>.md），补 frontmatter。

    id：answer/<aid> 优先（修取错 qid 的存量 bug）→ [0-9]{5,} → epoch。
    返回成品路径（对应 bash 的 FINAL_OUT）。
    """
    title = _title_of(tmp_path)
    m = re.search(r"answer/([0-9]+)", target)
    id_ = m.group(1) if m else ""
    if not id_:
        m = re.search(r"[0-9]{5,}", target)
        id_ = m.group(0) if m else ""
    if not id_:
        id_ = str(int(time.time()))
    name = f"{slug(title)}--{id_}.md" if title else f"{lane}-{id_}.md"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / name
    head = f"---\nsource: {target}\nvia: {lane}\n---\n\n".encode()
    out.write_bytes(head + Path(tmp_path).read_bytes())
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    return str(out)
