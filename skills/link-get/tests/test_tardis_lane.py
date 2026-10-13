"""test_tardis_lane.py — packs/zhihu/lanes/tardis_lane.py 离线自测。

stub tardis 是 FILE 控制（stub 同目录 rc/files/stderr/capture.jsonl）——
engine lane_env 白名单会滤掉 STUB_* env，文件控制让直连与 engine 两条
路径共享同一套罐装现场。覆盖 rc→terminal 映射全行（0/2/3/4/5/other）、
dep 缺席 rc10、LGC_OFF=1 注入、argv 序、dir-diff 收 artifacts、
sibling-of-zhihu-get 解析、fetch-engine lane-run/conformance 真跑。
全程无真实网络——stub 不连接。

Run:
  TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest python -m pytest \
    skills/link-get/tests/test_tardis_lane.py -x -q
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LANE = ROOT / "packs" / "zhihu" / "lanes" / "tardis_lane.py"
ENGINE = ROOT / "scripts" / "fetch_engine.py"
TMPBASE = os.path.expanduser("~/.cache")

# stub zhihu-tardis：argv <url> -o <adir>；同目录 rc 文件定出口码（缺省 0），
# files 逗号清单落盘到 adir，stderr 文件写诊断；调用现场记 capture.jsonl。
STUB = """#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.realpath(__file__))

def rd(n, d=""):
    p = os.path.join(here, n)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else d

adir = ""
if "-o" in sys.argv:
    adir = sys.argv[sys.argv.index("-o") + 1]
with open(os.path.join(here, "capture.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "argv": sys.argv[1:],
        "LGC_OFF": os.environ.get("LGC_OFF"),
        "LGC_WAIT": os.environ.get("LGC_WAIT"),
    }) + "\\n")
for name in rd("files").split(","):
    name = name.strip()
    if name and adir:
        fp = os.path.join(adir, name)
        os.makedirs(os.path.dirname(fp) or adir, exist_ok=True)
        with open(fp, "w") as g:
            g.write("stub content " + name)
err = rd("stderr")
if err:
    sys.stderr.write(err)
