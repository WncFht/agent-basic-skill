"""test_regressions.py — 最终对抗评审修复面的回归测试（全离线）。

覆盖批次：
  F1 engine：guard_url inet_aton 形 / canon 裸文件 denylist / 端口剥离 /
    userinfo 剥除 / match_scope=path / capture_query / identity.derive /
    meta-lane 缓存跳闸 / load_packs 兜底序 / run_lane 协议违例与首终态胜 /
    stderr 尾保留 / retry_after 透传 / validate_artifacts 同名去重 /
    _gc_jobs / json 模式交付行进 stderr / -o 非目录 rc2 / bad_vals /
    mask_url_secrets
  F2 pack 真值（真 pack.toml + --plan --json 决策面，不 spawn 车道）：
    zhihu query 注入不造 kind、bilibili ?p 捕获与 opus 边界、youtube 派生
    kind=fast、generic doc-signed query 埋文件名、canvas mint 兜底臂
  F3 shell 见 test_link_get.py；shim flag_params 在本文件（import 级）
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
SHIM = ROOT / "scripts" / "monolith_shim.py"
FIXTURES = ROOT / "tests" / "fixtures"
CTX_LANE = FIXTURES / "ctx_lane.py"
PACKS = ROOT / "packs"


def load_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("LGC_HOME", str(tmp_path / "lgc-home"))
    monkeypatch.setenv("FETCH_ENGINE_JOBS", str(tmp_path / "jobs"))
    spec = importlib.util.spec_from_file_location("fetch_engine", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fe(tmp_path, monkeypatch):
    return load_engine(monkeypatch, tmp_path)


def run_cli(args, env_extra=None, timeout=60):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def base_env(tmp_path, packs_dir=None):
    return {
        "LGC_HOME": str(tmp_path / "lgc-home"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "FETCH_ENGINE_PACKS": str(packs_dir or tmp_path / "packs"),
        "FETCH_ENGINE_ALLOW_PRIVATE": "1",
    }


def write_pack(tmp_path, name, body):
    pdir = tmp_path / "packs" / name
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "pack.toml").write_text(body)
    return tmp_path / "packs"


def write_lane(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    p.chmod(0o755)
    return str(p)


def envelope_of(p):
    return json.loads(p.stdout.strip().splitlines()[-1])


def plan_of(tmp_path, packs_dir, target, *params, extra_env=None):
    """--plan --json 决策面快照：不 spawn 车道，只断 route/identity/admit。"""
    env = base_env(tmp_path, packs_dir)
    env.update(extra_env or {})
    args = ["run", target, "--plan", "--json"]
    for kv in params:
        args += ["--param", kv]
    r = run_cli(args, env)
    envl = envelope_of(r)
    return r, envl, envl.get("plan") or {}


def journal_text(envl):
    return Path(envl["journal"]).read_text()


def journal_events(envl, etype=None):
    evs = [
        json.loads(ln)
        for ln in Path(envl["journal"]).read_text().splitlines()
        if ln.strip()
    ]
    return [e for e in evs if etype is None or e.get("type") == etype]


# ================================================================ F1 engine


# ---- guard_url：inet_aton 字面量形（ipaddress 全拒、inet_aton 全收）——
#      按 DNS 放行即 SSRF 逃逸，必须按解析后地址判私网
@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",  # dword = 127.0.0.1
        "http://127.1/",  # short form
        "http://0x7f000001/",  # hex
        "http://0177.0.0.1/",  # octal
        "http://[::1]/",  # v6 loopback
        "http://127.0.0.1/",
        "http://169.254.169.254/latest",  # cloud metadata
    ],
)
def test_guard_inet_aton_private_forms(fe, url):
    assert fe.guard_url(url) is not None, url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://zhihu.com/p/1",
    ],
)
def test_guard_allows_public_dns(fe, url):
    assert fe.guard_url(url) is None, url


def test_guard_allow_private_bypasses(fe):
    assert fe.guard_url("http://127.0.0.1/", allow_private=True) is None


# ---- canon：裸文件名 denylist 只拦无 / 的 token；host/path 文档 URL 照常
#      补 https（拦了会把 generic doc 车道饿死——修复前 .pdf 尾一律不补）
@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("report.pdf", "report.pdf"),  # 裸文件名：不补 scheme → rc3
        ("a.zip", "a.zip"),
        ("notes.txt", "notes.txt"),
        ("x.com/a.pdf", "https://x.com/a.pdf"),  # host/path 文档照补
        ("x.com/doc.pdf?dl=1", "https://x.com/doc.pdf?dl=1"),
        ("zhihu.com/p/1", "https://zhihu.com/p/1"),
    ],
)
def test_canon_bare_file_denylist_scope(fe, raw, want):
    out, err = fe.canon(raw)
    assert err is None
    assert out == want


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("https://x.com:443/a", "https://x.com/a"),  # 默认端口剥
        ("http://x.com:80/a", "http://x.com/a"),
        ("http://x.com:443/a", "http://x.com:443/a"),  # 跨 scheme 不剥
        ("https://x.com:8443/", "https://x.com:8443/"),
        ("https://user:pw@x.com/a", "https://x.com/a"),  # userinfo 剥除
        ("http://[::1]:8080/p", "http://[::1]:8080/p"),  # v6 bracket 保住
    ],
)
def test_canon_port_and_userinfo(fe, raw, want):
    out, err = fe.canon(raw)
    assert err is None
    assert out == want


@pytest.mark.parametrize("raw", ["https://x:abc/", "https://[bad"])
def test_canon_malformed_rc2(fe, raw):
    out, err = fe.canon(raw)
    assert out is None
    assert err


# ---- match_scope="path"：kind_by_url/capture 只在 netloc+path 匹配——
#      query 注入（?utm=/p/999）不造 kind、不喂捕获
def test_match_scope_path_e2e(tmp_path):
    packs = write_pack(
        tmp_path,
        "scope",
        """
