#!/usr/bin/env python3
"""mineru_lane.py — generic pack kind=doc 车道：MinerU 云 API 解析文档 URL → Markdown。

stdin : 一行 JSON {job_id, identity{raw,key,kind,params,...},
                   ctx{artifact_dir,journal_dir,budget_ms,cred_handle,key}}
stdout: JSONL events（progress/artifact/result/error），恰好一个终态行
rc    : 0=已自报终态 / 10=静默跳过（mineru 不可解析，dep 缺席语义）

命令面：spawn `mineru <url> -o <artifact_dir> --json [--lang …]`
（skills/mineru/scripts/mineru.py 的 CLI 面；stdout 单行 JSON 状态报告，
产物树落 <out>/<stem>/<stem>.md + images/ 等）。解析序：
$MINERU_BIN → PATH 上 `mineru` → 兄弟 skill mineru.py（rsync 线含 mineru）。
全无 → rc10（doc 臂单车道，全 skip → engine 合成 dep_absent）。

=================  PRIVACY BOUNDARY（硬约束）  =================
MinerU 云是 server-side 抓取：URL 被原样交给第三方云去下载——
任何含凭据/签名/私域语义的 URL 一旦提交即泄漏访问权。本分两层：

1. 路由层（pack.toml [kind_by_url]，先于本 lane）：非 https 的 doc URL、
   query 带签名类参数（sig|signature|token|expires|key-pair-pk|credential|
   x-amz-*）的 doc URL → kind=doc-signed（无臂伪 kind）→ route_miss rc2，
   lane 根本不会被 spawn。
2. 本 lane 自检（lane-run 旁路 / --param kind=doc 强指 / 正则漂移的兜底）：
   https-only、无 userinfo、非私网/回环/重绑域名形、query 无凭据参数。
   命中即 notcovered（retryable=false）终态——车道不覆盖该 URL 形状。
   engine 的 admit SSRF 闸已拒字面私网 host；此处是深度防御 + DNS-rebind
   形（*.nip.io 等）与数字 IP 字面量的补强。

错误分类（mineru rc/stdout/stderr → lane class）：
  rc0 + state=done → dir-diff 收产物 → result
  rc0/1 但无产物或 state=failed：
    rate limit/quota/429      → transient（retryable；engine RC 表无
                                rate_limited 键——直发会 KeyError）
    token/鉴权、超限、不支持   → notcovered（车道覆盖缺口非内容墓碑）
    timeout/network/unreachable → transient
    其余                       → noresults
  subprocess 超时             → budget_exceeded（engine 的 budget+grace 杀外）
"""

import ipaddress
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

LANE = "mineru"

# 兄弟 skill 兜底：packs/generic/lanes → skills/ → mineru/scripts/mineru.py
SKILL_SCRIPT = Path(__file__).resolve().parents[4] / "mineru" / "scripts" / "mineru.py"

# --- 隐私边界字面表 ---------------------------------------------------------
PRIVATE_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback"}
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home")
# DNS-rebind 公共服务域名形——字面 host 查不出私网但解析即回环
REBIND_SUFFIXES = (
    ".nip.io",
    ".sslip.io",
    ".xip.io",
    ".lvh.me",
    ".vcap.me",
    ".localtest.me",
)
# 签名类 query 参数名（比对前 lowercase；x-amz-* 前缀走前缀匹配）
CRED_PARAMS = {
    "sig",
    "signature",
    "token",
    "expires",
    "key-pair-pk",
    "key-pair",
    "credential",
    "credentials",
    "access-token",
    "access_token",
    "auth",
    "signatureversion",
}