sys.exit(int(rd("rc", "0").strip() or "0"))
"""


@pytest.fixture
def rig():
    home = tempfile.mkdtemp(prefix="tardis-lane-", dir=TMPBASE)
    bindir = os.path.join(home, "bin")
    os.makedirs(bindir)
    stub = os.path.join(bindir, "zhihu-tardis")
    with open(stub, "w") as f:
        f.write(STUB)
    os.chmod(stub, 0o755)
    # stub zhihu-get：只为 sibling-of-real-connector 解析提供锚点
    zg = os.path.join(bindir, "zhihu-get")
    with open(zg, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(zg, 0o755)
    adir = os.path.join(home, "artifacts")
    jdir = os.path.join(home, "job")
    os.makedirs(adir)
    os.makedirs(jdir)
    env = dict(os.environ)
    env["TARDIS_BIN"] = stub
    env["PATH"] = bindir + os.pathsep + env["PATH"]
    yield {
        "home": home,
        "bindir": bindir,
        "stub": stub,
        "adir": adir,
        "jdir": jdir,
        "env": env,
    }
    shutil.rmtree(home, ignore_errors=True)


def ctl(rig, name, content):
    p = Path(rig["bindir"]) / name
    if content is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(str(content))


def run_lane(
    rig, raw="https://zhuanlan.zhihu.com/p/123", budget_ms=30000, env_extra=None
):
    req = {
        "job_id": "t-lane",
        "identity": {"raw": raw, "key": "art:123", "kind": "art", "params": {}},
        "ctx": {
            "artifact_dir": rig["adir"],
            "journal_dir": rig["jdir"],
            "budget_ms": budget_ms,
            "cred_handle": "",
            "key": "art:123",
        },
    }
    env = dict(rig["env"])
    env.update(env_extra or {})
    p = subprocess.run(
        [sys.executable, str(LANE)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    events = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    return p, events


def terminals(events):
    return [e for e in events if e.get("type") in ("result", "error", "data")]


def captured(rig):
    cap = Path(rig["bindir"]) / "capture.jsonl"
    return [json.loads(x) for x in cap.read_text().splitlines()] if cap.exists() else []


# ------------------------------------------------------- rc → terminal 映射


def test_rc0_result_items(rig):
    """rc0 + 新产物 → artifact 事件先行、result 终态，items 限定 adir 内新文件。"""
    Path(rig["adir"], "pre-existing.md").write_text("old")
    ctl(rig, "rc", 0)
    ctl(rig, "files", "slug--123.md,sub/deep.md")
    p, ev = run_lane(rig)
    assert p.returncode == 0, p.stderr
    term = terminals(ev)
    assert len(term) == 1, ev
    assert term[0]["type"] == "result", ev
    names = sorted(i["name"] for i in term[0]["items"])
    assert names == ["deep.md", "slug--123.md"], term
    for it in term[0]["items"]:
        rp = Path(it["path"]).resolve()
        assert Path(rig["adir"]).resolve() in rp.parents, it
        assert it["name"], it
        assert it["bytes"] > 0, it
    arts = [e for e in ev if e.get("type") == "artifact"]
    assert {a["name"] for a in arts} == {"slug--123.md", "deep.md"}
    assert "sha256" in arts[0]


def test_rc0_empty_noresults(rig):
    """rc0 但 dir-diff 空 → noresults（shim 平价），retryable=False。"""
    ctl(rig, "rc", 0)
    p, ev = run_lane(rig)
    assert p.returncode == 0
    term = terminals(ev)
    assert len(term) == 1, ev
    assert term[0]["type"] == "error", ev
    assert term[0]["class"] == "noresults"
    assert term[0]["retryable"] is False


def test_rc2_silent_skip(rig):
    """rc2 = URL 形状不覆盖 → rc10 静默跳过，无终态行。
    connector lanes_run 对 tardis 任何失败豁免 z_lfail——若发 notcovered
    终态反而落 30d lane×key note，超出 connector 语义。"""
    ctl(rig, "rc", 2)
    ctl(rig, "stderr", "tardis 只覆盖单篇文章与单条回答\n")
    p, ev = run_lane(rig, raw="https://www.zhihu.com/question/555")
    assert p.returncode == 10, (p.returncode, p.stdout, p.stderr)
    assert terminals(ev) == [], ev
    assert "rc=2" in p.stderr


def test_rc3_notcovered(rig):
    """rc3 = 未镜像 → notcovered 终态（zhihu-tardis:426 内部 z_lnote tardis-miss
    30d 在 LGC_OFF 下已死；engine 的 notcovered→lane_note(base_key) 等价复现）。"""
    ctl(rig, "rc", 3)
    ctl(rig, "stderr", "HTTP 302\n")
    p, ev = run_lane(rig)
    assert p.returncode == 0, (p.returncode, p.stdout)
    term = terminals(ev)
    assert len(term) == 1, ev
    assert term[0]["type"] == "error", ev
    assert term[0]["class"] == "notcovered", ev
    assert term[0]["retryable"] is False


def test_rc4_permanent(rig):
    """rc4 = 删除墓碑 → permanent（STOP_CLASS），retryable=False。"""
    ctl(rig, "rc", 4)
    ctl(rig, "stderr", "内容已删除\n")
    p, ev = run_lane(rig)
    assert p.returncode == 0
    term = terminals(ev)
    assert len(term) == 1, ev
    assert term[0]["class"] == "permanent", ev
    assert term[0]["retryable"] is False


def test_rc5_transient_stderr_evidence(rig):
    """rc5 = 车道瞬时故障 → transient，evidence 取 stderr 尾部。"""
    ctl(rig, "rc", 5)
    ctl(rig, "stderr", "tardis 车道瞬时故障（HTTP 429）\n")
    p, ev = run_lane(rig)
    assert p.returncode == 0
    term = terminals(ev)
    assert len(term) == 1, ev
    assert term[0]["class"] == "transient", ev
    assert term[0]["retryable"] is True
    assert "429" in term[0]["evidence"]


def test_other_rc_transient(rig):
    """映射外 rc（如 7）一律 transient。"""
    ctl(rig, "rc", 7)
    p, ev = run_lane(rig)
    assert p.returncode == 0
    term = terminals(ev)
    assert len(term) == 1, ev
    assert term[0]["class"] == "transient", ev


# ------------------------------------------------------- spawn 契约


def test_argv_and_lgc_off(rig):
    """调用形态 <tardis> <raw> -o <adir>；子进程 env 强制 LGC_OFF=1。"""
    ctl(rig, "rc", 3)
    url = "https://www.zhihu.com/question/1/answer/9"
    p, _ = run_lane(rig, raw=url)
    assert p.returncode == 0
    caps = captured(rig)
    assert len(caps) == 1, caps
    assert caps[0]["argv"] == [url, "-o", rig["adir"]], caps
    assert caps[0]["LGC_OFF"] == "1", caps


def test_stderr_forwarded_to_lane_stderr(rig):
    """tardis stderr → lane stderr 副通道（runner 收 stderr.log）。"""
    ctl(rig, "rc", 5)
    ctl(rig, "stderr", "diag-line\n")
    p, _ = run_lane(rig)
    assert "diag-line" in p.stderr


@pytest.mark.parametrize(
    "ident",
    [
        {"raw": "", "kind": "art"},  # raw 空 → skip
        {"raw": "https://www.zhihu.com/question/1", "kind": "q"},  # kind 闸
        {"raw": "https://zhuanlan.zhihu.com/p/1"},  # kind 缺席 → skip
    ],
)
def test_skip_rc10(rig, ident):
    """kind∉{ans,art} 或 raw 空 → rc10 静默跳，无终态行（兄弟 lane 同则）。"""
    req = {
        "job_id": "t-lane",
        "identity": ident,
        "ctx": {
            "artifact_dir": rig["adir"],
            "journal_dir": rig["jdir"],
            "budget_ms": 30000,
        },
    }
    p = subprocess.run(
        [sys.executable, str(LANE)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env=rig["env"],
    )
    assert p.returncode == 10
    ev = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    assert ev == []


def test_missing_tardis_rc10(rig, monkeypatch, capsys):
    """tardis 三处定位全落空 → rc10，stdout 零事件。"""
    spec = importlib.util.spec_from_file_location("tardis_lane", LANE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "find_tardis", lambda: None)
    req = {
        "identity": {"raw": "https://zhuanlan.zhihu.com/p/1", "kind": "art"},
        "ctx": {"artifact_dir": rig["adir"], "journal_dir": rig["jdir"]},
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(req) + "\n"))
    rc = mod.main()
    out = capsys.readouterr().out
    assert rc == 10
    assert not out.strip()


def test_find_tardis_candidates(rig, monkeypatch):
    """定位序：TARDIS_BIN → zhihu-get 兄弟 → which → 兜底；全非 → None。"""
    spec = importlib.util.spec_from_file_location("tardis_lane", LANE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # TARDIS_BIN 在场即中
    monkeypatch.setenv("TARDIS_BIN", rig["stub"])
    assert mod.find_tardis() == rig["stub"]
    # TARDIS_BIN 坏 + which 缺席 + 兜底坏 → None
    monkeypatch.setenv("TARDIS_BIN", "/nonexistent/tardis")
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    monkeypatch.setattr(mod, "FALLBACK_TARDIS", "/nonexistent/fallback")
    assert mod.find_tardis() is None
    # TARDIS_BIN 坏但兜底可执行 → 兜底中（fallthrough）
    monkeypatch.setattr(mod, "FALLBACK_TARDIS", rig["stub"])
    assert mod.find_tardis() == rig["stub"]


# ------------------------------------------------------- engine 集成面


def test_lane_run_under_engine(rig, tmp_path):
    """engine lane_env 白名单滤掉 TARDIS_BIN → lane 走 PATH 上 stub
    zhihu-get 的 sibling 解析到 stub tardis → result + confinement 通过。"""
    ctl(rig, "rc", 0)
    ctl(rig, "files", "real--1.md")
    env = dict(rig["env"])
    env["FETCH_ENGINE_JOBS"] = str(Path(rig["home"]) / "jobs")
    req = {
        "identity": {
            "raw": "https://zhuanlan.zhihu.com/p/1",
            "key": "art:1",
            "kind": "art",
            "params": {},
        }
    }
    p = subprocess.run(
        [sys.executable, str(ENGINE), "lane-run", str(LANE), "-"],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["outcome"] == "result", out
    assert out["items"][0]["name"] == "real--1.md", out
    caps = captured(rig)
    assert len(caps) == 1, caps
    assert caps[0]["LGC_OFF"] == "1", caps


def test_conformance_under_engine(rig, tmp_path):
    """fetch-engine conformance：lane ABI §11 不变量全过。"""
    ctl(rig, "rc", 0)
    ctl(rig, "files", "conf--1.md")
    env = dict(rig["env"])
    env["FETCH_ENGINE_JOBS"] = str(Path(rig["home"]) / "jobs")
    p = subprocess.run(
        [sys.executable, str(ENGINE), "conformance", str(LANE), "--kind", "art"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "FAIL" not in p.stdout, p.stdout
