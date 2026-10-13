#!/usr/bin/env python3
"""scraper_lane.py — lane ABI v1 native lane over zhihu-scraper fetch.

stdin : ONE JSON line {job_id, identity{raw,key,kind,params,...},
        ctx{artifact_dir,journal_dir,budget_ms,cred_handle,key}}
stdout: JSONL events — progress / artifact / exactly ONE terminal result|error.
stderr: tool diagnostics tail (engine captures into <lane>.stderr.log).
rc    : 0 terminal emitted | 10 silent skip (zhihu-scraper absent / kind not covered)

覆盖 kind：ans（评论产能唯一车道）、col（整栏归档唯一车道）；其余 kind → rc10。

target = identity.raw；host 为 zhuanlan.zhihu.com 时归一化为
https://www.zhihu.com/column/<slug>（zhihu-get:483-485 平价——scraper 不认短链）。

argv: zhihu-scraper fetch <target> -s <settings> -o <stage> [--comments]
    settings = $ZHIHU_SETTINGS 或 ~/.config/zhihu-skill/settings.toml（connector 平价）
    --comments 在 params.comments 真值时追加（COMMENTS=1 时 connector 对所有
    scraper 分支都加，含 col——与 lanes_run 行为一致；flag 是
    BooleanOptionalAction，永不带值）。

Staging：产物先落 <artifact_dir>/.scraper-stage，result items 列相对 relpath
（scraper 产 <title>/ 条目目录 + assets/ + 归档进度.md，结构本身是产物）。

rc!=0 分类（证据=工具 stdout+stderr 尾部；cred-blind——auth_expired 绝不进
lane breaker）:
    401/need_login/z_c0 → auth_expired   (needs_human；scraper 401/403 文案自带 z_c0)
    zse-ck/40352/unhuman/captcha/回退不可用 → challenge_needed (needs_human)
    429/Retry-After     → rate_limited   (retryable, retry_after?)
    裸 HTTP 403 无更明证据 → challenge_needed (needs_human)
    其余                → transient      (retryable)
删除证据不在此判——产出内容的删除签名由 engine delguard/lgc put rc4 层判
（connector staged_run→z_store --from→ZDEL=1→rc4 同层平价）。
"""

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

RC_SKIP = 10
TOOL = "zhihu-scraper"
KINDS = {"ans", "col"}
STAGE_NAME = ".scraper-stage"
DEFAULT_SETTINGS = "~/.config/zhihu-skill/settings.toml"
STDERR_FORWARD_LINES = 40
EVIDENCE_CAP = 400
SHA256_CAP = 64 * 1024 * 1024

# --- 分类证据表（zhcli/scraper 两 lane 同源；改一处须同步另一处）---
# auth 先于 challenge：need_login=true 是凭证死；纯风控 challenge 不带它。
AUTH_TEXT = (
    "need_login=true",
    "need_login': True",
    'need_login": true',
    "need_login: True",
    "ERR_DECODE_SECURE_COOKIE",
    "authentication is missing or expired",
    "Check the z_c0",
    "Refresh the z_c0",
    "Cookie fields missing",
    "Cookie 字段缺少",
    "Could not safely load Cookie file",
    "CookieFileError",
    "cookie 无效",
    "Cookie 无效",
    "cookie 失效",
    "Cookie 失效",
    "cookie 已过期",
    "Cookie 已过期",
    "登录状态无效",
    "登录已过期",
    "登录失效",
    "重新登录",
    "尚未登录",
    "需要登录",
    "请先登录",
    "未登录",
    "LoginTimeoutError",
    "AuthenticationError",
    "login required",
    "not logged in",
)
CHALLENGE_TEXT = (
    "zh-zse-ck",
    "zse-ck",
    "__zse_ck",
    "unhuman",
    "40352",
    "风控",
    "人机验证",
    "安全验证",
    "验证码",
    "BrowserFallbackUnavailableError",
    "没有配置浏览器回退",
)
AUTH_RE = re.compile(r"(?<!\d)401(?!\d)")
CHALLENGE_RE = re.compile(r"captcha|risk.?control", re.IGNORECASE)
RATE_RE = re.compile(
    r"(?<!\d)429(?!\d)|rate.?limit|retry.?after|RetryWaitError|限流|请求过于频繁|操作频繁",
    re.IGNORECASE,
)
STATUS_403_RE = re.compile(r"(?<!\d)403(?!\d)")
RETRY_AFTER_RE = re.compile(r"retry.?after[:\s=]*(\d+)", re.IGNORECASE)


