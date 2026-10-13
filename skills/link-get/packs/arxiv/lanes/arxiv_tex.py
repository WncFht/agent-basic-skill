#!/usr/bin/env python3
r"""arxiv_tex.py — arxiv pack 原生 lane：arxiv-tex（stdout 型）→ artifact 终态。

stdin : 一行 JSON {job_id, identity{raw,key,kind,params}, ctx{artifact_dir,...}}
stdout: JSONL events（call/progress/result/error），恰好一个终态行
rc    : 0=已自报终态；其他=crash → runner 合成 lane_crash

为什么必须原生 lane：arxiv-tex 只产 stdout（arxiv-to-prompt 无 -o），
monolith shim 的 dir-diff 永远收不到产物 → noresults 误判（spec §4.2）。

为什么传裸 id 不传 URL：arxiv-to-prompt 的 extract_arxiv_id 只认新式
abs/pdf URL 且丢弃 vN（(?:v\d+)? 非捕获）；旧式 archive.CL/NNNNNNN URL
整串当 id 拼 e-print → 404。lane 自解裸 id（新旧两式含 vN）按位置参喂
connector——wrapper looks_like_id 同形收；vN 显式钉版时 wrapper 自己
SKIP 戳层，直通 uvx。

错误面（全部实读 core.py 核实）：arxiv-to-prompt 失败几乎全是
rc0+空 stdout——`if not content: return` / `if output is None: return`。
只有 argparse 互斥/缺位置参走 parser.error → rc2；wrapper 侧 uvx 缺席
exit 5。分类按 stderr 文本（详见 classify() 注释表）。
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

FALLBACK_CONN = str(
    Path(__file__).resolve().parents[3] / "scripts" / "connectors" / "arxiv-tex"
)

# 与 pack.toml [identity].capture.id 同形——新式 NNNN.NNNNN(vN) 与旧式
# archive.CL/NNNNNNN(vN) 整条捕获（丢 archive 前缀或 vN 都是 404 实锤）
ID_RE = re.compile(r"([a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?|\d{4}\.\d{4,5}(?:v\d+)?)")

MODES = {"full", "abstract", "sections", "figures", "list", "tokens"}
# mode → arxiv-to-prompt 旗标 + 产物扩展名（list 列节名、tokens 打 token 数、
# figures 打图路径——均非 TeX，给 .txt 系名保持产物自描述）
MODE_FLAG = {
    "abstract": ["--abstract"],
    "figures": ["--figure-paths"],
    "list": ["--list-sections"],
    "tokens": ["--token-count"],
}
MODE_EXT = {
    "full": ".tex",
    "sections": ".sections.tex",
    "abstract": ".abstract.txt",
    "figures": ".figpaths.txt",
    "list": ".sections.txt",
    "tokens": ".tokencount.txt",
}
# 修饰旗标（改内容不改输出形）——进 satisfies 等值断言，异修饰束互不供
MODIFIER_FLAGS = {
    "no_comments": "--no-comments",
    "no_appendix": "--no-appendix",
    "expand_macros": "--expand-macros",
}
# engine 保留 param → wrapper 自有旗标（戳层语义：LGC_REFRESH/LGC_OFF/LGC_TTL）
STAMP_FLAGS = {"refresh": "--refresh", "no_cache": "--no-cache"}


def emit(type_, **kw):
    sys.stdout.write(json.dumps({"type": type_, **kw}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def die(cls, evidence, retryable=None, scope_hint=None):
    ev = {
        "class": cls,
        "evidence": evidence,
        "retryable": (
            cls in ("transient", "rate_limited") if retryable is None else retryable
        ),
    }
    if scope_hint:
        ev["scope_hint"] = scope_hint
    emit("error", **ev)
    return 0


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def find_connector():
    """arxiv-tex 解析序：ARXIV_TEX env → PATH → 仓内相对兜底。"""
    cands = []
    if os.environ.get("ARXIV_TEX"):
        cands.append(os.environ["ARXIV_TEX"])
    w = shutil.which("arxiv-tex")
    if w:
        cands.append(w)
    cands.append(FALLBACK_CONN)
    for c in cands:
        p = Path(c)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def classify(rc, serr):
    """arxiv-tex rc+stderr → (error class, scope_hint)。

    | 信号 | class | scope | 依据 |
    | rc2（argparse 互斥/缺参） | notcovered | params | argv 由 lane 按 params 构造 |
    | rc5+uvx 未装 | dep_absent | — | wrapper:112-115 |
    | 其他非零 | transient | — | 未知非零当瞬时 |
    | Error checking source availability | transient | — | check_source_available 的
      RequestException（core.py:1177）——网络面 |
    | Error downloading / download lock / Failed to | transient | — | 下载/解包/锁/
      缓存目录/publish 失败（core.py:153/224/240/243） |
    | TeX source files not available | notcovered | — | format 页无 'Download source'
      的能力判词（core.py:1176）：无源/404 同文——内容级不覆盖，照常记墓碑 |
    | Main .tex file not found | noresults | — | 源包在场无主 tex——内容级空 |
    | 节名 not found / ambiguous | notcovered | params | sections 模式参数级不覆盖 |
    | tiktoken | dep_absent | — | tokens 模式可选依赖缺席（cli.py:188） |
    | rc0+空 stdout 无诊断 | noresults | — | 未解释的空——runner 对哑 rc0 同则 |

    scope="params" ⇒ engine 不写 lane×key 墓碑——参数级拒绝不是内容覆盖判词，
    上账会把同键其余参数组合陪葬 30d。
    """
    s = serr or ""
    if rc == 2:
        return "notcovered", "params"
    if rc == 5 and "uvx" in s:
        return "dep_absent", None
    if rc != 0:
        return "transient", None
    # rc0：stdout 空（调用方已判）——按 stderr 文本分
    if "Error checking source availability" in s:
        return "transient", None
    if "Error downloading" in s or "download lock" in s or "Failed to" in s:
        return "transient", None
    if "TeX source files not available" in s:
        return "notcovered", None
    if "Main .tex file not found" in s:
        return "noresults", None
    if "not found" in s or "ambiguous" in s:
        return "notcovered", "params"
    if "tiktoken" in s:
        return "dep_absent", None
    if "Error" in s or "Timed out" in s:
        return "transient", None
    return "noresults", None


def budget_s(ctx):
    try:
        return max(5.0, (int(ctx.get("budget_ms") or 120000) - 2000) / 1000)
    except (TypeError, ValueError):
        return 118.0


def safe_name(arxiv_id):
    """id → 文件名安全形：math.AG/0601234v2 → math.AG_0601234v2。"""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", arxiv_id)


def main():
    try:
        req = json.loads(next(line for line in sys.stdin if line.strip()))
    except Exception as e:
        return die("protocol_violation", f"stdin JSON: {e}", retryable=False)

    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    params = ident.get("params") or {}
    raw = ident.get("raw") or ""

    m = ID_RE.search(raw)
    if not m:
        return die(
            "notcovered",
            f"arXiv id 解不出（raw={raw!r}）——非 abs/pdf 论文 URL 不入此 pack",
            retryable=False,
        )
    arxiv_id = m.group(1)

    # mode 值域在 pack.toml [params].values 已由 engine 闸拒 rc2——此判是
    # 深层防御（裸跑/旧引擎），scope_hint=params 防参数级误伤上墓碑
    mode = str(params.get("mode") or "full")
    if mode not in MODES:
        return die(
            "notcovered",
            f"mode={mode!r} ∉ {sorted(MODES)}",
            retryable=False,
            scope_hint="params",
        )
    section = str(params.get("section") or "")
    if mode == "sections" and not section.strip():
        return die(
            "notcovered",
            "mode=sections 需要 section=<节名>（csv 可复数）",
            retryable=False,
            scope_hint="params",
        )

    conn = find_connector()
    if not conn:
        return die(
            "dep_absent",
            "arxiv-tex 不可执行（ARXIV_TEX/PATH/connectors/ 三段解析全落空）",
            retryable=False,
        )

    # 裸 id 位置参（URL 形态会被工具丢 vN/旧式整串 404——见模块 docstring）
    argv = [conn, arxiv_id]
    argv += MODE_FLAG.get(mode, [])
    if mode == "sections":
        for s in section.split(","):
            if s.strip():
                argv += ["--section", s.strip()]
    flags_on = {}
    for k, flag in MODIFIER_FLAGS.items():
        flags_on[k] = truthy(params.get(k))
        if flags_on[k]:
            argv.append(flag)
    for k, flag in STAMP_FLAGS.items():
        if truthy(params.get(k)):
            argv.append(flag)
    if params.get("cache_ttl"):
        argv += ["--cache-ttl", str(params["cache_ttl"])]

    adir = Path(ctx.get("artifact_dir") or (ctx.get("journal_dir", ".") + "/artifacts"))
    adir.mkdir(parents=True, exist_ok=True)
    emit("call", tool="arxiv-tex", argv=argv[1:], note="stdout→artifact")
    t0 = time.monotonic()

    try:
        proc = subprocess.Popen(
            argv,
            env=dict(os.environ),  # lane env 已白名单化——戳层 LGC_* 在列
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as e:
        return die("lane_crash", f"spawn: {e}")
    try:
        out, err = proc.communicate(timeout=budget_s(ctx))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        return die("budget_exceeded", f"arxiv-tex 超时（budget={budget_s(ctx):.0f}s）")
    rc = proc.returncode

    # connector 诊断原样过副通道（runner 收进 <lane>.stderr.log）
    for line in (err or "").splitlines():
        sys.stderr.write(line[:400] + "\n")
    sys.stderr.flush()

    tail = "\n".join((err or "").splitlines()[-6:]) or (out or "").strip()[-300:]
    if rc != 0 or not (out or "").strip():
        cls, scope = classify(rc, err)
        return die(cls, tail or f"arxiv-tex rc={rc} empty stdout", scope_hint=scope)

    art = adir / (safe_name(arxiv_id) + MODE_EXT[mode])
    art.write_text(out, encoding="utf-8")
    emit(
        "result",
        items=[{"path": str(art), "name": art.name, "bytes": art.stat().st_size}],
        params={
            # satisfies 断言面：全部按请求侧原值上报（mode 已校验归一、
            # section 逐字——非 sections 模式带的 section 是 no-op，但
            # 请求断言仍按原值来；归一成 "" 会让 mode=full&section=X 永不命中）
            "mode": mode,
            "section": section,
            "no_comments": flags_on["no_comments"],
            "no_appendix": flags_on["no_appendix"],
            "expand_macros": flags_on["expand_macros"],
        },
        via="arxiv-tex",
        elapsed_ms=int((time.monotonic() - t0) * 1000),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        try:
            emit(
                "error",
                **{
                    "class": "lane_crash",
                    "evidence": f"lane-internal: {e!r}",
                    "retryable": True,
                },
            )
        finally:
            sys.exit(1)
