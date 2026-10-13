"""test_pack_surface.py — 6b 批 pack.toml 新声明面测试：
[[match.bare]] bare_resolve（canon 前重写）、[params] 闸+secret 掩码、
[kind_by_url] 顶层表（regex→kind）、cred_domain→`lgc cred-fp` 委托、
writes_cred/routes 覆盖的 selftest 体检。全离线：fixture lane 回声 +
stub lgc，无网络。"""

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
FIXTURES = ROOT / "tests" / "fixtures"
ECHO = FIXTURES / "echo_lane.py"


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
    env.pop("LGC_BIN", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _pack(tmp_path, name, toml_text):
    pdir = tmp_path / "packs" / name
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(toml_text)
    return pdir


def _env(tmp_path):
    return {
        "LGC_HOME": str(tmp_path / "lgc-home"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
    }


def _envelope(proc):
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _journal(env_):
    out = []
    for line in Path(env_["journal"]).read_text().splitlines():
        out.append(json.loads(line))
    return out


def _decisions(env_):
    return [r for r in _journal(env_) if r.get("type") == "decision"]


# ------------------------------------------------------- bare fixture packs

ARXIV_FIX = f"""
[pack]
name = "arxivfix"
ns = "link-get"
kinds = ["tex"]

[match]
hosts = ["arxiv.org"]

[[match.bare]]
pattern = '^arxiv:(.+)$'
rewrite = 'https://arxiv.org/abs/{{1}}'

[[match.bare]]
pattern = '^([0-9]{{4}}\\.[0-9]{{4,5}}(v[0-9]+)?)$'
rewrite = 'https://arxiv.org/abs/{{1}}'

[[match.bare]]
pattern = '^([a-z-]+(?:\\.[A-Z]{{2}})?/[0-9]{{7}}(?:v[0-9]+)?)$'
rewrite = 'https://arxiv.org/abs/{{1}}'

[identity]
keyexpr = "tex:{{url}}"

[[lanes]]
name = "echo"
exec = "{ECHO}"
"""

CANVAS_FIX = f"""
[pack]
name = "canvasfix"
ns = "link-get"
kinds = ["lec"]

[match]
hosts = ["oc.sjtu.edu.cn"]

[[match.bare]]
pattern = '^([0-9]{{4,6}})$'
rewrite = 'https://oc.sjtu.edu.cn/courses/{{1}}'

[identity]
keyexpr = "lec:{{url}}"

[[lanes]]
name = "echo"
exec = "{ECHO}"
"""

CATCHALL_FIX = f"""
[pack]
name = "zzcatch"
ns = "link-get"
kinds = ["article"]

[match]
hosts = ["*"]

[identity]
keyexpr = "article:{{url}}"

[[lanes]]
name = "echo"
exec = "{ECHO}"
"""


def _bare_packs(tmp_path, with_arxiv_bare=True):
    """arxivfix + canvasfix + catchall。with_arxiv_bare=False 时 arxivfix
    不带 [[match.bare]]（canon 劫持回归的 before 态）。"""
    arxiv_toml = ARXIV_FIX
    if not with_arxiv_bare:
        arxiv_toml = "\n".join(
            ln
            for ln in ARXIV_FIX.splitlines()
            if "match.bare" not in ln
            and not ln.startswith("pattern = ")
            and not ln.startswith("rewrite = ")
        )
    _pack(tmp_path, "arxivfix", arxiv_toml)
    _pack(tmp_path, "canvasfix", CANVAS_FIX)
    _pack(tmp_path, "zzcatch", CATCHALL_FIX)
    return _env(tmp_path)


def _bare_events(env_):
    return [d for d in _journal(env_) if d.get("stage") == "bare_resolve"]


# ------------------------------------------------------- bare_resolve e2e


def test_bare_arxiv_prefix_rewrites(tmp_path):
    """'arxiv:ID' → bare 重写 abs URL → arxivfix 路由；journal 记
    pattern+rewrite 的 bare_resolve 行。"""
    env = _bare_packs(tmp_path)
    p = run_cli(["run", "arxiv:2401.09988", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"]["raw"] == "https://arxiv.org/abs/2401.09988"
    bare = _bare_events(env_)
    assert len(bare) == 1
    assert bare[0]["pack"] == "arxivfix"
    assert bare[0]["pattern"] == "^arxiv:(.+)$"
    assert "arxiv.org/abs" in bare[0]["rewrite"]
    assert any(
        d.get("stage") == "route" and d.get("pack") == "arxivfix"
        for d in _decisions(env_)
    )


def test_bare_numeric_id_canvas(tmp_path):
    """'97882' 裸课程号 → canvasfix 重写 → courses URL；rc0 data 终态。"""
    env = _bare_packs(tmp_path)
    p = run_cli(["run", "97882", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"]["raw"] == "https://oc.sjtu.edu.cn/courses/97882"
    assert _bare_events(env_)[0]["pack"] == "canvasfix"


def test_bare_oldstyle_archive_id(tmp_path):
    """旧式 'math.AG/0601234'：bare 先于 canon —— 不被 dot-TLD 劫成
    https://math.AG/...，落 arxiv abs URL（含 archive 前缀）。"""
    env = _bare_packs(tmp_path)
    p = run_cli(["run", "math.AG/0601234", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"]["raw"] == "https://arxiv.org/abs/math.AG/0601234"
    assert _bare_events(env_)[0]["pack"] == "arxivfix"


def test_bare_no_match_passthrough(tmp_path):
    """无 bare 命中的 URL token 原样进 canon——无 bare_resolve journal 行，
    路由照旧。"""
    env = _bare_packs(tmp_path)
    p = run_cli(["run", "https://arxiv.org/abs/2401.1", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"]["raw"] == "https://arxiv.org/abs/2401.1"
    assert _bare_events(env_) == []
    assert any(
        d.get("stage") == "route" and d.get("pack") == "arxivfix"
        for d in _decisions(env_)
    )


def test_bare_forced_pack_scopes_table(tmp_path):
    """-p 强制时只扫该 pack 的 bare 表：'97882' -p arxivfix → arxivfix 表无
    数字规则 → 不重写（canon 后非 URL → rc2）；同 token -p canvasfix → 重写。"""
    env = _bare_packs(tmp_path)
    p = run_cli(["run", "97882", "-p", "arxivfix", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert _bare_events(env_) == []

    p2 = run_cli(["run", "97882", "-p", "canvasfix", "--json"], env)
    assert p2.returncode == 0, (p2.returncode, p2.stdout, p2.stderr)
    assert _envelope(p2)["data"]["raw"] == ("https://oc.sjtu.edu.cn/courses/97882")


def test_bare_unknown_forced_pack_rc2(tmp_path):
    """-p 未知 pack → rc2 在 canon/bare 之前（扫描面都建不起来）。"""
    env = _bare_packs(tmp_path)
    p = run_cli(["run", "97882", "-p", "nosuch", "--json"], env)
    assert p.returncode == 2
    assert "unknown pack" in p.stderr


# ------------------------------------------------------- canon 劫持回归


def test_canon_hijack_documents_current_behavior(tmp_path):
    """无 bare 规则时 'math.AG/0601234' 被 canon dot-TLD 劫成
    https://math.ag/0601234 → catch-all（现行线上行为的 before 快照）。"""
    env = _bare_packs(tmp_path, with_arxiv_bare=False)
    p = run_cli(["run", "math.AG/0601234", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"]["raw"] == "https://math.ag/0601234"
    assert _bare_events(env_) == []
    assert any(
        d.get("stage") == "route" and d.get("pack") == "zzcatch"
        for d in _decisions(env_)
    )


# ------------------------------------------------------- bare_resolve 单元


def _bare_pack(fe, tmp_path, name, rules):
    toml_text = f"""
[pack]
name = "{name}"
[match]
hosts = ["{name}.example"]
{rules}
"""
    return fe.Pack(tmp_path / name / "pack.toml", tomllib.loads(toml_text))


def test_bare_resolve_first_hit_and_groups(fe, tmp_path):
    """有序表首中胜；{0}=整组 {1..}=捕获组；命中即停不重扫产物。"""
    p = _bare_pack(
        fe,
        tmp_path,
        "bp",
        """
[[match.bare]]
pattern = '^a(.+)$'
rewrite = 'https://x.example/{1}'

[[match.bare]]
pattern = '^a'
rewrite = 'https://x.example/SECOND-NEVER'
""",
    )
    out = fe.bare_resolve("aBC", [p])
    assert out == "https://x.example/BC"
    # {0} 整组展开
    p2 = _bare_pack(
        fe,
        tmp_path,
        "bp2",
        """
[[match.bare]]
pattern = '^z(.+)$'
rewrite = '{0}|{1}'
""",
    )
    assert fe.bare_resolve("zQ", [p2]) == "zQ|Q"


def test_bare_resolve_no_match_returns_input(fe, tmp_path):
    p = _bare_pack(
        fe,
        tmp_path,
        "bp",
        """
[[match.bare]]
pattern = '^a'
rewrite = 'x'
""",
    )
    assert fe.bare_resolve("zzz", [p]) == "zzz"


def test_bare_resolve_bad_pattern_skipped(fe, tmp_path):
    """坏正则跳过不炸（selftest 体检另捕）；后续规则照常评估。"""
    p = _bare_pack(
        fe,
        tmp_path,
        "bp",
        """
[[match.bare]]
pattern = '^('
rewrite = 'x'

[[match.bare]]
pattern = '^ok:(.+)$'
rewrite = 'https://x/{1}'
""",
    )
    assert fe.bare_resolve("ok:1", [p]) == "https://x/1"


# ------------------------------------------------------- [params] 闸

PGATE_FIX = f"""
[pack]
name = "pgate"
ns = "link-get"
kinds = ["article"]

[match]
hosts = ["example.com"]

[params]
quality = {{ type = "enum", values = ["hi", "lo"], desc = "质量档" }}
token = {{ type = "str", secret = true, desc = "秘参" }}

[identity]
keyexpr = "article:{{url}}"

[[routes]]
kinds = ["article"]
params = {{ fast = true }}
lanes = ["echo"]

[[routes]]
lanes = ["echo"]

[[lanes]]
name = "echo"
exec = "{ECHO}"
"""


def _pgate_env(tmp_path):
    _pack(tmp_path, "pgate", PGATE_FIX)
    return _env(tmp_path)


def test_params_gate_unknown_param_rc2(tmp_path):
    """未声明 param → rc2，stderr 点名非法键 + 合法集（声明面+豁免集）。"""
    env = _pgate_env(tmp_path)
    p = run_cli(["run", "https://example.com/x", "--param", "bogus=1", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "bogus" in p.stderr
    # 合法集枚举：声明键 + 保留名 + routes.params 键
    for k in ("quality", "token", "fast", "kind", "refresh", "variant"):
        assert k in p.stderr, p.stderr


def test_params_gate_declared_and_exempt_pass(tmp_path):
    """声明 param、engine 保留名、routes.params 键（未在 [params] 声明）
    都过闸。"""
    env = _pgate_env(tmp_path)
    url = "https://example.com/x"
    for extra in (
        ["--param", "quality=hi"],
        ["--param", "fast"],  # routes.params 键豁免
        ["--param", "kind=article", "--param", "refresh", "--param", "no_cache"],
        ["--param", "cache_ttl=60", "--param", "enum=x"],  # 保留名豁免
    ):
        p = run_cli(["run", url, *extra, "--json"], env)
        assert p.returncode == 0, (extra, p.returncode, p.stdout, p.stderr)


def test_params_gate_secret_masked_in_journal(tmp_path):
    """secret=true 的 param：journal 只记键名 '***'，值全文绝不出现。"""
    env = _pgate_env(tmp_path)
    marker = "sekrit-pat-abc123"
    p = run_cli(
        [
            "run",
            "https://example.com/x",
            "--param",
            f"token={marker}",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    jtext = Path(env_["journal"]).read_text()
    assert marker not in jtext, "secret value leaked into journal"
    assert '"token": "***"' in jtext


# ------------------------------------------------------- kind_by_url 顶层表

KBU_FIX = f"""
[pack]
name = "kbu"
ns = "link-get"
kinds = ["lec", "enum"]

[match]
hosts = ["oc.sjtu.edu.cn"]

[kind_by_url]
'courses/[0-9]+/files' = 'enum'

[identity]
keyexpr = "{{kind}}:{{url}}"

[[lanes]]
name = "echo"
exec = "{ECHO}"
"""


def test_kind_by_url_toplevel_selects_nondefault(fe, tmp_path):
    """顶层 [kind_by_url]（regex→kind）：命中 pattern → 非兜底 kind。"""
    _pack(tmp_path, "kbu", KBU_FIX)
    env = _env(tmp_path)
    p = run_cli(["run", "https://oc.sjtu.edu.cn/courses/5/files", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"]["kind"] == "enum"
    ident = next(d for d in _decisions(env_) if d.get("stage") == "identity")
    assert ident["kind"] == "enum"
    assert not ident.get("kind_miss")

    p2 = run_cli(["run", "https://oc.sjtu.edu.cn/courses/5", "--json"], env)
    env2 = _envelope(p2)
    assert env2["data"]["kind"] == "lec"  # kinds[0] 兜底保留
    ident2 = next(d for d in _decisions(env2) if d.get("stage") == "identity")
    assert ident2.get("kind_miss")


def test_kind_by_url_toplevel_overrides_identity(fe, tmp_path):
    """同 kind 双面声明：顶层 [kind_by_url]（regex→kind）赢。"""
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads("""
[pack]
name = "dual"
kinds = ["a", "b"]
[identity]
kind_by_url = { a = 'OLDRE' }
[kind_by_url]
'NEWRE' = 'a'
"""),
    )
    assert pack.kind_by_url == {"a": "NEWRE"}


# ------------------------------------------------------- cred_domain 委托


def test_resolve_cred_env_delegates_cred_domain(fe, tmp_path):
    """cred_domain 声明 → cred_handle = lgc cred-fp 输出；needs.creds
    原文哈希不再走。"""
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads("""
[pack]
name = "cd"
cred_domain = "bili"
[[lanes]]
name = "l"
exec = "x"
needs = { creds = ["/nonexistent-cred-file"] }
"""),
    )
    job = fe.Job(jobs_root=tmp_path / "jobs")
    job.journal.close()

    class _FakeLgc:
        def __init__(self, fp):
            self.fp = fp
            self.calls = []

        def cred_fp(self, domain):
            self.calls.append(domain)
            return self.fp

    fl = _FakeLgc("cafebabe")
    fe.resolve_cred_env(pack, job, fl)
    assert fl.calls == ["bili"]
    assert job.cred_handle == "cafebabe"

    # cred-fp 缺席/空（rc3）→ cred_handle 空——不按旧口径哈希
    fl2 = _FakeLgc(None)
    fe.resolve_cred_env(pack, job, fl2)
    assert job.cred_handle == ""


def test_resolve_cred_env_legacy_hash_without_domain(fe, tmp_path):
    """未声明 cred_domain：保持 needs.creds 原文哈希旧口径。"""
    cred = tmp_path / "cookie.txt"
    cred.write_bytes(b"cred-bytes")
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(f"""
[pack]
name = "cd"
[[lanes]]
name = "l"
exec = "x"
needs = {{ creds = ["{cred}"] }}
"""),
    )
    job = fe.Job(jobs_root=tmp_path / "jobs")
    job.journal.close()
    fe.resolve_cred_env(pack, job, None)
    expect = hashlib.sha256(b"cred-bytes").hexdigest()[:8]
    assert job.cred_handle == expect


def _stub_lgc(tmp_path, cred_fp_rc=0, cred_fp_out="cafebabe"):
    """最小 lgc stub：--version/has/key/get(miss)/lane probe/cred-fp。"""
    stub = tmp_path / "lgc-stub"
    stub.write_text(
        f"""#!/usr/bin/env bash
case "$1" in
  --version) echo "lgc 9.9-stub";;
  has) echo "lgc 9.9-stub"; echo "key get put neg release lane";;
  key) echo "kh-stub";;
  cred-fp) echo "{cred_fp_out}"; exit {cred_fp_rc};;
  get) exit 1;;
  *) exit 0;;
esac
"""
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def test_cred_domain_e2e_via_stub_lgc(tmp_path):
    """e2e：pack cred_domain + stub lgc cred-fp → lane 看到的
    ctx.cred_handle 是域指纹。"""
    stub = _stub_lgc(tmp_path)
    _pack(
        tmp_path,
        "cdom",
        f"""
[pack]
name = "cdom"
ns = "link-get"
kinds = ["article"]
cred_domain = "bili"
[match]
hosts = ["example.com"]
[identity]
keyexpr = "article:{{url}}"
[[lanes]]
name = "echo"
exec = "{ECHO}"
""",
    )
    env = _env(tmp_path)
    env["LGC_BIN"] = str(stub)
    p = run_cli(["run", "https://example.com/x", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert _envelope(p)["data"]["cred_handle"] == "cafebabe"


def test_cred_domain_rc3_falls_back_empty(tmp_path):
    """cred-fp rc3（域未知/无可读 cred）→ cred_handle 空，不炸。"""
    stub = _stub_lgc(tmp_path, cred_fp_rc=3, cred_fp_out="")
    _pack(
        tmp_path,
        "cdom",
        f"""
[pack]
name = "cdom"
ns = "link-get"
kinds = ["article"]
cred_domain = "bili"
[match]
hosts = ["example.com"]
[identity]
keyexpr = "article:{{url}}"
[[lanes]]
name = "echo"
exec = "{ECHO}"
""",
    )
    env = _env(tmp_path)
    env["LGC_BIN"] = str(stub)
    p = run_cli(["run", "https://example.com/x", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert _envelope(p)["data"]["cred_handle"] in ("", None)


# ------------------------------------------------------- selftest 体检


def _selftest_env(tmp_path):
    return {
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "LGC_HOME": str(tmp_path / "lgc-home"),
    }


def test_selftest_routes_coverage_fail(tmp_path):
    """[[routes]] 存在但某 kind 无臂覆盖 → 体检 ✗ 点名漏的 kind。"""
    _pack(
        tmp_path,
        "covbad",
        f"""
[pack]
name = "covbad"
ns = "link-get"
kinds = ["a", "b"]
[match]
hosts = ["example.com"]
[[lanes]]
name = "echo"
exec = "{ECHO}"
[[routes]]
kinds = ["a"]
lanes = ["echo"]
""",
    )
    p = run_cli(["selftest", "-p", "covbad"], _selftest_env(tmp_path))
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
    assert "✗" in p.stdout
    assert "'b'" in p.stdout or ", b" in p.stdout or " b" in p.stdout


def test_selftest_routes_catchall_covers(tmp_path):
    """无 kinds 限制的兜底臂覆盖全部 kind → 体检过。"""
    _pack(
        tmp_path,
        "covok",
        f"""
[pack]
name = "covok"
ns = "link-get"
kinds = ["a", "b"]
[match]
hosts = ["example.com"]
[[lanes]]
name = "echo"
exec = "{ECHO}"
[[routes]]
kinds = ["a"]
lanes = ["echo"]
[[routes]]
lanes = ["echo"]
""",
    )
    p = run_cli(["selftest", "-p", "covok"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)


def test_selftest_writes_cred_ns_maps_domain(tmp_path):
    """lane writes_cred='canvas-skill'（ns 名）→ NS_CRED_DOMAIN 映射到
    'canvas' cred domain → 体检 ✓ 不打红。"""
    _pack(
        tmp_path,
        "wcok",
        f"""
[pack]
name = "wcok"
ns = "canvas-skill"
kinds = ["article"]
[match]
hosts = ["example.com"]
[[lanes]]
name = "echo"
exec = "{ECHO}"
writes_cred = "canvas-skill"
""",
    )
    p = run_cli(["selftest", "-p", "wcok"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "writes_cred canvas-skill" in p.stdout


def test_selftest_writes_cred_unknown_fails(tmp_path):
    """writes_cred 映射不到任何已知 cred domain → 体检 ✗。"""
    _pack(
        tmp_path,
        "wcbad",
        f"""
[pack]
name = "wcbad"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["example.com"]
[[lanes]]
name = "echo"
exec = "{ECHO}"
writes_cred = "no-such-ns"
""",
    )
    p = run_cli(["selftest", "-p", "wcbad"], _selftest_env(tmp_path))
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
    assert "no-such-ns" in p.stdout


def test_selftest_cred_domain_membership(tmp_path):
    """cred_domain 声明须是 lgc CRED_FILES 已知域——'bili' 过、
    'bogus-dom' 打红（错拼域会静默产出空 cred_handle）。"""
    _pack(
        tmp_path,
        "cdok",
        f"""
[pack]
name = "cdok"
ns = "link-get"
kinds = ["article"]
cred_domain = "bili"
[match]
hosts = ["example.com"]
[[lanes]]
name = "echo"
exec = "{ECHO}"
""",
    )
    p = run_cli(["selftest", "-p", "cdok"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "cred_domain 'bili'" in p.stdout

    _pack(
        tmp_path,
        "cdbad",
        f"""
[pack]
name = "cdbad"
ns = "link-get"
kinds = ["article"]
cred_domain = "bogus-dom"
[match]
hosts = ["example.com"]
[[lanes]]
name = "echo"
exec = "{ECHO}"
""",
    )
    p2 = run_cli(["selftest", "-p", "cdbad"], _selftest_env(tmp_path))
    assert p2.returncode == 1, (p2.returncode, p2.stdout, p2.stderr)
    assert "bogus-dom" in p2.stdout


def test_params_gate_rejected_value_masked(tmp_path):
    """被拒的未知 param 值也不落 journal——错拼的秘参旗标（--param
    toke=PAT）同样按 '***' 掩码。"""
    env = _pgate_env(tmp_path)
    p = run_cli(
        [
            "run",
            "https://example.com/x",
            "--param",
            "toke=sekrit-typo-pat",
            "--json",
        ],
        env,
    )
    assert p.returncode == 2
    env_ = _envelope(p)
    jtext = Path(env_["journal"]).read_text()
    assert "sekrit-typo-pat" not in jtext
    assert '"toke": "***"' in jtext