def emit(ev):
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def eprint(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def truthy(v):
    """engine _truthy 同则。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def refusal_reason(url):
    """公网边界自检（lane 层兜底；路由层 doc-signed 伪 kind 已先行 rc2）。

    返回拒绝理由 str；可送云 → None。
    """
    try:
        u = urlsplit(url)
    except ValueError as e:
        return f"unparseable url: {e}"
    if u.scheme != "https":
        return (
            f"scheme '{u.scheme or '(none)'}' — MinerU cloud fetches the URL "
            "server-side; only public https URLs are allowed"
        )
    if u.username or u.password:
        return "URL carries userinfo credentials"
    host = (u.hostname or "").lower().rstrip(".")
    if not host:
        return "empty host"
    if host in PRIVATE_HOSTNAMES or host.endswith(PRIVATE_SUFFIXES):
        return f"private hostname '{host}'"
    if host.endswith(REBIND_SUFFIXES):
        return f"dns-rebind hostname '{host}'"
    ip = None
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        # 数字 IP 字面量（2130706433 = 127.0.0.1）——stdlib 不解析的私网形
        if host.isdigit():
            try:
                ip = ipaddress.ip_address(int(host))
            except ValueError:
                pass
    if ip is not None and (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return f"private address '{host}'"
    for name, _v in parse_qsl(u.query, keep_blank_values=True):
        n = name.lower()
        if n in CRED_PARAMS or n.startswith("x-amz-"):
            return (
                f"credential-ish query param '{name}' — signed URLs must not "
                "be submitted to MinerU cloud (server-side fetch)"
            )
    return None


def resolve_mineru():
    """mineru 入口解析序：$MINERU_BIN → PATH `mineru` → 兄弟 skill 脚本。"""
    if os.environ.get("MINERU_BIN"):
        return [os.environ["MINERU_BIN"]]
    w = shutil.which("mineru")
    if w:
        return [w]
    if SKILL_SCRIPT.is_file():
        return [sys.executable, str(SKILL_SCRIPT)]
    return None


def snap(d):
    """artifact_dir 快照 {path: (size, mtime_ns)}——rc 后与 pre-run 比对新产物。"""
    d = Path(d)
    if not d.is_dir():
        return {}
    return {
        p: (s.st_size, s.st_mtime_ns)
        for p in d.rglob("*")
        if p.is_file()
        for s in [p.stat()]
    }


def build_argv(base, url, adir, params, timeout_s):
    """params → mineru argv 旗标映射（engine [params] 闸已滤未声明键）。"""
    argv = [*base, url, "-o", str(adir), "--json", "--timeout", str(timeout_s)]
    if params.get("lang"):
        argv += ["--lang", str(params["lang"])]
    if truthy(params.get("ocr")):
        argv += ["--ocr"]
    if params.get("pages"):
        argv += ["--pages", str(params["pages"])]
    if params.get("model"):
        argv += ["--model", str(params["model"])]
    if params.get("api"):
        argv += ["--api", str(params["api"])]
    for f in str(params.get("format") or "").split(","):
        if f.strip():
            argv += ["--format", f.strip()]
    if truthy(params.get("no_formula")):
        argv += ["--no-formula"]
    if truthy(params.get("no_table")):
        argv += ["--no-table"]
    return argv


def classify(err):
    """mineru 错误文本 → (class, retryable)。rate_limited 刻意不归并——
    engine RC_FOR_CLASS 无此键，直发会让 envelope 路径 KeyError。"""
    e = (err or "").lower()
    if "rate limit" in e or "429" in e or "quota" in e:
        return "transient", True
    if (
        "invalid token" in e
        or "token expired" in e
        or "needs a token" in e
        or "a0202" in e
        or "a0211" in e
    ):
        return "notcovered", False  # token 缺口是车道覆盖问题，非内容墓碑
    if (
        "too large" in e
        or "too many pages" in e
        or "exceed" in e
        or "unsupported" in e
        or "not support" in e
        or "cannot delete" in e
    ):
        return "notcovered", False  # 车道能力上限，内容仍在
    if (
        "timed out" in e
        or "timeout" in e
        or "network" in e
        or "unreachable" in e
        or "download failed" in e
        or "upload failed" in e
    ):
        return "transient", True
    return "noresults", False


def main():
    try:
        req = json.loads(next(line for line in sys.stdin if line.strip()))
    except Exception as e:
        emit(
            {
                "type": "error",
                "class": "protocol_violation",
                "evidence": f"stdin JSON: {e}",
                "retryable": False,
            }
        )
        return 10

    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    url = ident.get("raw") or ""
    params = ident.get("params") or {}
    adir = Path(ctx.get("artifact_dir") or (ctx.get("journal_dir", ".") + "/artifacts"))
    adir.mkdir(parents=True, exist_ok=True)

    # --- 隐私边界自检（路由层 doc-signed 已先拦一层；此处为 lane-run/
    #     强制 kind 的兜底防线）
    why = refusal_reason(url)
    if why:
        return _refuse(url, why)

    base = resolve_mineru()
    if base is None:
        eprint(f"{LANE}_lane: mineru 缺席（MINERU_BIN/PATH/兄弟 skill 均未命中）")
        return 10

    budget_ms = int(ctx.get("budget_ms") or 600000)
    timeout_s = max(5, int(budget_ms / 1000) - 3)  # 留 3s 余量让本 lane 分类
    argv = build_argv(base, url, adir, params, timeout_s)
    emit({"type": "progress", "msg": f"spawn {Path(base[-1]).name}", "argv": argv})

    before = snap(adir)
    t0 = time.monotonic()
    try:
        p = subprocess.Popen(
            argv,
            env=dict(os.environ),
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as e:
        return _crash(f"spawn: {e}")
    try:
        out, err = p.communicate(timeout=timeout_s)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return _die_ret("budget_exceeded", f"mineru exceeded budget_ms={budget_ms}")

    # mineru 诊断 → lane stderr 副通道
    for line in (err or "").splitlines():
        sys.stderr.write(line[:400] + "\n")
    sys.stderr.flush()

    # --json 状态报告（stdout 单行 JSON；解析失败回退 stderr 分类）
    status = None
    try:
        status = json.loads((out or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        status = None
    res = {}
    if isinstance(status, dict):
        results = status.get("results") or []
        if results:
            res = results[0]

    new = [p for p, meta in snap(adir).items() if p not in before or before[p] != meta]
    if rc == 0 and (res.get("state") == "done" or (status is None and new)):
        if not new:
            return _die_ret(
                "noresults",
                "mineru rc=0 but no artifact under artifact_dir",
                retryable=False,
            )
        items = []
        for f in sorted(new):
            rel = str(f.relative_to(adir))
            emit({"type": "artifact", "path": str(f), "name": rel})
            items.append({"path": str(f), "name": rel, "bytes": f.stat().st_size})
        rp = {
            k: res.get(k)
            for k in ("api", "modality", "task_id")
            if res.get(k) is not None
        }
        emit(
            {
                "type": "result",
                "items": items,
                "params": rp,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
        )
        return 0

    err_text = res.get("error") or (err or "").strip() or f"mineru rc={rc}"
    cls, retryable = classify(err_text)
    return _die_ret(cls, f"mineru: {err_text[-400:]}", retryable=retryable)


def _refuse(url, why):
    eprint(f"{LANE}_lane: refused {url}: {why}")
    emit(
        {
            "type": "error",
            "class": "notcovered",
            "evidence": f"privacy boundary: {why}",
            "retryable": False,
        }
    )
    return 0


def _die_ret(cls, evidence, retryable=False, **kw):
    eprint(f"{LANE}_lane: {evidence}")
    emit(
        {
            "type": "error",
            "class": cls,
            "evidence": evidence,
            "retryable": bool(retryable),
            **kw,
        }
    )
    return 0


def _crash(evidence):
    eprint(f"{LANE}_lane: {evidence}")
    emit(
        {
            "type": "error",
            "class": "lane_crash",
            "evidence": evidence,
            "retryable": True,
        }
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        try:
            emit(
                {
                    "type": "error",
                    "class": "lane_crash",
                    "evidence": f"lane-internal: {e!r}",
                    "retryable": True,
                }
            )
        finally:
            sys.exit(1)
