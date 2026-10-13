"""test_engine_surface.py — batch-6b pack.toml 新声明面测试（全离线）：

  bare_resolve 段（[[match.bare]] raw-token 重写，canon 之前）
  [params] 声明闸 + 豁免集 + secret 打码
  顶层 [kind_by_url]（regex→kind 新 schema）+ [identity].kind_by_url 存量
  routes 覆盖自检 / writes_cred 域校验（selftest --deploy）
  cred_domain → `lgc cred-fp` 委托 cred_handle

fixture pack + ctx_lane 回显车道，不触网络（127.0.0.1 host match +
FETCH_ENGINE_ALLOW_PRIVATE=1 直接过 SSRF 闸，lane 不发请求只回显 ctx）。
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
FIXTURES = ROOT / "tests" / "fixtures"
CTX_LANE = FIXTURES / "ctx_lane.py"


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
        # fixture host=127.0.0.1 走私网白名单——lane 不真发请求，纯粹过闸
        "FETCH_ENGINE_ALLOW_PRIVATE": "1",
    }


def write_pack(tmp_path, name, body):
    pdir = tmp_path / "packs" / name
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "pack.toml").write_text(body)
    return tmp_path / "packs"


def envelope_of(p):
    return json.loads(p.stdout.strip().splitlines()[-1])


def decisions(env_):
    return [json.loads(line) for line in Path(env_["journal"]).read_text().splitlines()]


def journal_text(env_):
    return Path(env_["journal"]).read_text()


def lane_toml(tpl):
    """TOML 模板里的 __LANE__ 占位符 → ctx_lane 实路径
    （不用 %/format：模板内含 {url}/{kind} 等 TOML 花括号字面量）。"""
    return tpl.replace("__LANE__", str(CTX_LANE))


CTX_LANE_TOML = lane_toml(
    """
[[lanes]]
name = "ctx_lane"
exec = "__LANE__"
budget_ms = 15000
"""
)


# ---------------------------------------------------------------- bare_resolve


BARE_PACK = (
    """
[pack]
name = "zzbare"
abi = 1
ns = "link-get"
kinds = ["article"]

[match]
hosts = ["127.0.0.1"]
schemes = ["http"]

[[match.bare]]
pattern = '^arxiv:(.+)$'
rewrite = 'http://127.0.0.1/abs/{1}'

[[match.bare]]
pattern = '^([0-9]{4,6})$'
rewrite = 'http://127.0.0.1/courses/{1}'

[[match.bare]]
pattern = '^([a-z-]+(?:\\.[A-Z]{2})?/[0-9]{7}(?:v[0-9]+)?)$'
rewrite = 'http://127.0.0.1/abs/{1}'

