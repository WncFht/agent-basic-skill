"""test_machine_surface.py — batch-6e 机读面测试（全离线）：

  run --plan：dry-run 决策面（bare_resolve→canon→identity→route→admit 照跑，
    不 spawn 车道、不建 inflight claim、不写 entry/neg/cred；lgc 探针计数/
    GC 与真跑同质——评估面非冻结面；plan dict 出 stdout）
  packs [--json]：已加载 pack 的机读面列表（{packs,errors} 形；真 packs/ 断言）
  envelope.hint：class → 下一步动作提示（dep_absent/notcovered/lane_crash 有
    hint；rc0/rc2 无 hint 键）；--param json 透传同进 JSON 模式

fixture pack + ctx_lane 回显车道，不触网络（127.0.0.1 host match +
FETCH_ENGINE_ALLOW_PRIVATE=1 过 SSRF 闸，lane 在 --plan 下根本不跑）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
FIXTURES = ROOT / "tests" / "fixtures"
CTX_LANE = FIXTURES / "ctx_lane.py"


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


def lane_toml(tpl):
    """__LANE__ 占位 → ctx_lane 实路径（模板含 {url}/{kind} 字面量，不用 format）。"""
    return tpl.replace("__LANE__", str(CTX_LANE))


def envelope_of(p):
    return json.loads(p.stdout.strip().splitlines()[-1])


def journal_records(env_):
    return [json.loads(line) for line in Path(env_["journal"]).read_text().splitlines()]


def assert_no_exec_no_inflight(env_, tmp_path):
    """plan 硬断言：journal 无 stage=exec 行；lgc inflight 无 *.d 认领残留
    （ensure_dirs 会建空 inflight/ 目录本身——查内容物而非目录缺席）。
    lgc-home 必须已被探针创建——否则 inflight 检查空转 vacuous。"""
    recs = journal_records(env_)
    assert not any(r.get("stage") == "exec" for r in recs)
    lgc_home = tmp_path / "lgc-home"
    assert lgc_home.exists(), "lgc 探针未跑（LGC_HOME 未建）——inflight 断言无效"
    for d in lgc_home.rglob("inflight"):
        assert not list(d.iterdir()), f"inflight 认领残留: {list(d.iterdir())}"


# ---------------------------------------------------------------- run --plan

PLAN_PACK = lane_toml(
    """
[pack]
name = "planp"
abi = 1
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

[[lanes]]
name = "needs_lane"
exec = "__LANE__"
needs = { tools = ["no-such-tool-zzz"] }
"""
)


def _plan_pack(tmp_path):
    return write_pack(tmp_path, "planp", PLAN_PACK)


def test_plan_json_lists_lanes_and_gates(tmp_path):
    """--plan --json：rc0 + plan dict；车道逐条带 ok/拒因；车道不真跑。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--plan", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["rc"] == 0
    assert "data" not in env_  # ctx_lane 没跑——无 data 终态
    plan = env_["plan"]
    assert plan["target_raw"] == "http://127.0.0.1/x"
    assert plan["pack"] == "planp"
    assert plan["kind"] == "article"
    assert plan["key"] == "article:http://127.0.0.1/x"
    assert plan["base_key"] == plan["key"]
    # lgc 在场 → miss；缺席 → off（两态都合法，不断言死值）
    assert plan["cache_verdict"] in ("miss", "off")
    lanes = {ln["name"]: ln for ln in plan["lanes"]}
    assert set(lanes) == {"ctx_lane", "needs_lane"}
    assert lanes["ctx_lane"]["ok"] is True
    assert "gate" not in lanes["ctx_lane"]
    assert lanes["needs_lane"]["ok"] is False
    assert lanes["needs_lane"]["gate"] == "needs"
    assert lanes["needs_lane"]["missing"] == ["tool:no-such-tool-zzz"]
    assert plan["runnable"] == 1  # 消费方读此数判可跑性，不猜 rc0
    assert_no_exec_no_inflight(env_, tmp_path)


def test_plan_forced_pack(tmp_path):
    """-p 强制 pack 同支 --plan：route decision forced，plan.pack 落名。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/y", "-p", "planp", "--plan", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["plan"]["pack"] == "planp"
    recs = journal_records(env_)
    assert any(r.get("stage") == "route" and r.get("forced") for r in recs)
    assert_no_exec_no_inflight(env_, tmp_path)


def test_plan_via_param_passthrough(tmp_path):
    """壳 --plan → --param plan 透传路径：同进 plan 模式。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "plan", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "plan" in envelope_of(p)