def emit(type_, **kw):
    sys.stdout.write(json.dumps({"type": type_, **kw}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fail(cls, evidence, *, retryable, needs_human=False, retry_after=None):
    ev = {"class": cls, "evidence": evidence[-EVIDENCE_CAP:], "retryable": retryable}
    sys.stderr.write(f"scraper_lane {cls}: {evidence[-EVIDENCE_CAP:]}\n")
    sys.stderr.flush()
    if needs_human:
        ev["needs_human"] = True
    if retry_after is not None:
        ev["retry_after"] = retry_after
    emit("error", **ev)
    return 0


def classify_failure(blob):
    """rc!=0 → (class, retryable, needs_human)。顺序即优先级。

    删除证据只在产出内容上判（connector z_store delguard → rc4 同层）——
    工具 stderr 里的删除签名样文本不是墓碑证据（枚举页会提到已删条目），
    防把活内容按 stderr 误判成 permanent 90d。
    """
    if any(t in blob for t in AUTH_TEXT) or AUTH_RE.search(blob):
        return "auth_expired", False, True
    if any(t in blob for t in CHALLENGE_TEXT) or CHALLENGE_RE.search(blob):
        return "challenge_needed", False, True
    if RATE_RE.search(blob):
        return "rate_limited", True, False
    if STATUS_403_RE.search(blob):
        # 无更明证据的 403：知乎语境是风控/登录类，绝不能进 lane breaker
        return "challenge_needed", False, True
    return "transient", True, False


def retry_after_of(blob):
    m = RETRY_AFTER_RE.search(blob)
    return int(m.group(1)) if m else None


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def normalize_target(raw):
    """zhuanlan 专栏短链 → www.zhihu.com/column/<slug>（zhihu-get:483-485 平价）。"""
    if "zhuanlan.zhihu.com/" in raw:
        return "https://www.zhihu.com/column/" + raw.split("zhuanlan.zhihu.com/", 1)[1]
    return raw


def produced_files(stage):
    if not stage.is_dir():
        return []
    return sorted(p for p in stage.rglob("*") if p.is_file())


def run_tool(argv, budget_s):
    """Spawn with stdin=DEVNULL（防任何交互提示挂住车道）。
    Returns (rc|None, out_tail, err_tail, timed_out, spawn_err)."""
    try:
        p = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=True,
        )
    except OSError as e:
        return None, "", "", False, str(e)
    try:
        out, err = p.communicate(timeout=budget_s)
        return p.returncode, out[-8192:], err[-8192:], False, None
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None, "", "", True, None


def main():
    try:
        req = json.loads(next(line for line in sys.stdin if line.strip()))
    except Exception as e:
        emit(
            "error",
            **{
                "class": "protocol_violation",
                "evidence": f"stdin JSON: {e}",
                "retryable": False,
            },
        )
        return RC_SKIP

    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    params = ident.get("params") or {}
    raw = ident.get("raw") or ""
    if ident.get("kind") not in KINDS or not raw:
        print(
            f"scraper_lane: skip kind={ident.get('kind')!r} raw={raw!r}",
            file=sys.stderr,
        )
        return RC_SKIP

    if not shutil.which(TOOL):
        print(f"scraper_lane: {TOOL} 缺席 → dep-skip", file=sys.stderr)
        return RC_SKIP

    target = normalize_target(raw)
    settings = os.environ.get("ZHIHU_SETTINGS") or str(
        Path(DEFAULT_SETTINGS).expanduser()
    )

    adir = Path(ctx.get("artifact_dir") or (ctx.get("journal_dir", ".") + "/artifacts"))
    adir.mkdir(parents=True, exist_ok=True)
    stage = adir / STAGE_NAME
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)

    argv = [TOOL, "fetch", target, "-s", settings, "-o", str(stage)]
    if truthy(params.get("comments")):
        argv.append("--comments")
    budget_s = max((ctx.get("budget_ms") or 120000) / 1000 - 1.0, 1.0)
    emit("progress", msg=f"zhihu-scraper fetch {target}", argv=argv)
    rc, out, err, timed_out, spawn_err = run_tool(argv, budget_s)

    for line in err.splitlines()[-STDERR_FORWARD_LINES:]:
        sys.stderr.write(line[:400] + "\n")
    sys.stderr.flush()

    if timed_out:
        shutil.rmtree(stage, ignore_errors=True)
        return fail(
            "budget_exceeded",
            f"tool exceeded budget_ms={ctx.get('budget_ms')}",
            retryable=True,
        )
    if spawn_err is not None:
        shutil.rmtree(stage, ignore_errors=True)
        return fail("lane_crash", f"spawn: {spawn_err}", retryable=True)

    if rc != 0:
        blob = f"{err}\n{out}"
        cls, retryable, human = classify_failure(blob)
        evidence = (err.strip() or out.strip() or f"{TOOL} rc={rc}")[-EVIDENCE_CAP:]
        ra = retry_after_of(blob) if cls == "rate_limited" else None
        shutil.rmtree(stage, ignore_errors=True)
        return fail(
            cls,
            evidence,
            retryable=retryable,
            needs_human=human,
            retry_after=ra,
        )

    files = produced_files(stage)
    if not files:
        return fail(
            "noresults",
            f"rc=0 but no files under {STAGE_NAME}; stdout: {out.strip()[-300:]}",
            retryable=False,
        )

    items = []
    for p in files:
        size = p.stat().st_size
        it = {"path": str(p), "name": p.relative_to(stage).as_posix(), "bytes": size}
        if size < SHA256_CAP:
            it["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        items.append({"path": it["path"], "name": it["name"], "bytes": size})
        emit("artifact", **it)
    emit("result", items=items, via="zhihu-scraper")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # lane 内部崩溃：报 lane_crash 而非裸 traceback
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
