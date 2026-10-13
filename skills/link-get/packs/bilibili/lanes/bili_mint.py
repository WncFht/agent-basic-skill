#!/usr/bin/env python3
"""bili_mint meta-lane — refresh-cookies.sh bilibili 臂重铸 bili 凭证域。

writes_cred=bili（pack.toml 声明）：脚本能写 ~/.config/link-get/cookies/
bilibili.txt + ~/BBDown.data——meta-lane 凭证安装权（lane-abi §8 唯一
artifact_dir 外写例外，仅限 cred store 指定路径）。lane 自身永不读凭证
内容（只 stat mtime/size），cookie 值永不进 journal/stdout/stderr。

复用决策（任务硬性要求）：scripts/refresh-cookies.sh 原生支持
`refresh-cookies.sh bilibili` 单臂——SCOPE case 块 zhihu|all 与
bilibili|all 相互独立，传 bilibili 时 zhihu 臂整体不触发。提取链
（scp extractor→ssh 解 keychain→scp 回→chmod600→BBDown.data 重写→
nav API 验登）单源维护，lane spawn 它而非重实现。REFRESH_COOKIES env
可换脚本（CANVAS_GET 平价），COOKIE_HOST 换源主机（脚本原生 knob）。

终态：{type:data} mint 报告（文件路径/bytes/age_s、isLogin/uname、elapsed）。
error classes：dep_absent（缺 ssh/scp、fht-mba 不可达、脚本缺席——依赖
缺位不记账，permission denied 加 needs_human）；transient（脚本其余故障
——fail_note=false 不上账，remint 不被 lane×key 锁死）；auth_expired
（铸出但 isLogin≠True → needs_human：fht-mba Chrome 重登后再铸；
cred8 域账轮换自愈见 pack.toml 键注）；challenge_needed（风控类输出）。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# packs/bilibili/lanes → parents[3] = skills/link-get（canvas _lib 同深度惯例）
DEFAULT_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "refresh-cookies.sh"
HOST = os.environ.get("COOKIE_HOST") or "fht-mba"
CRED_TARGETS = (
    ("bilibili_txt", "~/.config/link-get/cookies/bilibili.txt"),
    ("bbdown_data", "~/BBDown.data"),
)
# ssh 传输层错误指纹 → dep_absent（链路/主机缺位是 dep 不是内容瞬时）
SSH_DEP_MARKERS = (
    "could not resolve hostname",
    "operation timed out",
    "connection timed out",
    "connection refused",
    "no route to host",
    "permission denied",
    "host key verification failed",
)
# B 站风控/挑战指纹 → challenge_needed（撞到就别 hammer——12h lane 账冷却）。
# 必须避开脚本自身验登行「登录验证:」——"验证"/"risk" 类宽词会全量误报。
CHALLENGE_MARKERS = ("-412", "-352", "风控", "captcha", "challenge")


def emit(ev):
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def die(cls, evidence, retryable=None, needs_human=False):
    """终态 error——恰好一条终态行，然后 rc0 退出（lane-abi §4）。"""
    emit(
        {
            "type": "error",
            "class": cls,
            "evidence": evidence,
            "retryable": (
                cls in ("transient", "auth_expired", "rate_limited")
                if retryable is None
                else retryable
            ),
            "needs_human": needs_human,
        }
    )
    sys.exit(0)


def _truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def budget_s(ctx):
    try:
        return max(5.0, (int(ctx.get("budget_ms") or 180000) - 2000) / 1000)
    except (TypeError, ValueError):
        return 178.0


def main():
    req = json.loads(sys.stdin.readline())
    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    # 自保闸：kind!=mint 且请求未带 mint 旗标 = 非 mint 流量被错路由进来
    # ——rc10 裸退（无终态行的合法 skip，engine 记 skipped 不上账）；
    # 宁可 dep_absent 也不在普通抓取上误铸凭证。
    params = ident.get("params") or {}
    if ident.get("kind") != "mint" and not _truthy(params.get("mint")):
        sys.stderr.write(
            f"bili_mint: refuse non-mint request kind={ident.get('kind')!r}\n"
        )
        sys.exit(10)
    script = os.environ.get("REFRESH_COOKIES") or str(DEFAULT_SCRIPT)

    # needs 自查：engine admit 已按 needs.tools 闸（→dep_absent 不发车）；
    # 此层给 lane-run 裸跑/分发变更留底——ssh/scp 是 mint 链全部依赖。
    for tool in ("ssh", "scp"):
        if not shutil.which(tool):
            die(
                "dep_absent", f"缺 {tool}——mint 依赖 ssh→{HOST} 凭证链", retryable=False
            )
    if not Path(script).is_file():
        die("dep_absent", f"refresh-cookies.sh 缺席：{script}", retryable=False)

    # advisory 探针（lane-time needs）：BatchMode 禁交互（口令提问永不挂起
    # ——ssh 循环 hammer 是禁项），accept-new 免首次 host-key 确认死锁，
    # ConnectTimeout 快败。不可达 → dep_absent：ssh 链是 lane 的 dep，
    # 主机关机/tailscale 断不是 fetch transient。
    try:
        probe = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "StrictHostKeyChecking=accept-new",
                HOST,
                "true",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        die(
            "dep_absent",
            f"ssh {HOST} 探针超时（15s）——tailscale/主机在睡？",
            retryable=True,
        )
    except OSError as e:
        die("dep_absent", f"ssh 探针启动失败：{e}", retryable=False)
    if probe.returncode != 0:
        err = (probe.stderr or "").strip()[-300:]
        human = "permission denied" in err.lower()
        die(
            "dep_absent",
            f"ssh {HOST} 不可达：{err or f'rc={probe.returncode}'}；"
            + ("修 ssh 密钥/agent 后重铸" if human else "查 tailscale/主机状态"),
            retryable=not human,
            needs_human=human,
        )

    t0 = time.monotonic()
    try:
        p = subprocess.run(
            ["bash", script, "bilibili"],
            capture_output=True,
            text=True,
            timeout=budget_s(ctx),
        )
    except subprocess.TimeoutExpired:
        die("budget_exceeded", f"refresh-cookies.sh 超时（{budget_s(ctx):.0f}s）")
    except OSError as e:
        die("dep_absent", f"refresh-cookies.sh 启动失败：{e}", retryable=False)

    if p.stderr:
        sys.stderr.write(p.stderr)
        if not p.stderr.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()

    blob = (p.stderr or "") + "\n" + (p.stdout or "")
    low = blob.lower()
    if p.returncode != 0:
        tail = "\n".join(blob.splitlines()[-6:]) or f"rc={p.returncode}"
        if any(m in low for m in SSH_DEP_MARKERS):
            human = "permission denied" in low
            die(
                "dep_absent",
                f"ssh 链中断：{tail}",
                retryable=not human,
                needs_human=human,
            )
        die("transient", f"refresh-cookies.sh rc={p.returncode}：{tail}")

    # 风控挑战：脚本 rc0 但输出带挑战指纹 → challenge_needed + needs_human
    # （人手上机过验证，12h lane 账冷却自带防 hammer）。
    if any(m in low for m in CHALLENGE_MARKERS):
        die(
            "challenge_needed",
            "输出带风控/验证指纹——上 fht-mba 人工过挑战后再铸",
            retryable=False,
            needs_human=True,
        )

    # 铸后核验：脚本尾部自打 'isLogin: <bool> | uname: <u>'（nav API 验登）。
    # 显式非 True → 新 cookie 未登录 = mac 侧 Chrome 会话死——auth_expired
    # + needs_human；行缺席（验证步被跳过/输出漂移）不判死——文件证据优先。
    m = re.search(r"isLogin:\s*(\w+)", p.stdout or "")
    um = re.search(r"uname:\s*(\S+)", p.stdout or "")
    if m and m.group(1) != "True":
        die(
            "auth_expired",
            f"铸出 cookie 未登录（isLogin: {m.group(1)}）——"
            "fht-mba Chrome 重登 B 站后再 --mint",
            retryable=True,
            needs_human=True,
        )

    files = {}
    for label, path in CRED_TARGETS:
        fp = Path(path).expanduser()
        if fp.is_file():
            st = fp.stat()  # 只取 mtime/size——永不读凭证内容
            files[label] = {
                "path": str(fp),
                "bytes": st.st_size,
                "age_s": int(time.time() - st.st_mtime),
            }
        else:
            files[label] = {"path": str(fp), "missing": True}
    if files["bilibili_txt"].get("missing"):
        # 脚本 rc0 但主凭证未落——mint 实际未产，报成功是误导
        die("transient", "refresh-cookies.sh rc=0 但 bilibili.txt 未写入")

    emit(
        {
            "type": "data",
            "payload": {
                "minted": files,
                "host": HOST,
                "isLogin": m.group(1) if m else None,
                "uname": um.group(1) if um else None,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            },
        }
    )


if __name__ == "__main__":
    main()
