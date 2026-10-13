"""test_engine.py — fetch-engine substrate tests. No real network: only
loopback http.server fixtures and fixture lanes."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import tomllib

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
LAUNCHER = ROOT / "scripts" / "fetch-engine"
FIXTURES = ROOT / "tests" / "fixtures"


def load_engine(monkeypatch, tmp_path):
    """Import fetch_engine with state roots redirected to tmp_path."""
    monkeypatch.setenv("LGC_HOME", str(tmp_path / "lgc-home"))
    monkeypatch.setenv("FETCH_ENGINE_JOBS", str(tmp_path / "jobs"))
    spec = importlib.util.spec_from_file_location("fetch_engine", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fe(tmp_path, monkeypatch):
    return load_engine(monkeypatch, tmp_path)


def run_cli(args, env_extra=None, timeout=60, cwd=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=cwd,
    )


# ---------------------------------------------------------------- units


@pytest.mark.parametrize(
    ("url", "expect"),
    [
        ("http://127.0.0.1:8877/x", "private"),
        ("http://localhost/a", "private"),
        ("http://foo.localhost/x", "private"),
        ("http://[::1]/x", "private"),
        ("http://169.254.169.254/meta", "private"),
        ("http://10.0.0.1/x", "private"),
        ("http://192.168.1.1/x", "private"),
        ("http://172.16.0.1/x", "private"),
        ("file:///etc/passwd", "scheme"),
        ("gopher://x", "scheme"),
        ("http://example.com/x", None),
        ("https://zhihu.com/answer/1", None),
    ],
)
def test_guard_url(fe, url, expect):
    r = fe.guard_url(url)
    if expect is None:
        assert r is None, r
    else:
        assert r is not None, r
        assert expect in r, r


def test_guard_url_allow_private(fe, monkeypatch):
    assert fe.guard_url("http://127.0.0.1/x", allow_private=True) is None
    assert fe.guard_url("http://127.0.0.1/x") is not None


def test_canon(fe):
    raw, err = fe.canon("HTTPS://EXAMPLE.COM:443/a?q=1#frag")
    assert err is None
    assert raw == "https://example.com/a?q=1"  # :443 stripped, fragment dropped
    raw, err = fe.canon("  ")
    assert err
    # v6 brackets 必须保住——裸写 netloc 下游 urlsplit 按 host:port 误切，SSRF 闸被绕
    raw, err = fe.canon("http://[FE80::1]/x")
    assert (raw, err) == ("http://[fe80::1]/x", None)
    assert fe.guard_url(raw) is not None
    # 裸 host/path → https 归一（connector 时代 curl 自补 scheme）；非 host 形不动
    raw, err = fe.canon("zhihu.com/p/1")
    assert (raw, err) == ("https://zhihu.com/p/1", None)
    raw, err = fe.canon("foo bar")
    assert (raw, err) == ("foo bar", None)
    # 坏端口走 error 通道，不是 traceback
    raw, err = fe.canon("http://h:abc/x")
    assert err


def test_rc_compression(fe):
    assert fe.RC_FOR_CLASS["noresults"] == 3
    assert fe.RC_FOR_CLASS["notcovered"] == 3
    assert fe.RC_FOR_CLASS["permanent"] == 4
    assert fe.RC_FOR_CLASS["transient"] == 5
    assert fe.RC_FOR_CLASS["auth_expired"] == 6
    assert fe.RC_FOR_CLASS["challenge_needed"] == 6
    assert fe.RC_FOR_CLASS["budget_exceeded"] == 7


def test_check_lane_stdout(fe):
    bad, types, terms = fe.check_lane_stdout(
        ['{"type":"progress"}', '{"type":"result","items":[]}']
    )
    assert bad == []
    assert terms == ["result"]
    bad, types, terms = fe.check_lane_stdout(["not json", '{"type":"data"}'])
    assert bad == [0]
    assert terms == ["data"]


def test_validate_artifacts(fe, tmp_path):
    adir = tmp_path / "art"
    adir.mkdir()
    good = adir / "a.md"
    good.write_text("x")
    outside = tmp_path / "b.md"
    outside.write_text("x")
    ok, bad = fe.validate_artifacts(
        [
            {"path": str(good), "name": "a.md"},
            {"path": str(outside), "name": "b.md"},
            {"path": str(good), "name": ""},
            {"path": str(good), "name": "../escape.md"},
            {"path": str(good), "name": "/abs/x.md"},
            {"path": str(good), "name": "sub/ok.md"},
        ],
        adir,
    )
    assert [i["name"] for i in ok] == ["a.md", "sub/ok.md"]
    assert len(bad) == 4


def test_delguard_scan(fe, tmp_path):
    p = tmp_path / "a.md"
    p.write_text("normal content")
    assert fe.delguard_scan([p]) is None
    p.write_text("前言 该内容已被发布者删除 后记")
    assert fe.delguard_scan([p]) == "该内容已被发布者删除"
    q = tmp_path / "b.bin"
    q.write_bytes(b"\x00" * 100)
    assert fe.delguard_scan([q]) is None  # only .md/.txt/__value__ scanned


class _SpyLgc:
    def __init__(self):
        self.calls = []

    def available(self):
        return True

    def __getattr__(self, name):
        return lambda *a, **kw: self.calls.append((name, a, kw))


def test_record_error_auth_expired(fe):
    ident = {"key": "ans:1"}
    # cred 死只记车道账（lane note + scoped breaker），内容键不落 neg——
    # 否则会毒死 connector 共享 store；never an explicit fp，lgc 自派 cred 域
    for res in (
        {"class": "auth_expired"},
        {"class": "auth_expired", "cred_fp": "deadbeef"},
    ):
        lgc = _SpyLgc()
        fe.record_error(lgc, ident, "zhcli", res)
        assert lgc.calls == [
            ("lane_note", ("zhcli", "ans:1", "auth-expired"), {"ttl": 3600}),
            ("lane_fail", ("zhcli", "ans:1", "auth-expired"), {}),
        ]


def test_record_error_scope_table(fe):
    ident = {"key": "art:9"}
    lgc = _SpyLgc()
    fe.record_error(lgc, ident, "L", {"class": "permanent"})
    fe.record_error(lgc, ident, "L", {"class": "noresults"})
    fe.record_error(lgc, ident, "L", {"class": "budget_exceeded"})
    assert lgc.calls == [
        ("neg", ("art:9", "deleted"), {}),
        ("neg", ("art:9", "unavailable"), {"ttl": 86400}),
    ]  # budget_exceeded records nothing


def test_record_error_notcovered_scope_hint(fe):
    """notcovered+scope_hint=params 不写 lane×key 墓碑——参数级拒绝不是内容覆盖判词。"""
    ident = {"key": "arxivtex:1"}
    lgc = _SpyLgc()
    fe.record_error(lgc, ident, "arxiv-tex", {"class": "notcovered"})
    fe.record_error(
        lgc, ident, "arxiv-tex", {"class": "notcovered", "scope_hint": "params"}
    )
    assert lgc.calls == [
        ("lane_note", ("arxiv-tex", "arxivtex:1", "notcovered"), {"ttl": 2592000}),
    ]


# ---------------------------------------------------------------- run_lane


def run_fixture(fe, name, tmp_path, budget_ms=10000):
    job = fe.Job(jobs_root=tmp_path / "jobs", budget_ms=budget_ms)
    ident = {"raw": "test://x", "key": "test:x", "kind": "article", "params": {}}
    lc = {"name": Path(name).stem, "exec": str(FIXTURES / name), "budget_ms": budget_ms}
    pack = type("P", (), {"dir": FIXTURES, "monolith": {}, "name": "t"})()
    res = fe.run_lane(job, pack, lc, ident, {})
    jlines = (job.dir / "journal.jsonl").read_text().splitlines()
    job.journal.close()
    return res, [json.loads(line) for line in jlines], job


def test_lane_result(fe, tmp_path):
    res, jlines, job = run_fixture(fe, "ok_lane.py", tmp_path)
    assert res["outcome"] == "result"
    assert res["items"][0]["name"] == "article--fixture.md"
    assert all(line["job_id"] == job.job_id for line in jlines)


def test_lane_data(fe, tmp_path):
    res, _, _ = run_fixture(fe, "data_lane.py", tmp_path)
    assert res["outcome"] == "data"
    assert res["payload"]["rows"][0][1] == "course-a"


def test_lane_quiet_noresults(fe, tmp_path):
    res, jlines, _ = run_fixture(fe, "quiet_lane.py", tmp_path)
    assert res["outcome"] == "error"
    assert res["class"] == "noresults"
    assert any(line.get("synthesized_terminal") for line in jlines)


def test_lane_timeout_killed(fe, tmp_path):
    t0 = time.monotonic()
    res, jlines, _ = run_fixture(fe, "sleeper_lane.py", tmp_path, budget_ms=700)
    elapsed = time.monotonic() - t0
    assert res["outcome"] == "error"
    assert res["class"] == "budget_exceeded"
    assert elapsed < 5  # killed at ~1.1s, not the lane's 60s
    assert any(line.get("killed") for line in jlines)


def test_lane_rc10_skipped(fe, tmp_path):
    res, _, _ = run_fixture(fe, "skip_lane.py", tmp_path)
    assert res["outcome"] == "skipped"


def test_lane_terminal_beats_rc10(fe, tmp_path):
    res, jlines, _ = run_fixture(fe, "badterm_lane.py", tmp_path)
    assert res["outcome"] == "result"
    assert any("rc10_after_terminal" in json.dumps(line) for line in jlines)


def test_lane_error_class(fe, tmp_path):
    res, _, _ = run_fixture(fe, "err_lane.py", tmp_path)
    assert res["outcome"] == "error"
    assert res["class"] == "transient"


def test_lane_dirty_stdout_does_not_kill(fe, tmp_path):
    res, jlines, _ = run_fixture(fe, "dirty_lane.py", tmp_path)
    assert res["outcome"] == "result"
    assert any(line.get("protocol_violation") for line in jlines)


def test_lane_stderr_captured(fe, tmp_path):
    res, _, job = run_fixture(fe, "skip_lane.py", tmp_path)
    log = job.dir / "skip_lane.stderr.log"
    assert log.exists()
    assert "not covered" in log.read_text()


# ---------------------------------------------------------------- cli


def test_launcher_finds_python(tmp_path):
    env = dict(os.environ)
    env["FETCH_ENGINE_JOBS"] = str(tmp_path / "jobs")
    p = subprocess.run(
        ["sh", str(LAUNCHER), "--version"], capture_output=True, text=True, env=env
    )
    assert p.returncode == 0
    assert "fetch-engine" in p.stdout


def test_launcher_version_gate(tmp_path):
    # FETCH_ENGINE_PYTHON pointing at a bad interpreter must be rejected
    # (simulate with /bin/true which fails the tomllib probe -> falls through
    # to a working interpreter anyway; assert we still get --version output)
    env = dict(os.environ)
    env["FETCH_ENGINE_PYTHON"] = "/bin/true"
    env["FETCH_ENGINE_JOBS"] = str(tmp_path / "jobs")
    p = subprocess.run(
        ["sh", str(LAUNCHER), "--version"], capture_output=True, text=True, env=env
    )
    assert p.returncode == 0
    assert "fetch-engine" in p.stdout


def test_selftest(tmp_path):
    p = run_cli(
        ["selftest"], {"FETCH_ENGINE_JOBS": str(tmp_path / "jobs")}, timeout=120
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "FAIL" not in p.stdout


def _deploy_pack(tmp_path, tools, probe_rc=0):
    pdir = tmp_path / "packs" / "fixp"
    (pdir / "lanes").mkdir(parents=True)
    (pdir / "pack.toml").write_text(
        '[pack]\nname = "fixp"\nns = "link-get"\n'
        "[[lanes]]\n"
        'name = "l1"\n'
        'exec = "lanes/l1.py"\n'
        f"needs = {{ tools = {tools} }}\n"
    )
    (pdir / "lanes" / "l1.py").write_text("print('{}')\n")
    (pdir / "probe.sh").write_text(
        f"#!/bin/bash\necho '  ✓ probe ran'\nexit {probe_rc}\n"
    )
    return {
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
    }


def test_selftest_deploy_pack_ok(tmp_path):
    """-p 部署体检：lane exec + tools + probe.sh 全过 → rc0。"""
    env = _deploy_pack(tmp_path, '["bash"]')
    p = run_cli(["selftest", "-p", "fixp"], env, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "== pack fixp" in p.stdout
    assert "probe ran" in p.stdout
    assert "== lgc" in p.stdout


def test_selftest_deploy_missing_tool_fails(tmp_path):
    env = _deploy_pack(tmp_path, '["definitely-missing-tool-xyzzy"]')
    p = run_cli(["selftest", "-p", "fixp"], env, timeout=60)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "✗" in p.stdout


def test_selftest_deploy_probe_fail(tmp_path):
    env = _deploy_pack(tmp_path, '["bash"]', probe_rc=1)
    p = run_cli(["selftest", "-p", "fixp"], env, timeout=60)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "probe.sh rc1" in p.stdout


def test_selftest_deploy_monolith_pack_relative_conn(tmp_path):
    """monolith connector 是 pack.dir 相对路径（如 ../../scripts/connectors/x）——
    体检须与 monolith_shim 同序解析，不能丢给 shutil.which 按 CWD 猜。"""
    pdir = tmp_path / "packs" / "fixp"
    pdir.mkdir(parents=True)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "conn.sh").write_text("#!/bin/bash\nexit 0\n")
    (pdir / "pack.toml").write_text(
        '[pack]\nname = "fixp"\nns = "link-get"\n'
        "[[lanes]]\n"
        'name = "m1"\n'
        'exec = "monolith"\n'
        'connector = "../../bin/conn.sh"\n'
    )
    env = {
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
    }
    p = run_cli(["selftest", "-p", "fixp"], env, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "connector ../../bin/conn.sh" in p.stdout


def test_selftest_deploy_unknown_pack(tmp_path):
    p = run_cli(
        ["selftest", "-p", "nosuchpack"],
        {"FETCH_ENGINE_JOBS": str(tmp_path / "jobs")},
        timeout=60,
    )
    assert p.returncode == 2


def test_selftest_deploy_bad_pack_toml_fails(tmp_path):
    """坏 pack.toml 不许被 load_packs 静默吞掉——deploy 体检要计 fail。"""
    (tmp_path / "packs" / "badp").mkdir(parents=True)
    (tmp_path / "packs" / "badp" / "pack.toml").write_text("not = [valid")
    env = {
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
    }
    p = run_cli(["selftest", "--deploy"], env, timeout=60)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "解析失败" in p.stdout


def test_selftest_deploy_route_ref_missing_lane(tmp_path):
    """[[routes]].lanes 引用未声明 lane → 体检 ✗（拼错名会让该臂静默空道）。"""
    pdir = tmp_path / "packs" / "fixp"
    (pdir / "lanes").mkdir(parents=True)
    (pdir / "pack.toml").write_text(
        '[pack]\nname = "fixp"\nns = "link-get"\n'
        "[[lanes]]\n"
        'name = "l1"\n'
        'exec = "lanes/l1.py"\n'
        "[[routes]]\n"
        'kinds = ["a"]\n'
        'lanes = ["ghost"]\n'
    )
    (pdir / "lanes" / "l1.py").write_text("print('{}')\n")
    env = {
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
    }
    p = run_cli(["selftest", "-p", "fixp"], env, timeout=60)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "ghost" in p.stdout


def test_expand_argv_valued_not_eaten(tmp_path):
    """flag_params 带值旗标 v="1" 不许塌成 bare——'--lecture 1' 丢值会让
    connector 吃到无参 --lecture（verify 实锤：v in ("true","1") 误判）。"""
    spec = importlib.util.spec_from_file_location(
        "monolith_shim", ROOT / "scripts" / "monolith_shim.py"
    )
    shim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shim)
    shim.CONF.update({"flag_params": {"lecture": "--lecture", "refresh": "--refresh"}})
    out = shim.expand_argv(
        ["{url}"], {"raw": "U", "params": {"lecture": "1", "refresh": True}}, {}
    )
    assert out == ["U", "--lecture", "1", "--refresh"]
    # 显式 --param k=true 仍算 bare（人性化兼容），bare=True 同理
    out = shim.expand_argv([], {"raw": "U", "params": {"refresh": "true"}}, {})
    assert out == ["--refresh"]


def test_kind_required_hint(tmp_path):
    """zhihu kind_required 带 kind_hint——无 kind 形态拒 rc2 时给可行动提示。"""
    p = run_cli(
        ["run", "https://www.zhihu.com/collection/123", "-p", "zhihu"],
        {"FETCH_ENGINE_JOBS": str(tmp_path / "jobs")},
    )
    assert p.returncode == 2, p.stdout + p.stderr
    assert "Collections-MCP" in p.stderr


def test_skillmd_marker_pair_count(tmp_path):
    """pack-table 标记须恰好各一对——find() 只命中首对，第二对会在绿灯下腐坏。"""
    md = tmp_path / "SKILL.md"
    md.write_text(
        "x\n<!-- pack-table:start -->\n<!-- pack-table:end -->\n"
        "<!-- pack-table:start -->\n<!-- pack-table:end -->\n"
    )
    p = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "skillmd_sync.py"),
            "--check",
            str(md),
        ],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 2
    assert "标记" in p.stderr


def test_skillmd_table_fresh():
    """SKILL.md 路由表与 packs/*/pack.toml 同步（skillmd_sync --check）。"""
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "skillmd_sync.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p.returncode == 0, p.stdout + p.stderr


def test_lane_run_bypass(tmp_path):
    p = run_cli(
        ["lane-run", str(FIXTURES / "ok_lane.py"), "-"],
        {"FETCH_ENGINE_JOBS": str(tmp_path / "jobs")},
        timeout=30,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["outcome"] == "result"
    assert Path(out["journal"]).exists()


def test_conformance_ok_lane(tmp_path):
    p = run_cli(
        ["conformance", str(FIXTURES / "ok_lane.py")],
        {"FETCH_ENGINE_JOBS": str(tmp_path / "jobs")},
    )
    assert p.returncode == 0, p.stdout
    assert "FAIL" not in p.stdout


def test_run_no_pack(tmp_path):
    p = run_cli(
        ["run", "not-a-url"],
        {
            "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
            "FETCH_ENGINE_PACKS": str(tmp_path / "no-packs"),
        },
    )
    assert p.returncode in (2, 3)


def test_run_ssrf_refused(tmp_path):
    p = run_cli(
        ["run", "http://127.0.0.1:9/x"], {"FETCH_ENGINE_JOBS": str(tmp_path / "jobs")}
    )
    assert p.returncode == 2
    assert "refused" in p.stderr


# ---------------------------------------------------------------- e2e


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><body>fixture article</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def httpd():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def make_pack(tmp_path):
    """A test pack whose lane is the ok fixture (fetches the URL itself)."""
    pdir = tmp_path / "packs" / "testpack"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(f"""
[pack]
name = "testpack"
abi = 1
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["127.0.0.1", "localhost"]
schemes = ["http"]
[identity]
keyexpr = "article:{{url}}"
[[lanes]]
name = "ok_lane"
exec = "{FIXTURES}/ok_lane.py"
budget_ms = 15000
""")
    return tmp_path / "packs"


def e2e_env(tmp_path):
    return {
        "LGC_HOME": str(tmp_path / "lgc-home"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "FETCH_ENGINE_PACKS": None,  # filled by caller
        "FETCH_ENGINE_ALLOW_PRIVATE": "1",
    }


def test_e2e_fetch_and_cache_hit(tmp_path, httpd):
    packs = make_pack(tmp_path)
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/a"
    outdir = tmp_path / "out"

    p1 = run_cli(["run", url, "-o", str(outdir)], env)
    assert p1.returncode == 0, p1.stderr
    assert "==> 已存" in p1.stdout
    arts = list(outdir.glob("article--fixture.md"))
    assert arts
    assert arts[0].read_bytes() == b"<html><body>fixture article</body></html>"

    p2 = run_cli(["run", url, "-o", str(outdir)], env)
    if p2.returncode == 0 and "cache: hit" in p2.stderr:
        pass  # lgc present: second run served from cache
    else:
        # lgc absent -> degraded re-fetch is also acceptable
        assert p2.returncode == 0


def test_e2e_json_envelope(tmp_path, httpd):
    packs = make_pack(tmp_path)
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/j"
    p = run_cli(["run", url, "--json"], env)
    assert p.returncode == 0, p.stderr
    env_ = json.loads(p.stdout.strip().splitlines()[-1])
    assert env_["rc"] == 0
    assert env_["items"]
    assert Path(env_["journal"]).exists()


def _journal_decisions(env_):
    out = []
    for line in Path(env_["journal"]).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "decision":
            out.append(rec)
    return out


def test_e2e_no_cache_and_refresh(tmp_path, httpd):
    """no_cache bypasses all lgc ops; refresh skips reads but still stores."""
    packs = make_pack(tmp_path)
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/nc"

    p1 = run_cli(["run", url, "--json"], env)
    assert p1.returncode == 0, p1.stderr
    env1 = json.loads(p1.stdout.strip().splitlines()[-1])
    assert any(d.get("gate") == "cache" for d in _journal_decisions(env1)), (
        "first run must consult the cache gate"
    )

    p2 = run_cli(["run", url, "--param", "no_cache", "--json"], env)
    assert p2.returncode == 0, p2.stderr
    assert "cache: hit" not in p2.stderr
    env2 = json.loads(p2.stdout.strip().splitlines()[-1])
    dec2 = _journal_decisions(env2)
    assert [d.get("verdict") for d in dec2 if d.get("gate") == "cache"] == ["no_cache"]
    assert not any(d.get("gate") == "store" for d in dec2), (
        "no_cache must not write to the store"
    )

    p3 = run_cli(["run", url, "--param", "refresh", "--json"], env)
    assert p3.returncode == 0, p3.stderr
    assert "cache: hit" not in p3.stderr
    env3 = json.loads(p3.stdout.strip().splitlines()[-1])
    dec3 = _journal_decisions(env3)
    assert [d.get("verdict") for d in dec3 if d.get("gate") == "cache"] == ["refresh"]
    if any(d.get("gate") == "store" for d in _journal_decisions(env1)):
        # refresh writes back when lgc is functional
        assert any(d.get("gate") == "store" for d in dec3)


def test_e2e_noresults_tombstone(tmp_path, httpd):
    """An erroring lane -> error rc; journal records classification."""
    pdir = tmp_path / "packs" / "errpack"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(f"""
[pack]
name = "errpack"
abi = 1
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["127.0.0.1", "localhost"]
[[lanes]]
name = "err_lane"
exec = "{FIXTURES}/err_lane.py"
budget_ms = 15000
""")
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(tmp_path / "packs")
    url = f"http://127.0.0.1:{httpd.server_port}/x"
    p = run_cli(["run", url], env)
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    assert "transient" in p.stderr


# ---------------------------------------------------------------- variants:
# base_key / routes / probe chain / kind_required / store='base' / fail_note

LGC_MISSING = shutil.which("lgc") is None
requires_lgc = pytest.mark.skipif(LGC_MISSING, reason="lgc not on PATH")


class _NoLgc:
    def available(self):
        return False


def _toml_pack(fe, tmp_path, text):
    return fe.Pack(tmp_path / "pack.toml", tomllib.loads(text))


def test_make_identity_base_key_and_kind_miss(fe, tmp_path):
    pack = _toml_pack(
        fe,
        tmp_path,
        """
[pack]
name = "z"
kinds = ["ans", "art"]
[identity]
keyexpr = "{kind}:{id}{variant}"
key_params = ["variant"]
kind_by_url = { ans = 'answer/[0-9]+' }
capture = { id = 'answer/([0-9]+)' }
""",
    )
    lgc = _NoLgc()
    ident = fe.make_identity(
        pack, "https://www.zhihu.com/answer/456", {"variant": "+f"}, lgc
    )
    assert ident["kind"] == "ans"
    assert ident["key"] == "ans:456+f"
    assert ident["base_key"] == "ans:456"  # variant stripped
    assert ident["kind_miss"] is False

    ident = fe.make_identity(pack, "https://www.zhihu.com/answer/456", {}, lgc)
    assert ident["key"] == "ans:456" == ident["base_key"]  # no variant -> same key

    ident = fe.make_identity(pack, "https://www.zhihu.com/elsewhere", {}, lgc)
    assert ident["kind"] == "ans"  # kinds[0] fallback, but flagged
    assert ident["kind_miss"] is True


def test_select_lanes_routes(fe, tmp_path):
    pack = _toml_pack(
        fe,
        tmp_path,
        """
[pack]
name = "z"
kinds = ["ans", "col"]
[identity]
keyexpr = "{kind}:{id}{variant}"
key_params = ["variant"]
[[routes]]
kinds = ["ans"]
params = { variant = "" }
lanes = ["a", "b"]
[[routes]]
kinds = ["ans"]
params = { variant = "+f" }
lanes = ["b"]
[[routes]]
kinds = ["col"]
params = { comments = true }
lanes = ["c"]
[[lanes]]
name = "a"
exec = "x"
[[lanes]]
name = "b"
exec = "y"
[[lanes]]
name = "c"
exec = "z"
""",
    )

    def names(kind, params):
        sel = fe.select_lanes(pack, {"kind": kind, "params": params})
        return None if sel is None else [lc["name"] for lc in sel]

    assert names("ans", {}) == ["a", "b"]  # missing param matches variant=""
    assert names("ans", {"variant": "+f"}) == ["b"]  # route order, not pack order
    assert names("ans", {"variant": "+c"}) is None  # routes exist, no arm -> miss
    assert names("col", {"comments": True}) == ["c"]  # bool true via _truthy
    assert names("col", {}) is None  # comments absent -> not _truthy -> no match

    pack2 = _toml_pack(
        fe,
        tmp_path,
        """
[pack]
name = "p"
[[lanes]]
name = "a"
exec = "x"
""",
    )
    sel = fe.select_lanes(pack2, {"kind": "article", "params": {}})
    assert [lc["name"] for lc in sel] == ["a"]  # no routes -> pack.lanes


def test_record_error_permanent_negs_base(fe):
    ident = {"key": "ans:1+f", "base_key": "ans:1"}
    lgc = _SpyLgc()
    fe.record_error(lgc, ident, "L", {"class": "permanent"})
    assert lgc.calls == [
        ("neg", ("ans:1+f", "deleted"), {}),
        ("neg", ("ans:1", "deleted"), {}),
    ]  # variant gone => base gone


def test_record_error_fail_note_gate(fe):
    ident = {"key": "ans:1+f", "base_key": "ans:1"}
    lgc = _SpyLgc()
    fe.record_error(lgc, ident, "L", {"class": "transient"}, {"fail_note": False})
    assert lgc.calls == []  # tardis parity: no breaker bump, no lane note
    lgc = _SpyLgc()
    fe.record_error(lgc, ident, "L", {"class": "transient"}, {})
    assert lgc.calls == [
        ("lane_fail", ("L",), {}),
        ("lane_note", ("L", "ans:1", "lane-fail"), {"ttl": 600}),
    ]  # default fail_note=True; note lands on base_key


def make_zpack(tmp_path, lanes_toml, routes_toml="", kind_required=False):
    """Variant pack: keyexpr carries {variant}; probe_base_variants = +f."""
    pdir = tmp_path / "packs" / "zpack"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(f"""
[pack]
name = "zpack"
abi = 1
ns = "link-get"
kinds = ["art"]
kind_required = {str(kind_required).lower()}
[match]
hosts = ["127.0.0.1", "localhost"]
[identity]
keyexpr = "{{kind}}:{{id}}{{variant}}"
key_params = ["variant"]
probe_base_variants = ["+f"]
kind_by_url = {{ art = "/a/[0-9]+" }}
capture = {{ id = "/a/([0-9]+)" }}
{routes_toml}
{lanes_toml}
""")
    return tmp_path / "packs"


OK_LANE_TOML = f"""
[[lanes]]
name = "ok_lane"
exec = "{FIXTURES}/ok_lane.py"
budget_ms = 15000
"""

ERR_LANE_TOML = f"""
[[lanes]]
name = "err_lane"
exec = "{FIXTURES}/err_lane.py"
budget_ms = 15000
"""


def _lgc(args, env):
    return subprocess.run(
        ["lgc", *args],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


@requires_lgc
def test_e2e_variant_probe_order(tmp_path, httpd):
    """+f fetch probes [base, key] in order; refill hits on the variant key."""
    packs = make_zpack(tmp_path, OK_LANE_TOML)
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/a/1"

    p1 = run_cli(["run", url, "variant=+f", "--json"], env)
    assert p1.returncode == 0, p1.stderr
    env1 = json.loads(p1.stdout.strip().splitlines()[-1])
    gates = [
        d for d in _journal_decisions(env1) if d.get("gate") == "cache" and d.get("key")
    ]
    assert [d["key"] for d in gates] == ["art:1", "art:1+f"]
    assert [d["verdict"] for d in gates] == ["miss", "miss"]

    p2 = run_cli(["run", url, "variant=+f", "--json"], env)
    assert p2.returncode == 0, p2.stderr
    env2 = json.loads(p2.stdout.strip().splitlines()[-1])
    gates2 = [
        d for d in _journal_decisions(env2) if d.get("gate") == "cache" and d.get("key")
    ]
    assert [d["key"] for d in gates2] == ["art:1", "art:1+f"]
    assert gates2[0]["verdict"] == "miss"  # base still empty (no store=base)
    assert gates2[1]["verdict"] == "hit"


@requires_lgc
def test_e2e_store_base(tmp_path, httpd):
    """store='base' lane writes the base key; a plain fetch then hits cache."""
    packs = make_zpack(
        tmp_path,
        f"""
[[lanes]]
name = "ok_lane"
exec = "{FIXTURES}/ok_lane.py"
budget_ms = 15000
store = "base"
""",
    )
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/a/2"

    p1 = run_cli(["run", url, "variant=+f", "--json"], env)
    assert p1.returncode == 0, p1.stderr
    g = _lgc(
        ["get", "link-get", "art:2", "--into", str(tmp_path / "m1"), "--json"], env
    )
    assert g.returncode == 0, g.stderr  # content landed on the base key
    g = _lgc(["get", "link-get", "art:2+f", "--into", str(tmp_path / "m2")], env)
    assert g.returncode != 0  # variant key left empty

    p2 = run_cli(["run", url, "--json"], env)
    assert p2.returncode == 0, p2.stderr
    assert "cache: hit" in p2.stderr  # base fetch served by the +f fill


@requires_lgc
def test_e2e_lane_cooling_on_base_key(tmp_path, httpd):
    """Variant-fetch failure notes the lane on base_key -> base fetch cools."""
    packs = make_zpack(tmp_path, ERR_LANE_TOML)
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/a/6"

    p1 = run_cli(["run", url, "variant=+f", "--json"], env)
    assert p1.returncode == 5, p1.stderr  # transient exhausted

    p2 = run_cli(["run", url, "--json"], env)
    env2 = json.loads(p2.stdout.strip().splitlines()[-1])
    dec2 = _journal_decisions(env2)
    assert env2["class"] == "dep_absent"
    assert p2.returncode == 5
    assert any(d.get("gate") == "cooling" and d.get("verdict") == "skip" for d in dec2)
    assert not any(d.get("stage") == "exec" for d in dec2)


def test_e2e_routes_arms(tmp_path, httpd):
    """[[routes]] picks a different lane arm per (kind, params) combo."""
    packs = make_zpack(
        tmp_path,
        ERR_LANE_TOML + OK_LANE_TOML,
        routes_toml="""
[[routes]]
kinds = ["art"]
params = { variant = "" }
lanes = ["err_lane"]
[[routes]]
kinds = ["art"]
params = { variant = "+f" }
lanes = ["ok_lane"]
""",
    )
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/a/3"

    p1 = run_cli(["run", url, "--json"], env)
    assert p1.returncode == 5, (p1.returncode, p1.stderr)  # err_lane transient
    env1 = json.loads(p1.stdout.strip().splitlines()[-1])
    dec1 = _journal_decisions(env1)
    assert any(
        d.get("stage") == "route" and d.get("lanes") == ["err_lane"] for d in dec1
    )
    exec1 = [d.get("lane") for d in dec1 if d.get("stage") == "exec"]
    assert "err_lane" in exec1
    assert "ok_lane" not in exec1

    p2 = run_cli(["run", url, "variant=+f", "--json"], env)
    assert p2.returncode == 0, p2.stderr  # +f arm runs ok_lane
    env2 = json.loads(p2.stdout.strip().splitlines()[-1])
    dec2 = _journal_decisions(env2)
    assert any(
        d.get("stage") == "route" and d.get("lanes") == ["ok_lane"] for d in dec2
    )
    exec2 = [d.get("lane") for d in dec2 if d.get("stage") == "exec"]
    assert "ok_lane" in exec2
    assert "err_lane" not in exec2


def test_e2e_route_miss(tmp_path, httpd):
    """routes present but no arm matches -> rc2 refused + route_miss decision."""
    packs = make_zpack(
        tmp_path,
        OK_LANE_TOML,
        routes_toml="""
[[routes]]
kinds = ["art"]
params = { variant = "+f" }
lanes = ["ok_lane"]
""",
    )
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)
    url = f"http://127.0.0.1:{httpd.server_port}/a/4"

    p = run_cli(["run", url, "variant=+c", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "no route" in p.stderr
    env_ = json.loads(p.stdout.strip().splitlines()[-1])
    assert env_["rc"] == 2
    assert env_["class"] == "refused"
    assert any(d.get("stage") == "route_miss" for d in _journal_decisions(env_))


def test_e2e_kind_required(tmp_path, httpd):
    """kind_required pack refuses URLs whose kind can't be determined."""
    packs = make_zpack(tmp_path, OK_LANE_TOML, kind_required=True)
    env = e2e_env(tmp_path)
    env["FETCH_ENGINE_PACKS"] = str(packs)

    url = f"http://127.0.0.1:{httpd.server_port}/zzz"  # matches hosts, not kind
    p = run_cli(["run", url, "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "no kind" in p.stderr
    env_ = json.loads(p.stdout.strip().splitlines()[-1])
    assert env_["class"] == "refused"
    assert any(
        d.get("stage") == "identity" and d.get("kind_miss")
        for d in _journal_decisions(env_)
    )

    url2 = f"http://127.0.0.1:{httpd.server_port}/a/5"  # kind found -> proceeds
    p2 = run_cli(["run", url2, "--json"], env)
    assert p2.returncode == 0, p2.stderr