[identity]
keyexpr = "article:{url}"
"""
    + CTX_LANE_TOML
)


def test_bare_arxiv_prefix_rewrites(tmp_path):
    """'arxiv:ID' bare token → rewrite 成 URL → 路由到声明 pack → rc0。"""
    packs = write_pack(tmp_path, "zzbare", BARE_PACK)
    p = run_cli(["run", "arxiv:2401.00001", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    decs = decisions(env_)
    bare = [d for d in decs if d.get("stage") == "bare_resolve"]
    assert bare, "bare_resolve decision missing"
    assert bare[0]["pattern"] == "^arxiv:(.+)$"
    assert bare[0]["rewrite"] == "http://127.0.0.1/abs/{1}"
    assert bare[0]["target"] == "http://127.0.0.1/abs/2401.00001"
    assert any(d.get("stage") == "route" and d.get("pack") == "zzbare" for d in decs)
    assert env_["data"]["raw"] == "http://127.0.0.1/abs/2401.00001"


def test_bare_digits_rewrites_to_courses(tmp_path):
    """'97882' 裸课程号 → courses URL 臂命中。"""
    packs = write_pack(tmp_path, "zzbare", BARE_PACK)
    p = run_cli(["run", "97882", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    decs = decisions(env_)
    bare = [d for d in decs if d.get("stage") == "bare_resolve"]
    assert bare
    assert bare[0]["pattern"] == "^([0-9]{4,6})$"
    assert env_["data"]["raw"] == "http://127.0.0.1/courses/97882"


def test_bare_old_style_arxiv_id(tmp_path):
    """canon 劫持回归：'math.AG/0601234' 旧式 ID 带 archive 前缀——
    bare 规则先抓住，不落入 canon 的 dot-TLD 误归一。"""
    packs = write_pack(tmp_path, "zzbare", BARE_PACK)
    p = run_cli(["run", "math.AG/0601234", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["data"]["raw"] == "http://127.0.0.1/abs/math.AG/0601234"
    assert any(d.get("stage") == "bare_resolve" for d in decisions(env_))


def test_bare_nonmatching_passthrough(tmp_path):
    """无命中的 token 原样进 canon——不记 bare_resolve，不改动语义。"""
    packs = write_pack(tmp_path, "zzbare", BARE_PACK)
    p = run_cli(["run", "hello world", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    decs = decisions(env_)
    assert not any(d.get("stage") == "bare_resolve" for d in decs)
    canon = next(d for d in decs if d.get("stage") == "canon")
    assert canon["raw"] == "hello world"


def test_bare_canon_hijack_without_rule(fe, tmp_path):
    """对照组（无 bare 规则的现状行为，文档化）：'math.AG/0601234' 被 canon
    dot-TLD 规则误归一为 https://math.ag/0601234 —— 无匹配 pack → rc3。"""
    packs = write_pack(
        tmp_path,
        "plainp",
        """
[pack]
name = "plainp"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["example.com"]
[identity]
keyexpr = "article:{url}"
"""
        + CTX_LANE_TOML,
    )
    raw, err = fe.canon("math.AG/0601234")
    assert err is None
    assert raw == "https://math.ag/0601234"  # canon 劫持——这就是要修的现行 bug
    p = run_cli(["run", "math.AG/0601234", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    decs = decisions(env_)
    assert not any(d.get("stage") == "bare_resolve" for d in decs)
    canon = next(d for d in decs if d.get("stage") == "canon")
    assert canon["raw"] == "https://math.ag/0601234"


def test_bare_forced_pack_scopes_table(tmp_path):
    """-p 时只扫被指定 pack 的 bare 表：别的 pack 的规则不生效。"""
    packs = write_pack(tmp_path, "zzbare", BARE_PACK)
    write_pack(
        tmp_path,
        "otherp",
        """
[pack]
name = "otherp"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["example.org"]
[identity]
keyexpr = "article:{url}"
"""
        + CTX_LANE_TOML,
    )
    # -p otherp：zzbare 的 arxiv: 规则不扫 → token 不重写 → 无 pack 匹配 rc3
    p = run_cli(
        ["run", "arxiv:2401.00001", "-p", "otherp", "--json"],
        base_env(tmp_path, packs),
    )
    env_ = envelope_of(p)
    decs = decisions(env_)
    assert not any(d.get("stage") == "bare_resolve" for d in decs)
    assert any(d.get("stage") == "route" and d.get("pack") == "otherp" for d in decs)
    # 'arxiv:x' 不重写 → canon 原样 → forced pack 下 SSRF 拒（scheme 不合法）
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    # -p zzbare：自己的表照常生效
    p2 = run_cli(
        ["run", "arxiv:2401.00001", "-p", "zzbare", "--json"],
        base_env(tmp_path, packs),
    )
    assert p2.returncode == 0, (p2.returncode, p2.stdout, p2.stderr)
    assert envelope_of(p2)["data"]["raw"] == "http://127.0.0.1/abs/2401.00001"


def test_bare_applied_once_no_rescan(tmp_path):
    """重写产物不再回扫——rewrite 结果若也形似 bare pattern，不得二次重写。"""
    packs = write_pack(
        tmp_path,
        "zzbare",
        """
[pack]
name = "zzbare"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["127.0.0.1"]
[[match.bare]]
pattern = '^arxiv:(.+)$'
rewrite = 'arxiv2:{1}'
[[match.bare]]
pattern = '^arxiv2:(.+)$'
rewrite = 'http://127.0.0.1/abs/{1}'
[identity]
keyexpr = "article:{url}"
"""
        + CTX_LANE_TOML,
    )
    # 首中 'arxiv:' → 'arxiv2:x'；若重扫会再变 URL——断言只跳一次
    p = run_cli(["run", "arxiv:x", "--json"], base_env(tmp_path, packs))
    env_ = envelope_of(p)
    decs = decisions(env_)
    bare = [d for d in decs if d.get("stage") == "bare_resolve"]
    assert len(bare) == 1
    assert bare[0]["target"] == "arxiv2:x"
    # 'arxiv2:x' 不是 URL → canon 原样 → 无 pack 匹配 rc3（证明没二次重写成 http）
    assert p.returncode == 3
    canon = next(d for d in decs if d.get("stage") == "canon")
    assert canon["raw"] == "arxiv2:x"


def test_bare_whole_match_group0(tmp_path):
    """{0}=整组、{N}=捕获组 N——验证 {0} 展开口径。"""
    packs = write_pack(
        tmp_path,
        "zzbare",
        """
[pack]
name = "zzbare"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["127.0.0.1"]
[[match.bare]]
pattern = '^id-([0-9]+)$'
rewrite = 'http://127.0.0.1/e/{0}/{1}'
[identity]
keyexpr = "article:{url}"
"""
        + CTX_LANE_TOML,
    )
    p = run_cli(["run", "id-42", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert envelope_of(p)["data"]["raw"] == "http://127.0.0.1/e/id-42/42"


# ---------------------------------------------------------------- [params] 闸


GATE_PACK = (
    """
[pack]
name = "gatep"
abi = 1
ns = "link-get"
kinds = ["article"]

[match]
hosts = ["127.0.0.1"]
schemes = ["http"]

[identity]
keyexpr = "article:{url}"
key_params = ["flavor"]
satisfies = { qlvl = { param = "qlvl", type = "int" } }

[params]
depth = { type = "int", desc = "枚举深度" }
token = { type = "str", secret = true, desc = "PAT" }
"""
    + CTX_LANE_TOML
)


def _gate_pack(tmp_path):
    return write_pack(tmp_path, "gatep", GATE_PACK)


def test_params_gate_unknown_rejected(tmp_path):
    """未知 --param → rc2，stderr 列出合法集（含声明键 + 保留名）。"""
    packs = _gate_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "bogus=1"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "bogus" in p.stderr
    assert "depth" in p.stderr
    assert "token" in p.stderr
    assert "kind" in p.stderr  # 保留名也在合法集内


@pytest.mark.parametrize(
    "kv",
    [
        "depth=3",  # [params] 声明
        "refresh",  # engine 保留
        "kind=article",  # engine 保留
        "flavor=+x",  # key_params 豁免
        "qlvl=2",  # satisfies param 豁免
    ],
)
def test_params_gate_exemptions_pass(tmp_path, kv):
    packs = _gate_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", kv, "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (kv, p.returncode, p.stdout, p.stderr)


def test_params_gate_routes_params_key_exempt(tmp_path):
    """routes.params / lane params_gate 声明的键即使不在 [params] 也通过。"""
    packs = write_pack(
        tmp_path,
        "routep",
        lane_toml(
            """
[pack]
name = "routep"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["127.0.0.1"]
schemes = ["http"]
[identity]
keyexpr = "article:{url}"
[[lanes]]
name = "ctx_lane"
exec = "__LANE__"
params_gate = { lg = ["yes"] }
[[routes]]
kinds = ["article"]
params = { mode = "special" }
lanes = ["ctx_lane"]
[[routes]]
lanes = ["ctx_lane"]
"""
        ),
    )
    # mode（routes.params 键）+ lg（params_gate 键）皆未声明 [params] 但合法
    p = run_cli(
        [
            "run",
            "http://127.0.0.1/x",
            "--param",
            "mode=special",
            "--param",
            "lg=yes",
            "--json",
        ],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    # 未声明键照旧拒
    p2 = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "nope=1"],
        base_env(tmp_path, packs),
    )
    assert p2.returncode == 2


def test_params_secret_masked_in_journal(tmp_path):
    """secret=true 参数：journal 记键名 + '***'，值全文不出现。"""
    packs = _gate_pack(tmp_path)
    p = run_cli(
        [
            "run",
            "http://127.0.0.1/x",
            "--param",
            "token=sekrit-pat-9",
            "--json",
        ],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    jtext = journal_text(env_)
    assert "sekrit-pat-9" not in jtext
    gate = [
        d
        for d in decisions(env_)
        if d.get("stage") == "admit" and d.get("gate") == "params"
    ]
    assert gate
    assert gate[0]["provided"]["token"] == "***"


def test_params_gate_decision_logged(tmp_path):
    """param 闸 journal 行：provided 表原样带（非 secret 不打码）。"""
    packs = _gate_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "depth=3", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0
    gate = [
        d
        for d in decisions(envelope_of(p))
        if d.get("stage") == "admit" and d.get("gate") == "params"
    ]
    assert gate
    assert gate[0]["provided"]["depth"] == "3"
    assert "rejected" not in gate[0]


def test_params_gate_rejected_values_masked(tmp_path):
    """被拒的未知键同样不落明文——错拼的秘参旗标不该把值写进 journal。"""
    packs = _gate_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "tokne=sekrit-oops", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 2
    env_ = envelope_of(p)
    assert "sekrit-oops" not in journal_text(env_)


# ---------------------------------------------------------------- kind_by_url


def test_kind_by_url_toplevel_regex_to_kind(tmp_path):
    """顶层 [kind_by_url]（regex→kind 新 schema）：首个命中正则定 kind。"""
    packs = write_pack(
        tmp_path,
        "kbup",
        """
[pack]
name = "kbup"
ns = "link-get"
kinds = ["article", "doc"]
[match]
hosts = ["127.0.0.1"]
schemes = ["http"]
[kind_by_url]
'/doc/' = 'doc'
'/a/' = 'article'
[identity]
keyexpr = "{kind}:{url}"
"""
        + CTX_LANE_TOML,
    )
    p = run_cli(["run", "http://127.0.0.1/doc/9", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["data"]["kind"] == "doc"
    ident = next(d for d in decisions(env_) if d.get("stage") == "identity")
    assert ident["kind"] == "doc"
    assert "kind_miss" not in ident

    # 无命中 → kinds[0] 兜底 + kind_miss 标记（fallback 语义不变）
    p2 = run_cli(["run", "http://127.0.0.1/zzz", "--json"], base_env(tmp_path, packs))
    assert p2.returncode == 0
    ident2 = next(d for d in decisions(envelope_of(p2)) if d.get("stage") == "identity")
    assert ident2["kind"] == "article"
    assert ident2.get("kind_miss")


def test_kind_by_url_identity_legacy_still_works(fe, tmp_path):
    """[identity].kind_by_url（kind→regex 存量面）不受新表影响。"""

    class _NoLgc:
        def available(self):
            return False

    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(
            """
[pack]
name = "z"
kinds = ["ans", "art"]
[identity]
kind_by_url = { ans = 'answer/', art = '/p/' }
"""
        ),
    )
    ident = fe.make_identity(pack, "https://x/answer/1", {}, _NoLgc())
    assert ident["kind"] == "ans"


def test_kind_by_url_merges_both_surfaces(fe, tmp_path):
    """两声明面合并进 {kind: regex} 内部表；顶层 [kind_by_url] 同 kind 覆盖。"""
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(
            """
[pack]
name = "z"
kinds = ["ans", "doc"]
[identity]
kind_by_url = { ans = 'answer/', doc = 'identity-doc/' }
[kind_by_url]
'/doc/' = 'doc'
"""
        ),
    )
    # identity 面保留 ans；顶层面覆盖 doc 的正则
    assert pack.kind_by_url["ans"] == "answer/"
    assert pack.kind_by_url["doc"] == "/doc/"


# ------------------------------------------------------- routes 覆盖 / catch-all


def test_select_lanes_catchall_arm(fe, tmp_path):
    """无 kinds 限制的臂 = 兜底臂：任何 kind 都中（selftest 覆盖口径同源）。"""
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(
            """
[pack]
name = "z"
kinds = ["a", "b"]
[[lanes]]
name = "l1"
exec = "x"
[[routes]]
kinds = ["a"]
lanes = ["l1"]
[[routes]]
lanes = ["l1"]
"""
        ),
    )
    sel = fe.select_lanes(pack, {"kind": "b", "params": {}})
    assert [lc["name"] for lc in sel] == ["l1"]


def test_select_lanes_star_catchall(fe, tmp_path):
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(
            """
[pack]
name = "z"
kinds = ["a", "b"]
[[lanes]]
name = "l1"
exec = "x"
[[routes]]
kinds = ["*"]
lanes = ["l1"]
"""
        ),
    )
    sel = fe.select_lanes(pack, {"kind": "b", "params": {}})
    assert [lc["name"] for lc in sel] == ["l1"]


def _selftest_env(tmp_path):
    return {
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
    }


def test_selftest_routes_coverage_fail(tmp_path):
    """pack.kinds 有 kind 无臂覆盖 → deploy 体检打红。"""
    write_pack(
        tmp_path,
        "covp",
        lane_toml(
            """
[pack]
name = "covp"
ns = "link-get"
kinds = ["a", "b"]
[[lanes]]
name = "l1"
exec = "__LANE__"
[[routes]]
kinds = ["a"]
lanes = ["l1"]
"""
        ),
    )
    p = run_cli(["selftest", "-p", "covp"], _selftest_env(tmp_path))
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
    assert "✗" in p.stdout
    assert "b" in p.stdout


def test_selftest_routes_coverage_catchall_ok(tmp_path):
    """兜底臂（无 kinds）覆盖全部 kind → 体检绿。"""
    write_pack(
        tmp_path,
        "covok",
        lane_toml(
            """
[pack]
name = "covok"
ns = "link-get"
kinds = ["a", "b"]
[[lanes]]
name = "l1"
exec = "__LANE__"
[[routes]]
kinds = ["a"]
lanes = ["l1"]
[[routes]]
lanes = ["l1"]
"""
        ),
    )
    p = run_cli(["selftest", "-p", "covok"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "routes 覆盖" in p.stdout


def test_selftest_routes_coverage_star_ok(tmp_path):
    """kinds=['*'] 臂同样兜全部。"""
    write_pack(
        tmp_path,
        "covstar",
        lane_toml(
            """
[pack]
name = "covstar"
ns = "link-get"
kinds = ["a", "b"]
[[lanes]]
name = "l1"
exec = "__LANE__"
[[routes]]
kinds = ["*"]
lanes = ["l1"]
"""
        ),
    )
    p = run_cli(["selftest", "-p", "covstar"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)


# ------------------------------------------------------- writes_cred 自检


def test_selftest_writes_cred_ns_maps_domain(tmp_path):
    """writes_cred='canvas-skill'（ns 名）→ NS_CRED_DOMAIN 映射 'canvas' ∈
    CRED_DOMAINS → 体检绿（映射口径=domain 名而非 ns 名）。"""
    write_pack(
        tmp_path,
        "wcp",
        lane_toml(
            """
[pack]
name = "wcp"
ns = "link-get"
kinds = ["article"]
writes_cred = "canvas-skill"
[[lanes]]
name = "l1"
exec = "__LANE__"
"""
        ),
    )
    p = run_cli(["selftest", "-p", "wcp"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "writes_cred" in p.stdout


def test_selftest_writes_cred_domain_direct(tmp_path):
    """writes_cred 直接写 domain 名（'bili'）也合法。"""
    write_pack(
        tmp_path,
        "wcd",
        lane_toml(
            """
[pack]
name = "wcd"
ns = "link-get"
kinds = ["article"]
writes_cred = "bili"
[[lanes]]
name = "l1"
exec = "__LANE__"
"""
        ),
    )
    p = run_cli(["selftest", "-p", "wcd"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)


def test_selftest_writes_cred_lane_level(tmp_path):
    """lane 级 writes_cred（canvas-mint 存量面）同样过自检。"""
    write_pack(
        tmp_path,
        "wcl",
        lane_toml(
            """
[pack]
name = "wcl"
ns = "link-get"
kinds = ["enum"]
[[lanes]]
name = "mint"
exec = "__LANE__"
writes_cred = "canvas-skill"
"""
        ),
    )
    p = run_cli(["selftest", "-p", "wcl"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)


def test_selftest_writes_cred_bogus_fails(tmp_path):
    """writes_cred 指到未知 ns/domain → 体检打红。"""
    write_pack(
        tmp_path,
        "wcb",
        lane_toml(
            """
[pack]
name = "wcb"
ns = "link-get"
kinds = ["article"]
writes_cred = "bogus-ns"
[[lanes]]
name = "l1"
exec = "__LANE__"
"""
        ),
    )
    p = run_cli(["selftest", "-p", "wcb"], _selftest_env(tmp_path))
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
    assert "bogus-ns" in p.stdout


def test_selftest_cred_domain_validated(tmp_path):
    """cred_domain 声明须是 lgc CRED_FILES 已知域——未知域体检打红。"""
    write_pack(
        tmp_path,
        "cdok",
        lane_toml(
            """
[pack]
name = "cdok"
ns = "link-get"
kinds = ["article"]
cred_domain = "bili"
[[lanes]]
name = "l1"
exec = "__LANE__"
"""
        ),
    )
    p = run_cli(["selftest", "-p", "cdok"], _selftest_env(tmp_path))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    write_pack(
        tmp_path,
        "cdbad",
        lane_toml(
            """
[pack]
name = "cdbad"
ns = "link-get"
kinds = ["article"]
cred_domain = "nosuchdomain"
[[lanes]]
name = "l1"
exec = "__LANE__"
"""
        ),
    )
    p2 = run_cli(["selftest", "-p", "cdbad"], _selftest_env(tmp_path))
    assert p2.returncode == 1, (p2.returncode, p2.stdout, p2.stderr)
    assert "nosuchdomain" in p2.stdout


# ------------------------------------------------------- cred_domain 委托


class _FakeLgc:
    def __init__(self, fp):
        self._fp = fp

    def cred_fp(self, _domain):
        return self._fp


def test_cred_domain_delegates_to_lgc(fe, tmp_path):
    """pack.cred_domain → cred_handle 直接取 lgc cred-fp 结果，不哈希文件。"""
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(
            '[pack]\nname = "z"\ncred_domain = "canvas"\n'
            '[[lanes]]\nname = "l"\nexec = "x"\n'
        ),
    )
    job = fe.Job(jobs_root=tmp_path / "jobs")
    fe.resolve_cred_env(pack, job, _FakeLgc("cafebabe"))
    assert job.cred_handle == "cafebabe"
    job.journal.close()

    # rc3/空 → cred_handle 空（不坍缩成 'anon' 哈希）
    job2 = fe.Job(jobs_root=tmp_path / "jobs2")
    fe.resolve_cred_env(pack, job2, _FakeLgc(None))
    assert job2.cred_handle == ""
    job2.journal.close()


def test_cred_domain_absent_keeps_file_hash(fe, tmp_path):
    """无 cred_domain 的 pack 保留 needs.creds 原文哈希旧口径。"""
    cred = tmp_path / "tok"
    cred.write_text("secret-token")
    pack = fe.Pack(
        tmp_path / "pack.toml",
        tomllib.loads(
            '[pack]\nname = "z"\n[[lanes]]\nname = "l"\nexec = "x"\n'
            f'needs = {{ creds = ["{cred}"] }}\n'
        ),
    )
    job = fe.Job(jobs_root=tmp_path / "jobs")
    fe.resolve_cred_env(pack, job, _FakeLgc("should-not-be-used"))
    assert job.cred_handle == hashlib.sha256(b"secret-token").hexdigest()[:8]
    job.journal.close()


class _StubLgcRun:
    """Lgc._run 罐装：验证 cred_fp 方法的 argv/rc 解析。"""

    def __init__(self, rc, out):
        self._rc, self._out = rc, out
        self.argv = None

    def __call__(self, args, **_kw):
        self.argv = args
        return self._rc, self._out, ""


def test_lgc_cred_fp_contract(fe, tmp_path, monkeypatch):
    """Lgc.cred_fp：shell 'cred-fp <dom>'；rc0+非空 → fp，rc3/空 → None。"""
    j = fe.Journal("t", tmp_path / "j")
    lgc = fe.Lgc(journal=j)
    stub = _StubLgcRun(0, "cafebabe\n")
    monkeypatch.setattr(lgc, "_run", stub)
    monkeypatch.setattr(lgc, "_avail", True)
    assert lgc.cred_fp("canvas") == "cafebabe"
    assert stub.argv == ["cred-fp", "canvas"]

    stub2 = _StubLgcRun(3, "")
    monkeypatch.setattr(lgc, "_run", stub2)
    assert lgc.cred_fp("canvas") is None
    j.close()


def test_lgc_cred_fp_lgc_absent(fe, tmp_path, monkeypatch):
    j = fe.Journal("t", tmp_path / "j")
    lgc = fe.Lgc(journal=j)
    monkeypatch.setattr(lgc, "_avail", False)
    assert lgc.cred_fp("canvas") is None
    j.close()


_STUB_LGC_TEMPLATE = """#!/usr/bin/env python3
import sys
a = sys.argv[1:]
if not a:
    sys.exit(2)
if a[0] == '--version':
    print('lgc 9.9-stub')
    sys.exit(0)
if a[0] == 'has':
    print('lgc 9.9-stub')
    sys.exit(0)
if a[0] == 'cred-fp':
    %s
if a[0] == 'key':
    sys.exit(1)
if a[0] == 'get':
    sys.exit(1)
if a[0] == 'lane':
    sys.exit(0)
sys.exit(0)
"""


def _write_stub_lgc(tmp_path, cred_fp_body):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "lgc"
    stub.write_text(_STUB_LGC_TEMPLATE % cred_fp_body)
    stub.chmod(0o755)
    return stub


def test_e2e_cred_domain_via_stub_lgc(tmp_path):
    """端到端：LGC_BIN stub 应 cred-fp → cred_handle 进 lane ctx。"""
    stub = _write_stub_lgc(tmp_path, "print('cafebabe')\n    sys.exit(0)")
    packs = write_pack(
        tmp_path,
        "credp",
        """
[pack]
name = "credp"
ns = "link-get"
kinds = ["article"]
cred_domain = "canvas"
[match]
hosts = ["127.0.0.1"]
schemes = ["http"]
[identity]
keyexpr = "article:{url}"
"""
        + CTX_LANE_TOML,
    )
    env = base_env(tmp_path, packs)
    env["LGC_BIN"] = str(stub)
    p = run_cli(["run", "http://127.0.0.1/x", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert envelope_of(p)["data"]["cred_handle"] == "cafebabe"


def test_e2e_cred_domain_stub_rc3_empty_handle(tmp_path):
    """cred-fp rc3（无可读 cred 文件）→ cred_handle 空，不沿用文件哈希。"""
    stub = _write_stub_lgc(tmp_path, "sys.exit(3)")
    cred = tmp_path / "tok"
    cred.write_text("secret-token")
    packs = write_pack(
        tmp_path,
        "credp",
        lane_toml(
            f"""
[pack]
name = "credp"
ns = "link-get"
kinds = ["article"]
cred_domain = "canvas"
[match]
hosts = ["127.0.0.1"]
schemes = ["http"]
[identity]
keyexpr = "article:{{url}}"
[[lanes]]
name = "ctx_lane"
exec = "__LANE__"
budget_ms = 15000
needs = {{ creds = ["{cred}"] }}
"""
        ),
    )
    env = base_env(tmp_path, packs)
    env["LGC_BIN"] = str(stub)
    p = run_cli(["run", "http://127.0.0.1/x", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    # cred_domain 包完全替换文件哈希口径——不是 sha256('secret-token')[:8]
    assert envelope_of(p)["data"]["cred_handle"] == ""
