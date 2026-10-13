#!/usr/bin/env python3
"""monolith_shim.py — wrap a legacy connector as a single JSONL lane (lane-abi §10).

stdin : one JSON object {job_id, identity{raw,key,kind,params}, ctx{...}}
stdout: JSONL events; exactly one terminal {type:result|error|data}
env   : MONOLITH_CONF = JSON {connector, argv, flag_params, kinds, pack_dir,
                              env_passthrough}
rc    : 0 terminal emitted / 10 skipped / 1 shim-internal failure
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

RC_CLASS = {2: "protocol_violation", 3: "notcovered", 4: "permanent", 5: "transient"}


def emit(type_, **kw):
    sys.stdout.write(json.dumps({"type": type_, **kw}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def die(cls, evidence, rc=0, retryable=True, **kw):
    emit("error", **{"class": cls, "evidence": evidence, "retryable": retryable, **kw})
    return rc


def snap(d):
    d = Path(d)
    if not d.is_dir():
        return {}
    return {
        p: (s.st_size, s.st_mtime_ns)
        for p in d.rglob("*")
        if p.is_file()
        for s in [p.stat()]
    }


def expand_argv(template, ident, ctx):
    url = ident.get("raw", "")
    key = ident.get("key", "")
    params = ident.get("params") or {}
    out = []
    for tok in template:
        t = tok.replace("{url}", url).replace("{key}", key)
        t = t.replace("{artifact_dir}", ctx.get("artifact_dir", ""))
        t = t.replace("{journal_dir}", ctx.get("journal_dir", ""))
        t = t.replace("{kind}", ident.get("kind", ""))
        for k, v in params.items():
            t = t.replace("{param:" + str(k) + "}", str(v))
        out.append(t)
    for k, flag in (CONF.get("flag_params") or {}).items():
        v = params.get(k)
        # bare = True（--param k）或字符串 "true"；valued 原样带出值——
        # "1" 不能算 bare，否则 --lecture 1 丢值成裸旗
        if v is True or (isinstance(v, str) and v.lower() == "true"):
            out.append(flag)
        elif isinstance(v, str) and v.lower() in ("false", "0", "no", "off"):
            continue  # 显式假值不带旗——"no_cache=false" 不该发 --no-cache false
        elif v not in (None, False, ""):
            sv = str(v)
            if sv.startswith("-"):
                # 值以 - 开头：两参形会被 connector 当新旗标吞（argv 注入）
                out.append(f"{flag}={sv}")
            else:
                out += [flag, sv]
    flag = (CONF.get("kind_flags") or {}).get(ident.get("kind"))
    if flag:
        out.append(flag)
    return out


CONF = {}


def main():
    try:
        CONF.update(json.loads(os.environ.get("MONOLITH_CONF") or "{}"))
    except json.JSONDecodeError as e:
        return die("protocol_violation", f"MONOLITH_CONF: {e}", retryable=False)
    try:
        req = json.loads(next(line for line in sys.stdin if line.strip()))
    except Exception as e:
        return die("protocol_violation", f"stdin JSON: {e}", rc=10, retryable=False)

    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    kinds = CONF.get("kinds") or []
    if kinds and ident.get("kind") not in kinds:
        return die(
            "notcovered",
            f"kind {ident.get('kind')!r} not in {kinds}",
            rc=10,
            retryable=False,
        )
    if not ident.get("raw"):
        return die("notcovered", "identity.raw missing", rc=10, retryable=False)

    connector = CONF.get("connector", "")
    conn_path = Path(connector)
    if not conn_path.is_absolute():
        conn_path = Path(CONF.get("pack_dir", ".")) / connector
    if not conn_path.exists():
        # fall back to PATH lookup
        from shutil import which

        found = which(connector)
        if not found:
            return die(
                "dep_absent", f"connector {connector} not found", retryable=False
            )
        conn_path = Path(found)

    adir = Path(ctx.get("artifact_dir") or (ctx.get("journal_dir", ".") + "/artifacts"))
    adir.mkdir(parents=True, exist_ok=True)
    argv = [str(conn_path), *expand_argv(CONF.get("argv") or ["{url}"], ident, ctx)]

    env = dict(os.environ)
    if CONF.get("lgc_off", True):
        env["LGC_OFF"] = "1"
    for name in CONF.get("env_passthrough") or []:
        if name in os.environ:
            env[name] = os.environ[name]

    budget = (ctx.get("budget_ms") or 120000) / 1000
    emit("progress", msg=f"spawn {conn_path.name}", argv=argv[1:])
    before = snap(adir)
    t0 = time.monotonic()
    try:
        # connector 继承 shim 的进程组（engine 为 lane 建的组）——自开 session
        # 会逃进新组：engine killpg 杀 lane 时 connector 成孤儿无界跑
        p = subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as e:
        return die("lane_crash", f"spawn: {e}")
    try:
        out, err = p.communicate(timeout=budget)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        # 先广播终态再灭全组（connector+后代+self 同组）——killpg 落了自己也死，
        # 终态已 flush 进 stdout，engine 照常分类
        emit(
            "error",
            **{
                "class": "budget_exceeded",
                "evidence": f"connector exceeded budget_ms={int(budget * 1000)}",
                "retryable": True,
            },
        )
        try:
            if os.getpgrp() == os.getpid():
                os.killpg(os.getpgrp(), signal.SIGKILL)
            else:
                # 非组长（手工裸跑调试形）：killpg 会连坐调用方进程组——只杀 connector
                p.kill()
        except (ProcessLookupError, PermissionError):
            p.kill()
        p.communicate()
        return 0

    # connector diagnostics -> lane stderr side-channel (runner captures)
    for line in (err or "").splitlines():
        sys.stderr.write(line[:400] + "\n")
    lane = None
    import re

    m = re.search(r"已存 \S+（(\w+)）", out or "")
    if m:
        lane = m.group(1)
        emit("call", tool=lane, note="connector-internal lane")

    new = [p for p, meta in snap(adir).items() if p not in before or before[p] != meta]
    for p in sorted(new):
        it = {"path": str(p), "name": p.name, "bytes": p.stat().st_size}
        if p.stat().st_size < 64 * 1024 * 1024:
            it["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        emit("artifact", **it)

    if rc == 0:
        if not new:
            return die(
                "noresults",
                f"rc=0 but no new artifact; stdout: {(out or '').strip()[-300:]}",
                retryable=False,
            )
        emit(
            "result",
            items=[
                {"path": str(p), "name": p.name, "bytes": p.stat().st_size}
                for p in sorted(new)
            ],
            elapsed_ms=int((time.monotonic() - t0) * 1000),
            via=lane or conn_path.name,
        )
        return 0
    # lane rc_map 覆盖默认表（如 tardis rc2=不覆盖 → notcovered 而非违例）
    rcmap = RC_CLASS | {int(k): v for k, v in (CONF.get("rc_map") or {}).items()}
    cls = rcmap.get(rc, "transient")
    return die(
        cls,
        ((err or "").strip() or (out or "").strip() or f"connector rc={rc}")[-400:],
        retryable=cls in ("transient", "notcovered"),
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        try:
            emit(
                "error",
                **{
                    "class": "lane_crash",
                    "evidence": f"shim-internal: {e!r}",
                    "retryable": True,
                },
            )
        finally:
            sys.exit(1)
