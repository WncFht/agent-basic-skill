#!/usr/bin/env python3
"""xyzfm_mint.py — 凭证铸造 meta-lane（kind=mint / --param mint；writes_cred）。

两道：
1. refresh 快速道：token.json 在 → POST app_auth_tokens.refresh（refresh
   token 走 x-jike-refresh-token 头）→ 新 token 在响应头 → 回写。
2. QR 道：POST web-api /v1/auth/qrcode/create（x-midway-app-id 常量）→
   qrencode 渲 PNG + ANSI → 轮询 /v1/auth/qrcode/login → USED 时 token 在
   响应头 → 写 ~/.config/xyzfm/token.json（chmod 600）。

凭证纪律：token 值永不进 stdout/journal——payload 只报路径与状态（stat 层
语义，canvas_mint/bili_mint 平价）。写 cred store 是 writes_cred 唯一授权
的 artifact_dir 外写面。
"""

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

POLL_S = 2.5


def write_token(tok):
    """mkstemp(0600)+os.replace：杜绝 write→chmod 间的 umask 可读窗口与截断
    残留——并发/中断下 token.json 要么完整要么缺席，不存烂文件。"""
    _lib.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=_lib.TOKEN_PATH.parent, prefix=".token.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(tok, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, _lib.TOKEN_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clear_lane_notes():
    """铸成顺手清 xyzfm-tr 的 auth 面旧账：
    - `clear --prefix lane:xyzfm-tr:` → auth-expired/ratelimited 等 lane×key
      note（lane 键不带 cred8，旧 token 时代的 1h note 不随轮换自灭）；
      代价是同前缀 notcovered(30d) 记忆被一并清掉——换得 mint 后立刻转正，
      无转写集至多再各探一次，接受。
    - `lane hit` → breaker 行：auth_expired 同键喂的连续 fail 会让 tr 跳闸，
      只清 note 不清 breaker 则 ≤600s 内仍被 cooling 降级。
    返回 {notes, breaker} 各自 rc==0——失败如实报不谎报。"""
    lgc = os.environ.get("LGC_BIN") or shutil.which("lgc")
    out = {"notes": False, "breaker": False}
    if not lgc:
        return out
    try:
        p = subprocess.run(
            [lgc, "clear", "link-get", "--prefix", "lane:xyzfm-tr:"],
            capture_output=True,
            timeout=10,
        )
        out["notes"] = p.returncode == 0
        p = subprocess.run(
            [lgc, "lane", "link-get", "hit", "xyzfm-tr"],
            capture_output=True,
            timeout=10,
        )
        out["breaker"] = p.returncode == 0
    except (subprocess.SubprocessError, OSError):
        pass
    return out


def try_refresh(tok):
    """refresh 快速道 → 新 token dict 或 None（401/403/网络败都走 QR）。"""
    if not tok or not tok.get("refresh_token"):
        return None
    did = _lib.device_id(tok)
    status, hdrs, _body = _lib.http_post(
        f"{_lib.API}/app_auth_tokens.refresh",
        {},
        _lib.app_headers(did, refresh=tok["refresh_token"]),
        timeout=20.0,
    )
    if status != 200:
        return None
    at = hdrs.get("x-jike-access-token")
    rt = hdrs.get("x-jike-refresh-token")
    if not at:
        return None
    return {
        "access_token": at,
        "refresh_token": rt or tok["refresh_token"],
        "device_id": did,
    }