[pack]
name = "scope"
abi = 1
ns = "link-get"
kinds = ["art", "q"]

[match]
hosts = ["127.0.0.1"]

[identity]
keyexpr = "{kind}:{did}"
kind_by_url = { art = '/p/' }
match_scope = "path"
capture = { did = '([0-9]{6,})' }

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    # ?utm=/p/999 + ?id=123456 全在 query——path 面下既不判 art 也不捕获
    _, envl, plan = plan_of(tmp_path, packs, "http://127.0.0.1/x?utm=/p/999&id=123456")
    assert plan["kind"] == "art"  # kind_by_url 不中 → kinds[0] 兜底


def test_match_scope_path_kind_fallback_and_query_capture(tmp_path):
    packs = write_pack(
        tmp_path,
        "scope",
        """
[pack]
name = "scope"
abi = 1
ns = "link-get"
kinds = ["art", "q"]

[match]
hosts = ["127.0.0.1"]

[identity]
keyexpr = "{kind}:{did}:p{part}"
kind_by_url = { q = '/q/' }
match_scope = "path"
capture = { did = '([0-9]{6,})', part = '[?&]p=([0-9]+)' }
capture_defaults = { did = 'none', part = '1' }
capture_query = ["part"]

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    # path 命中 /q/ → kind=q；did 从 path 捕获（query 里 999999 不算数）；
    # part 白名单仍吃 query ?p=3
    _, envl, plan = plan_of(tmp_path, packs, "http://127.0.0.1/q/123456?utm=999999&p=3")
    assert plan["kind"] == "q"
    assert plan["key"] == "q:123456:p3"
    # query 注入的 kind/capture 不成立：/p/ 在 query 不判 art，?p= 不污染 did
    _, envl2, plan2 = plan_of(
        tmp_path, packs, "http://127.0.0.1/x?next=/q/999&id=123456"
    )
    assert plan2["kind"] == "art"  # kinds[0] 兜底（kind_by_url 不中）
    assert "123456" not in plan2["key"]


# ---- identity.derive：target=kind 早决 + 普通 param 派生
def test_derive_kind_and_param(tmp_path):
    packs = write_pack(
        tmp_path,
        "deriv",
        """
[pack]
name = "deriv"
abi = 1
ns = "link-get"
kinds = ["tr", "fast"]

[match]
hosts = ["127.0.0.1"]

[params]
fast = { type = "bool" }
comments = { type = "bool" }
variant = { type = "str" }

[identity]
keyexpr = "{kind}:{url}"
key_params = ["variant"]
kind_by_url = { tr = '/t/' }
variant_params = ["variant"]

[[identity.derive]]
target = "kind"
value = "fast"
when_truthy = "fast"

[[identity.derive]]
target = "variant"
value = "+c"
when_kind = "tr"
when_truthy = "comments"

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    # 裸 --param fast → kind=fast（kind-derive 在 kind_by_url 之后、kinds[0] 之前）
    _, envl, plan = plan_of(tmp_path, packs, "http://127.0.0.1/v/abc", "fast")
    assert plan["kind"] == "fast"
    # kind_by_url 仍优先：/t/ URL + fast → kind=tr（kind_by_url 命中不派生）
    _, _, plan2 = plan_of(tmp_path, packs, "http://127.0.0.1/t/abc", "fast")
    assert plan2["kind"] == "tr"
    # param 派生：tr + comments → variant=+c 进 keyexpr
    _, _, plan3 = plan_of(tmp_path, packs, "http://127.0.0.1/t/abc", "comments")
    assert plan3["key"].startswith("tr:")
    # base_key 剥 variant
    assert "+c" not in plan3["base_key"]


# ---- meta-lane：全臂 writes_cred → gate1 探测与 gate2 冷却全跳
def test_meta_lane_skips_cache_and_cooling(tmp_path):
    packs = write_pack(
        tmp_path,
        "meta",
        """
[pack]
name = "meta"
abi = 1
ns = "link-get"
kinds = ["mint"]

[match]
hosts = ["127.0.0.1"]

[identity]
keyexpr = "{kind}:const"

[[lanes]]
name = "minter"
exec = "__CTX__"
writes_cred = "meta"
""".replace("__CTX__", str(CTX_LANE)),
    )
    r, envl, plan = plan_of(tmp_path, packs, "http://127.0.0.1/x")
    assert envl["rc"] == 0
    assert plan["cache_verdict"] == "meta-lane"
    # gate2 冷却判定同样标 meta-lane（lgc 在场才记——缺席时该判定本就跳过）
    cooling = [
        e for e in journal_events(envl, "decision") if e.get("gate") == "cooling"
    ]
    for e in cooling:
        assert e.get("verdict") == "meta-lane"


# ---- load_packs 序：hosts=["*"] 兜底恒排最后——名字靠前也不抢路由
def test_catchall_pack_sorted_last(tmp_path):
    packs = write_pack(
        tmp_path,
        "aaa_catchall",
        """
[pack]
name = "aaa_catchall"
abi = 1
ns = "link-get"
kinds = ["article"]

[match]
hosts = ["*"]

[identity]
keyexpr = "{kind}:{url}"

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    write_pack(
        tmp_path,
        "zzz_specific",
        """
[pack]
name = "zzz_specific"
abi = 1
ns = "link-get"
kinds = ["thing"]

[match]
hosts = ["127.0.0.1"]

[identity]
keyexpr = "{kind}:{url}"

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    _, _, plan = plan_of(tmp_path, packs, "http://127.0.0.1/x")
    assert plan["pack"] == "zzz_specific"
    # 不匹配的 host 仍落兜底
    _, _, plan2 = plan_of(tmp_path, packs, "http://127.0.0.2/x")
    assert plan2["pack"] == "aaa_catchall"


# ---- run_lane 协议面：非 dict JSONL / 双终态 / retry_after / stderr 尾 / 断管
def _lane_pack(tmp_path, lane_path, extra=""):
    return write_pack(
        tmp_path,
        "proto",
        """
[pack]
name = "proto"
abi = 1
ns = "link-get"
kinds = ["thing"]

[match]
hosts = ["127.0.0.1"]

[identity]
keyexpr = "{kind}:{url}"

[[lanes]]
name = "proto_lane"
exec = "__LANE_PATH__"
""".replace("__LANE_PATH__", lane_path)
        + extra,
    )


def _run(tmp_path, packs, target="http://127.0.0.1/x", extra_args=None):
    env = base_env(tmp_path, packs)
    return run_cli(["run", target, "--json"] + (extra_args or []), env)


def test_lane_nondict_line_protocol_violation(tmp_path):
    lane = write_lane(
        tmp_path,
        "badline.py",
        """#!/usr/bin/env python3
import json, sys
from pathlib import Path
req = json.loads(sys.stdin.readline() or '{}')
adir = Path(req['ctx']['artifact_dir'])
(adir / 'a.md').write_text('x')
print('["not","a","dict"]')
print('plain text noise')
print(json.dumps({"type":"result","items":[{"path":str(adir/'a.md'),"name":"a.md"}]}))
""",
    )
    packs = _lane_pack(tmp_path, lane)
    r = _run(tmp_path, packs)
    envl = envelope_of(r)
    assert envl["rc"] == 0, r.stderr
    viol = [e for e in journal_events(envl, "event") if e.get("protocol_violation")]
    assert len(viol) >= 2  # 两行非 dict 各记一条


def test_lane_first_terminal_wins(tmp_path):
    lane = write_lane(
        tmp_path,
        "twoterm.py",
        """#!/usr/bin/env python3
import json, sys
from pathlib import Path
req = json.loads(sys.stdin.readline() or '{}')
adir = Path(req['ctx']['artifact_dir'])
(adir / 'a.md').write_text('x')
print(json.dumps({"type":"result","items":[{"path":str(adir/'a.md'),"name":"a.md"}]}))
print(json.dumps({"type":"error","class":"transient","evidence":"late"}))
""",
    )
    packs = _lane_pack(tmp_path, lane)
    r = _run(tmp_path, packs)
    envl = envelope_of(r)
    assert envl["rc"] == 0, r.stderr  # 首终态 result 胜，不是 error
    viol = [
        e
        for e in journal_events(envl, "event")
        if e.get("protocol_violation") and "second terminal" in str(e.get("detail"))
    ]
    assert viol, "second terminal 必须记违例"


def test_lane_error_retry_after_propagates(tmp_path):
    lane = write_lane(
        tmp_path,
        "ratelimit.py",
        """#!/usr/bin/env python3
import json, sys
sys.stdin.readline()
print(json.dumps({"type":"error","class":"rate_limited","evidence":"429","retry_after":7}))
""",
    )
    packs = _lane_pack(tmp_path, lane)
    r = _run(tmp_path, packs)
    envl = envelope_of(r)
    assert envl["rc"] == 5  # rate_limited → transient rc 面
    # lane_event 原样带 retry_after；record_error 用其定 lane_note ttl=7
    lane_evs = [
        e
        for e in journal_events(envl, "event")
        if isinstance(e.get("lane_event"), dict)
        and e["lane_event"].get("retry_after") == 7
    ]
    assert lane_evs


def test_lane_stderr_log_keeps_tail(tmp_path):
    lane = write_lane(
        tmp_path,
        "bigstderr.py",
        """#!/usr/bin/env python3
import sys
sys.stdin.readline()
sys.stderr.write("HEAD-MARKER\\n")
sys.stderr.write("x" * (70 * 1024) + "\\n")
sys.stderr.write("TAIL-MARKER\\n")
sys.exit(1)
""",
    )
    packs = _lane_pack(tmp_path, lane)
    r = _run(tmp_path, packs)
    envl = envelope_of(r)
    assert envl["rc"] == 5
    log = Path(envl["journal"]).parent / "proto_lane.stderr.log"
    data = log.read_bytes()
    assert len(data) <= 64 * 1024
    assert b"TAIL-MARKER" in data
    assert b"HEAD-MARKER" not in data  # 留尾不留头——crash 段恰在尾


def test_lane_stdin_broken_pipe_no_crash(tmp_path):
    # 秒退不读 stdin——engine 写 BrokenPipe 不是 engine 错
    lane = write_lane(tmp_path, "instant.sh", "#!/bin/sh\nexit 0\n")
    packs = _lane_pack(tmp_path, lane)
    r = _run(tmp_path, packs)
    envl = envelope_of(r)
    # rc=0 无终态 → noresults 分类 rc3（engine 自己不崩）
    assert envl["rc"] == 3
    assert envl.get("class") == "noresults"


# ---- validate_artifacts：同名去重保 subdir 与扩展名；越界拒
def test_validate_artifacts_dedup_preserves_path_and_ext(fe, tmp_path):
    adir = tmp_path / "adir"
    (adir / "sub").mkdir(parents=True)
    f1 = adir / "sub" / "x.md"
    f2 = adir / "x.md"
    f1.write_text("a")
    f2.write_text("b")
    items = [
        {"path": str(f1), "name": "sub/x.md"},
        {"path": str(f2), "name": "x.md"},
        {"path": str(f1), "name": "sub/x.md"},  # 撞名
    ]
    ok, bad = fe.validate_artifacts(items, adir)
    assert not bad
    names = sorted(it["name"] for it in ok)
    assert names == ["sub/x-1.md", "sub/x.md", "x.md"], names


def test_validate_artifacts_rejects_escape(fe, tmp_path):
    adir = tmp_path / "adir"
    adir.mkdir()
    outside = tmp_path / "out.md"
    outside.write_text("x")
    items = [
        {"path": str(outside), "name": "out.md"},
        {"path": str(outside), "name": "../escape.md"},
    ]
    ok, bad = fe.validate_artifacts(items, adir)
    assert not ok
    assert len(bad) == 2


# ---- _gc_jobs：过期任务目录回收，新鲜保留
def test_gc_jobs_removes_only_stale(fe, tmp_path):
    root = tmp_path / "jobs"
    old = root / "old-job"
    fresh = root / "fresh-job"
    old.mkdir(parents=True)
    fresh.mkdir()
    stale = time.time() - (15 * 86400)
    import os as _os

    _os.utime(old, (stale, stale))
    fe._gc_jobs(root)
    assert not old.exists()
    assert fresh.exists()


# ---- cmd_run 杂项：-o 非目录 rc2；json 模式交付行进 stderr；bad_vals
def test_outdir_existing_file_rc2(tmp_path):
    packs = _lane_pack(tmp_path, str(CTX_LANE))
    f = tmp_path / "afile"
    f.write_text("x")
    r = run_cli(["run", "http://127.0.0.1/x", "-o", str(f)], base_env(tmp_path, packs))
    assert r.returncode == 2
    assert "非目录" in r.stderr


def test_json_mode_delivery_lines_to_stderr(tmp_path):
    lane = write_lane(
        tmp_path,
        "artlane.py",
        """#!/usr/bin/env python3
import json, sys
from pathlib import Path
req = json.loads(sys.stdin.readline() or '{}')
adir = Path(req['ctx']['artifact_dir'])
(adir / 'a.md').write_text('x')
print(json.dumps({"type":"result","items":[{"path":str(adir/'a.md'),"name":"a.md"}]}))
""",
    )
    packs = _lane_pack(tmp_path, lane)
    dest = tmp_path / "out"
    r = run_cli(
        ["run", "http://127.0.0.1/x", "-o", str(dest), "--json"],
        base_env(tmp_path, packs),
    )
    assert r.returncode == 0, r.stderr
    # stdout 是单行 envelope——"已存" 交付行只进 stderr
    out_lines = [ln for ln in r.stdout.strip().splitlines() if ln.strip()]
    assert len(out_lines) == 1
    json.loads(out_lines[0])
    assert "已存" in r.stderr
    assert "已存" not in r.stdout


def test_bad_vals_values_enum_and_kind(tmp_path):
    packs = write_pack(
        tmp_path,
        "enumval",
        """
[pack]
name = "enumval"
abi = 1
ns = "link-get"
kinds = ["thing"]

[match]
hosts = ["127.0.0.1"]

[params]
enum = { type = "str", values = ["a", "b"] }

[identity]
keyexpr = "{kind}:{url}"

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    # values 表外值 → rc2 out-of-range（原 dep_absent 误导类）
    r = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "enum=zzz"],
        base_env(tmp_path, packs),
    )
    assert r.returncode == 2
    assert "out of range" in r.stderr
    # 合法值放行
    r2 = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "enum=a", "--plan", "--json"],
        base_env(tmp_path, packs),
    )
    assert r2.returncode == 0, r2.stderr
    # kind ∉ pack.kinds → rc2（原静默坍 kinds[0] 写错域键）
    r3 = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "kind=bogus"],
        base_env(tmp_path, packs),
    )
    assert r3.returncode == 2
    assert "out of range" in r3.stderr


# ---- mask_url_secrets：journal/plan 掩码（lgc argv 需真值不动）
def test_journal_masks_query_secrets(tmp_path):
    packs = write_pack(
        tmp_path,
        "maskp",
        """
[pack]
name = "maskp"
abi = 1
ns = "link-get"
kinds = ["thing"]

[match]
hosts = ["127.0.0.1"]

[identity]
keyexpr = "{kind}:{url}"

[[lanes]]
name = "ctx"
exec = "__CTX__"
""".replace("__CTX__", str(CTX_LANE)),
    )
    r, envl, plan = plan_of(tmp_path, packs, "http://127.0.0.1/x?sig=sekrit123&k=1")
    jt = journal_text(envl)
    assert "sekrit123" not in jt, "journal 落盘不得存 query 秘参明文"
    assert "sig=***" in jt
    assert "sig=***" in plan["key"]  # plan 机读面同样掩码


# ================================================================ shim flag_params


def _load_shim():
    spec = importlib.util.spec_from_file_location("monolith_shim", SHIM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_shim_flag_params_falsy_and_dash_values():
    mod = _load_shim()
    mod.CONF.update(
        {
            "flag_params": {
                "refresh": "--refresh",
                "no_cache": "--no-cache",
                "lecture": "--lecture",
            }
        }
    )
    ctx = {"artifact_dir": "/a", "journal_dir": "/j"}

    def argv(params):
        return mod.expand_argv(
            ["{url}"], {"kind": "t", "raw": "u", "params": params}, ctx
        )

    assert argv({"refresh": "false"}) == ["u"]  # 显式假不带旗
    assert argv({"refresh": "0"}) == ["u"]
    assert argv({"no_cache": "off"}) == ["u"]
    assert argv({"refresh": True}) == ["u", "--refresh"]
    assert argv({"refresh": "true"}) == ["u", "--refresh"]
    # 值以 - 开头：两参形会被 connector 当新旗标吞——并单 token --flag=v
    assert argv({"lecture": "-3"}) == ["u", "--lecture=-3"]
    assert argv({"lecture": "3"}) == ["u", "--lecture", "3"]


# ================================================================ F2 pack 真值
# 真 pack.toml + --plan --json：断 kind/key/runnable，不 spawn 车道


def _real_packs_env(tmp_path):
    env = base_env(tmp_path, PACKS)
    # 真 pack hosts 是公网域名——SSRF 闸要放行
    env["FETCH_ENGINE_ALLOW_PRIVATE"] = ""
    return env


def _plan_real(tmp_path, target, *params):
    env = _real_packs_env(tmp_path)
    args = ["run", target, "--plan", "--json"]
    for kv in params:
        args += ["--param", kv]
    r = run_cli(args, env)
    try:
        envl = envelope_of(r)
    except Exception:
        envl = None
    return r, envl


def test_zhihu_query_injection_no_kind_forgery(tmp_path):
    """match_scope=path：?utm=/answer/ 不伪造 ans kind（修复前 url 面匹配会中）"""
    r, envl = _plan_real(tmp_path, "https://www.zhihu.com/question/123?utm=/answer/999")
    assert envl
    assert envl["plan"]["kind"] == "q", envl


def test_zhihu_derive_variant_parity(tmp_path):
    """裸 --param comments/fast 经 derive 注 variant（壳注入的引擎层平价）：
    answer+comments→+c、answer+fast→+f、/p/+fast→+f、question+fast→+f"""
    cases = [
        ("https://www.zhihu.com/question/1/answer/2", ("comments",), "+c"),
        ("https://www.zhihu.com/question/1/answer/2", ("fast",), "+f"),
        ("https://zhuanlan.zhihu.com/p/123", ("fast",), "+f"),
        ("https://www.zhihu.com/question/1", ("fast",), "+f"),
    ]
    for url, params, suffix in cases:
        _, envl = _plan_real(tmp_path, url, *params)
        key = envl["plan"]["key"]
        assert key.endswith(suffix), (url, params, key)
        # base_key 剥 variant——车道账不走变体键
        assert not envl["plan"]["base_key"].endswith(suffix)


def test_bilibili_part_capture_and_opus_boundary(tmp_path):
    # ?p=3 是 query——capture_query 白名单下仍捕获（path 面剥了会全坍 p1）
    _, envl = _plan_real(tmp_path, "https://www.bilibili.com/video/BV1xx411c7mD?p=3")
    assert envl["plan"]["key"].endswith(":p3"), envl["plan"]["key"]
    # ?utm=/opus/1 不伪造 opus kind（path scope）
    _, envl2 = _plan_real(
        tmp_path, "https://www.bilibili.com/video/BV1xx411c7mD?utm=/opus/1"
    )
    assert envl2["plan"]["kind"] == "subs"
    # mopus 类 substring 不命中（opus 词边界收紧）
    _, envl3 = _plan_real(tmp_path, "https://www.bilibili.com/mopus/1234567890")
    assert envl3["plan"]["kind"] == "subs"


def test_youtube_derive_fast_and_capture(tmp_path):
    """--param fast → derive kind=fast；youtu.be//shorts 形 capture 覆盖"""
    _, envl = _plan_real(tmp_path, "https://www.youtube.com/watch?v=abc123XYZ", "fast")
    assert envl["plan"]["kind"] == "fast"
    _, envl2 = _plan_real(tmp_path, "https://youtu.be/abc123XYZ")
    assert "abc123XYZ" in envl2["plan"]["key"]
    _, envl3 = _plan_real(tmp_path, "https://www.youtube.com/shorts/abc123XYZ")
    assert "abc123XYZ" in envl3["plan"]["key"]


def test_generic_doc_signed_query_embedded_rc2(tmp_path):
    """文件名埋在 query（/dl?f=doc.pdf&token=x）同样判 doc-signed →
    无臂 kind → route_miss rc2，签名链绝不喂云"""
    r, envl = _plan_real(tmp_path, "https://example.com/dl?f=doc.pdf&token=xyz")
    assert r.returncode == 2
    assert "doc-signed" in r.stderr
    # 对照：干净 doc URL 正常进 doc 臂
    r2, envl2 = _plan_real(tmp_path, "https://example.com/a.pdf")
    assert envl2
    assert envl2["plan"]["kind"] == "doc"


def test_canvas_mint_catchall_locks_meta_lane(tmp_path):
    """kind=lecture 带 mint（play-center 直喂 engine）→ routes 无 kinds 约束的
    mint=true 兜底臂锁 canvas-mint——不静默下载"""
    _, envl = _plan_real(
        tmp_path,
        "https://oc.sjtu.edu.cn/courses/42/play-center/x",
        "kind=lecture",
        "mint",
    )
    ok_lanes = [s["name"] for s in envl["plan"]["lanes"] if s["ok"]]
    assert ok_lanes == ["canvas-mint"], envl["plan"]["lanes"]
    # canvas 是 self_managed 包——缓存判定先于 meta-lane 短路（connector 自管账）
    assert envl["plan"]["cache_verdict"] == "self-managed"


def test_canvas_enum_routes_still_hold(tmp_path):
    """对照组：enum+mint → canvas-mint；enum 无下载参 → canvas-rest"""
    _, envl = _plan_real(
        tmp_path,
        "https://oc.sjtu.edu.cn/courses/42",
        "enum=mint",
    )
    ok_lanes = [s["name"] for s in envl["plan"]["lanes"] if s["ok"]]
    assert ok_lanes == ["canvas-mint"]
    _, envl2 = _plan_real(
        tmp_path,
        "https://oc.sjtu.edu.cn/courses/42",
        "enum=files",
    )
    ok2 = [s["name"] for s in envl2["plan"]["lanes"] if s["ok"]]
    assert ok2 == ["canvas-rest"]


# ================================================================ F4 杂项


def test_skill_frontmatter_triggers():
    """SKILL.md description 触发面抽查——路由域一个不能丢（agent 发现面契约）"""
    head = (ROOT / "SKILL.md").read_text()[:4000]
    m = re.search(r"description:\s*(.+?)(?:\n---|\Z)", head, re.DOTALL)
    desc = m.group(1) if m else ""
    for trigger in (
        "YouTube",
        "Bilibili",
        "知乎",
        "微信",
        "Canvas",
        "arXiv",
        "链接",
    ):
        assert trigger in desc, f"frontmatter 缺触发域 {trigger}"


def test_canvas_rest_rejects_placeholder_course(tmp_path):
    """canvas-rest：enum 臂拿站点根 URL/空 course 必须 notcovered——
    壳对裸枚举旗标回填的占位 TARGET 喂 connector 只会 rc0 空表假成功"""
    lane = PACKS / "canvas" / "lanes" / "canvas_rest.py"
    for raw, params in [
        ("https://oc.sjtu.edu.cn/", {"enum": "files"}),  # 占位根 URL
        ("", {"enum": "files", "course": ""}),  # 空 course
        ("https://oc.sjtu.edu.cn/", {"enum": "announcements"}),
    ]:
        req = {"identity": {"raw": raw, "params": params}, "ctx": {}}
        r = subprocess.run(
            [sys.executable, str(lane)],
            input=json.dumps(req) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        ev = json.loads(r.stdout.strip().splitlines()[-1])
        assert ev["type"] == "error", (raw, params, r.stdout)
        assert ev["class"] == "notcovered", (raw, params, r.stdout)
    # 对照：真课程 URL / 裸 ID 通过闸（会去调 canvas-get——不给它就 dep_absent
    # 而不是 notcovered，断的不是同一条）
    req = {
        "identity": {
            "raw": "https://oc.sjtu.edu.cn/courses/97882",
            "params": {"enum": "files"},
        },
        "ctx": {},
    }
    r = subprocess.run(
        [sys.executable, str(lane)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "CANVAS_GET": "/nonexistent"},
    )
    ev = json.loads(r.stdout.strip().splitlines()[-1])
    assert ev["class"] != "notcovered", r.stdout
