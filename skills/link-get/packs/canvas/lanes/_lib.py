#!/usr/bin/env python3
"""_lib.py — canvas pack 原生 lane 共享助手（Lane ABI v1，references/lane-abi.md）。

两条 lane 都是薄壳：spawn canvas-get 子命令 → stdout 收进 {type:data}
payload（消费侧与直连逐字平价），stderr 原样过副通道，rc→class 映射同
zhihu lanes 分类语义。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def read_req():
    """读 stdin 单行 JSON 请求（engine 写完一行即关 stdin）。"""
    return json.loads(sys.stdin.readline())


def emit(ev):
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def die(cls, evidence, retryable=None):
    """终态 error——恰好一条终态行，然后 rc0 退出。"""
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
        }
    )
    sys.exit(0)


def canvas_get_bin():
    """canvas-get 解析序：CANVAS_GET env > PATH > 仓内相对路径。"""
    env = os.environ.get("CANVAS_GET")
    if env:
        return env
    w = shutil.which("canvas-get")
    if w:
        return w
    # packs/canvas/lanes → skills/link-get/scripts/connectors/canvas-get
    return str(
        Path(__file__).resolve().parents[3] / "scripts" / "connectors" / "canvas-get"
    )


def classify(rc, serr):
    """canvas-get rc → lane class：PAT/401/403 一律 auth_expired（凭证域
    信号不进内容账）；rc3=无内容；rc2=用法/请求形；其余 transient。"""
    if "PAT" in serr or "HTTP 401" in serr or "HTTP 403" in serr:
        return "auth_expired"
    if rc == 3:
        return "noresults"
    if rc == 2:
        return "notcovered"  # 用法/请求形错误 ≠ 内容墓碑——90d 墓碑会毒死枚举键
    return "transient"


def budget_s(ctx):
    try:
        return max(5.0, (int(ctx.get("budget_ms") or 120000) - 2000) / 1000)
    except (TypeError, ValueError):
        return 118.0


def run_canvas_get(argv, ctx):
    """spawn canvas-get → CompletedProcess；超时/缺席转终态 error。"""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=budget_s(ctx)
        )
    except FileNotFoundError as e:
        die("dep_absent", f"canvas-get 不可执行：{e}")
    except subprocess.TimeoutExpired:
        die("budget_exceeded", f"canvas-get 超时（budget={budget_s(ctx):.0f}s）")


def finish(p):
    """统一收尾：stderr 过副通道；rc0 → 调用方发终态；非 0 → 分类 error。"""
    if p.stderr:
        sys.stderr.write(p.stderr)
        if not p.stderr.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()
    if p.returncode == 0:
        return
    tail = "\n".join((p.stderr or "").splitlines()[-6:]) or f"rc={p.returncode}"
    die(classify(p.returncode, p.stderr or ""), tail)
