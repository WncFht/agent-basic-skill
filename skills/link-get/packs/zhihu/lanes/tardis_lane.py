#!/usr/bin/env python3
"""tardis_lane.py — zhihu tardis 镜像车道（lane-ABI v1 原生实现，非 monolith shim）。

stdin : 一行 JSON {job_id, identity{raw,key,kind,params,...},
                   ctx{artifact_dir,journal_dir,budget_ms,cred_handle,key}}
stdout: JSONL events（progress/artifact/result/error），恰好一个终态行
rc    : 0=已自报终态 / 10=silent skip（tardis 缺席或 raw 空，无终态行的合法跳过）

zhihu-tardis 出口码契约（对照 skills/link-get/scripts/connectors/zhihu-tardis 核实）：
  rc0 → -o 目录产物 → dir-diff 收 items → result
  rc2 → URL 形状不覆盖（非 /p/、非 /answer/、id 解不出）→ rc10 静默跳过
        【connector lanes_run 对 tardis 失败一律豁免 z_lfail——不落 note 不熔断】
  rc3 → 未镜像（HTTP 302/404）→ notcovered
        【zhihu-tardis:426 内部 z_lnote tardis-miss 30d 在 LGC_OFF 下已死；
         engine 的 notcovered→lane_note(base_key,30d) 等价复现该负缓存】
  rc4 → 删除墓碑 → permanent（STOP_CLASS）
  rc5 → 车道瞬时故障（uv 缺席、403/412/429/5xx/000、验证页、解析/改名失败）
        → transient（stderr 尾部为 evidence）
  其他 → transient

env overlay：LGC_OFF=1 —— CRITICAL。tardis 自带的 probe/store/neg/lane-note
循环以其内部 KIND:ID 为键；engine 现在独占全部缓存/记账，必须掐断旧路径
（z_probe/z_lane/z_lnote/z_lfail/z_store 在 LGC_OFF 下全部 no-op，
连带 --wait 类等待也一并失效，无需另传 LGC_WAIT）。

tardis 定位序：$TARDIS_BIN → which(zhihu-get) 真实路径的兄弟脚本 →
仓库绝对路径兜底 → 全无 → rc10。
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

FALLBACK_TARDIS = str(
    Path(__file__).resolve().parents[3] / "scripts" / "connectors" / "zhihu-tardis"
)
SHA256_CAP = 64 * 1024 * 1024


def emit(type_, **kw):
    sys.stdout.write(json.dumps({"type": type_, **kw}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def die(cls, evidence, rc=0, retryable=True, **kw):
    emit("error", **{"class": cls, "evidence": evidence, "retryable": retryable, **kw})
    return rc


def snap(d):
    """artifact_dir 文件快照 {path: (size, mtime_ns)}——rc0 后与 pre-run 比对新产物。"""
    d = Path(d)
    if not d.is_dir():
        return {}
    return {
        p: (s.st_size, s.st_mtime_ns)
        for p in d.rglob("*")
        if p.is_file()
        for s in [p.stat()]
    }


def find_tardis():
    """定位 zhihu-tardis：env 覆盖 → zhihu-get 真实路径兄弟 → 绝对兜底。"""
    cands = []
    if os.environ.get("TARDIS_BIN"):
        cands.append(os.environ["TARDIS_BIN"])
    zg = shutil.which("zhihu-get")
    if zg:
        try:
            cands.append(str(Path(zg).resolve().parent / "zhihu-tardis"))
        except OSError:
            pass
    zt = shutil.which("zhihu-tardis")
    if zt:
        cands.append(zt)
    cands.append(FALLBACK_TARDIS)
    for c in cands:
        p = Path(c)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def main():
    try:
        req = json.loads(next(line for line in sys.stdin if line.strip()))
    except Exception as e:
        return die("protocol_violation", f"stdin JSON: {e}", rc=10, retryable=False)

    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    raw = ident.get("raw") or ""
    # 覆盖 kind：ans（/answer/）、art（/p/）——其余 kind 无产能（兄弟 lane 同则）
    if ident.get("kind") not in ("ans", "art") or not raw:
        sys.stderr.write(f"tardis_lane: skip kind={ident.get('kind')!r} raw={raw!r}\n")
        return 10

    tardis = find_tardis()
    if not tardis:
        sys.stderr.write(
            "tardis_lane: zhihu-tardis 缺席"
            "（TARDIS_BIN/zhihu-get 兄弟/绝对兜底均不可执行）\n"
        )
        return 10

    adir = Path(ctx.get("artifact_dir") or (ctx.get("journal_dir", ".") + "/artifacts"))
    adir.mkdir(parents=True, exist_ok=True)
    argv = [tardis, raw, "-o", str(adir)]
    env = dict(os.environ)
    env["LGC_OFF"] = "1"  # engine 独占缓存/记账：掐断 tardis 内部 probe/store/neg
    budget = (ctx.get("budget_ms") or 120000) / 1000

    emit("progress", msg=f"spawn {Path(tardis).name}", argv=argv[1:])
    before = snap(adir)
    t0 = time.monotonic()
    try:
        p = subprocess.Popen(
            argv,
            env=env,
            start_new_session=True,
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
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return die("budget_exceeded", f"tardis exceeded budget_ms={int(budget * 1000)}")

    # tardis 诊断 → lane stderr 副通道（runner 收进 <lane>.stderr.log）
    for line in (err or "").splitlines():
        sys.stderr.write(line[:400] + "\n")
    sys.stderr.flush()

    new = [p for p, meta in snap(adir).items() if p not in before or before[p] != meta]
    for p in sorted(new):
        it = {"path": str(p), "name": p.name, "bytes": p.stat().st_size}
        if p.stat().st_size < SHA256_CAP:
            it["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        emit("artifact", **it)

    tail = ((err or "").strip() or (out or "").strip() or f"tardis rc={rc}")[-400:]
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
            via="zhihu-tardis",
        )
        return 0
    if rc == 3:
        # 未镜像（302/404）：zhihu-tardis:426 内部 z_lnote tardis-miss 30d 在
        # LGC_OFF 下已死——notcovered 让 engine 记 lane×key note 复现该负缓存
        return die("notcovered", tail, retryable=False)
    if rc == 2:
        # URL 形状不覆盖（非 /p/、非 /answer/、id 解不出）：connector lanes_run
        # 对 tardis 任何失败都不记账（z_lfail 豁免）——rc10 静默跳过等价复现；
        # 若发 notcovered 终态反而落 30d lane×key note，超出 connector 语义
        sys.stderr.write(f"tardis_lane: 形状不覆盖 rc=2 {tail}\n")
        return 10
    if rc == 4:
        # 内容已删除（墓碑证据）→ permanent STOP_CLASS
        return die("permanent", tail, retryable=False)
    return die("transient", tail)


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