def test_plan_human_output(tmp_path):
    """非 --json：人类摘要——pack/kind 行 + 每 lane 一行 ok/拒因。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--plan"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "pack=planp" in p.stdout
    assert "kind=article" in p.stdout
    assert "lane ctx_lane: ok" in p.stdout
    assert "lane needs_lane: 拒(needs" in p.stdout
    assert "no-such-tool-zzz" in p.stdout


# ---------------------------------------------------------------- packs 子命令


def test_packs_json_real_dir(tmp_path):
    """packs --json 指向真 packs/（无 env 覆盖）：{packs,errors} 形，≥8 pack，
    字段结构齐；干净目录不带 errors 键。"""
    env = base_env(tmp_path)
    del env["FETCH_ENGINE_PACKS"]
    p = run_cli(["packs", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    out = json.loads(p.stdout.strip())
    assert "errors" not in out
    rows = out["packs"]
    names = {r["name"] for r in rows}
    assert names >= {
        "arxiv",
        "canvas",
        "zhihu",
        "generic",
        "youtube",
        "bilibili",
        "wechat",
        "media",
    }
    for r in rows:
        assert isinstance(r["name"], str)
        assert r["name"]
        assert isinstance(r["desc"], str)
        assert isinstance(r["kinds"], list)
        assert r["kinds"]
        assert isinstance(r["hosts"], list)
        assert r["hosts"]
        assert isinstance(r["schemes"], list)
        assert r["schemes"]
        assert isinstance(r["lanes"], list)
        assert all(isinstance(ln, str) for ln in r["lanes"])
        assert isinstance(r["bare"], bool)
    by_name = {r["name"]: r for r in rows}
    assert by_name["zhihu"]["cred_domain"] == "zhihu"
    assert by_name["arxiv"]["bare"] is True
    assert by_name["zhihu"]["bare"] is False
    assert "media-get" in by_name["media"]["lanes"]


def test_packs_human_table(tmp_path):
    """缺省人类表：rc0 + 每 pack 一行摘要。"""
    env = base_env(tmp_path)
    del env["FETCH_ENGINE_PACKS"]
    p = run_cli(["packs"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "zhihu" in p.stdout
    assert "kinds=" in p.stdout


def test_packs_json_fixture_dir(tmp_path):
    """fixture packs 目录同形输出——bare 无声明 → false，cred_domain 键缺席。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(["packs", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    out = json.loads(p.stdout.strip())
    rows = out["packs"]
    assert [r["name"] for r in rows] == ["planp"]
    r = rows[0]
    assert r["bare"] is False
    assert "cred_domain" not in r
    assert r["lanes"] == ["ctx_lane", "needs_lane"]
    assert r["hosts"] == ["127.0.0.1"]
    assert r["schemes"] == ["http"]


def test_packs_json_broken_toml_surfaces_error(tmp_path):
    """坏 TOML 的 pack 不静默丢：errors 键带路径+错因（机读面漏报比炸更糟）。"""
    packs = _plan_pack(tmp_path)
    bad = packs / "brokenp"
    bad.mkdir()
    (bad / "pack.toml").write_text("this is [ not toml")
    p = run_cli(["packs", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    out = json.loads(p.stdout.strip())
    assert [r["name"] for r in out["packs"]] == ["planp"]
    assert len(out["errors"]) == 1
    assert "brokenp" in out["errors"][0]


# ---------------------------------------------------------------- envelope.hint

GATED_PACK = lane_toml(
    """
[pack]
name = "gatedp"
ns = "link-get"
kinds = ["article"]
[match]
hosts = ["127.0.0.1"]
schemes = ["http"]
[identity]
keyexpr = "article:{url}"
[[lanes]]
name = "needs_lane"
exec = "__LANE__"
needs = { tools = ["no-such-tool-zzz"] }
"""
)


def test_hint_dep_absent(tmp_path):
    """全车道 needs 闸死 → rc5 dep_absent + hint 指 selftest --deploy。"""
    packs = write_pack(tmp_path, "gatedp", GATED_PACK)
    p = run_cli(["run", "http://127.0.0.1/x", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["class"] == "dep_absent"
    assert "selftest" in env_["hint"]


def test_hint_notcovered(tmp_path):
    """无 pack 覆盖 → rc3 notcovered + hint 含'车道'。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://nonexistent.example.com/x", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["class"] == "notcovered"
    assert "车道" in env_["hint"]


def test_hint_absent_on_rc0(tmp_path):
    """rc0 envelope 不带 hint 键。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(["run", "http://127.0.0.1/x", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "hint" not in envelope_of(p)


def test_hint_absent_on_rc2_usage(tmp_path):
    """rc2 usage（未知 param）同样不带 hint。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "bogus=1", "--json"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert "hint" not in env_


def test_hint_lane_crash(tmp_path):
    """lane 非 JSONL 输出退 2 → lane_crash + hint 指 stderr.log。"""
    lane = tmp_path / "crash.py"
    lane.write_text("#!/usr/bin/env python3\nimport sys\nprint('junk')\nsys.exit(2)\n")
    lane.chmod(0o755)
    body = (
        '[pack]\nname = "crashp"\nns = "link-get"\nkinds = ["article"]\n'
        '[match]\nhosts = ["127.0.0.1"]\nschemes = ["http"]\n'
        '[identity]\nkeyexpr = "article:{url}"\n'
        '[[lanes]]\nname = "crash"\nexec = "' + str(lane) + '"\n'
    )
    packs = write_pack(tmp_path, "crashp", body)
    p = run_cli(["run", "http://127.0.0.1/x", "--json"], base_env(tmp_path, packs))
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = envelope_of(p)
    assert env_["class"] == "lane_crash"
    assert "stderr" in env_["hint"]


def test_param_json_passthrough_enables_json(tmp_path):
    """link-get 透传形 --param json 同进 JSON 模式——机读面经壳可达。"""
    packs = _plan_pack(tmp_path)
    p = run_cli(
        ["run", "http://127.0.0.1/x", "--param", "json", "--plan"],
        base_env(tmp_path, packs),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = json.loads(p.stdout.strip().splitlines()[-1])
    assert "plan" in env_  # 人类摘要行未出——stdout 是可解析 JSON