def qr_png(url, adir):
    """qrencode → PNG 产物 + ANSI 终端码（stderr 副通道，不进 stdout JSONL）。"""
    qr = shutil.which("qrencode")
    if not qr:
        return None
    png = adir / "xyzfm-login-qr.png"
    try:
        subprocess.run(
            [qr, "-o", str(png), "-s", "8", url],
            check=True,
            capture_output=True,
            timeout=15,
        )
        ansi = subprocess.run(
            [qr, "-t", "ANSIUTF8", url], capture_output=True, text=True, timeout=15
        )
        if ansi.stdout:
            _lib.eprint(ansi.stdout)
        return png
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def mint_qr(ctx):
    did = _lib.device_id(_lib.load_token() or {})
    status, _h, body = _lib.http_post(
        f"{_lib.WEB_API}/v1/auth/qrcode/create",
        {"clientId": "xyz-web"},
        {
            "x-midway-app-id": _lib.MIDWAY_APP_ID,
            "content-type": "application/json",
            "User-Agent": _lib.PAGE_UA,
        },
        timeout=20.0,
    )
    if status != 200:
        _lib.die("transient", f"qrcode/create HTTP {status}", retryable=True)
    try:
        qr = json.loads(body)
        qid, qurl = qr["id"], qr["url"]
    except Exception:
        _lib.die(
            "transient", f"qrcode/create 响应解析失败：{body[:120]!r}", retryable=True
        )

    png = qr_png(qurl, Path(ctx["artifact_dir"]))
    if png:
        _lib.artifact(png, "xyzfm-login-qr.png")
    _lib.progress(f"小宇宙 App 扫码登录：{qurl}", stage="qr")

    # budget_s 返回【秒】——预留 15s 收尾（单位错配曾把 300s 恒压成 30s）
    deadline = time.time() + max(30.0, _lib.budget_s(ctx) - 15.0)
    last = ""
    while time.time() < deadline:
        status, hdrs, body = _lib.http_post(
            f"{_lib.WEB_API}/v1/auth/qrcode/login",
            {"id": qid},
            {
                "x-midway-app-id": _lib.MIDWAY_APP_ID,
                "content-type": "application/json",
                "User-Agent": _lib.PAGE_UA,
            },
            timeout=20.0,
        )
        if status != 200:
            time.sleep(POLL_S)
            continue
        try:
            st = (json.loads(body) or {}).get("status") or ""
        except Exception:
            st = ""
        if st != last:
            _lib.progress(f"扫码状态：{st or '?'}")
            last = st
        if st == "USED":
            at = hdrs.get("x-jike-access-token")
            rt = hdrs.get("x-jike-refresh-token")
            if not at:
                _lib.die("transient", "USED 但响应头无 token", retryable=True)
            write_token(
                {"access_token": at, "refresh_token": rt or "", "device_id": did}
            )
            _lib.data(
                {
                    "status": "minted",
                    "cred": str(_lib.TOKEN_PATH),
                    "via": "qrcode",
                    "lane_notes_cleared": clear_lane_notes(),
                    "note": "token 已写盘 chmod 600，值不进日志",
                }
            )
            return
        if st in ("EXPIRED", "CANCELLED"):
            # 自家 QR 过期≠站点风控墙：retry_after=60 让 lane 账 60s 后自愈
            # （engine challenge 账默认 12h——remint 不该被冷却锁死）
            _lib.die(
                "challenge_needed",
                f"QR 状态 {st}——重跑 --mint 取新码再扫",
                retryable=True,
                retry_after=60,
                needs_human=True,
            )
        time.sleep(POLL_S)

    _lib.die(
        "challenge_needed",
        f"QR 在预算内未确认（{qurl}）——重跑 --mint 再扫",
        retryable=True,
        retry_after=60,
        needs_human=True,
    )


def main():
    req = _lib.read_req()
    ident = req["identity"]
    ctx = req["ctx"]
    Path(ctx["artifact_dir"]).mkdir(parents=True, exist_ok=True)

    # 自保闸：错路由进来的正常流量不真铸（bili_mint 平价）
    if ident.get("kind") != "mint" and not _lib.truthy(
        (ident.get("params") or {}).get("mint")
    ):
        _lib.skip("xyzfm-mint: 非 mint 流量")

    # 单飞：meta-lane 跳过 gate1 无 inflight 归并，并发 --mint 会双铸/竞写
    # token.json——flock 串行化，后至者拿到锁时走 refresh 道即安静出新对
    _lib.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _lock = open(_lib.TOKEN_PATH.parent / ".mint.lock", "a")  # noqa: SIM115
    fcntl.flock(_lock, fcntl.LOCK_EX)

    tok = _lib.load_token()
    if tok and tok.get("refresh_token"):
        _lib.progress("refresh 快速道")
        new = try_refresh(tok)
        if new:
            write_token(new)
            _lib.data(
                {
                    "status": "refreshed",
                    "cred": str(_lib.TOKEN_PATH),
                    "via": "refresh_token",
                    "lane_notes_cleared": clear_lane_notes(),
                    "note": "token 已写盘 chmod 600，值不进日志",
                }
            )
            return
        _lib.progress("refresh 失败——转 QR 道")
    else:
        _lib.progress(
            "token.json 缺席" if not tok else "token.json 无 refresh_token——QR 道"
        )

    mint_qr(ctx)


if __name__ == "__main__":
    main()
