"""test_phase3.py — Phase 3 e2e: zhihu-style decomposed pack via routes.

Fixture pack mirrors packs/zhihu/pack.toml: [[routes]] kind×params → ordered
lane arms, kind_required, probe_base_variants base-key probe chain,
store="base", fail_note, base_key lane accounting, per-lane rc_map (shim),
flag_params, needs.env.

Stub connectors are FILE-controlled (rc.<name> files + calls.log in the
fixture lanes dir) because lane_env whitelists env — connectors never see
test env vars. No real network: stubs never connect.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
NS = "zhihu-skill"  # pack-owned ns — engine must honor pack.ns, not link-get

STUB = """#!/bin/bash
# argv: <artifact_dir> [args...] — logs "<name> <args>" to lanes/calls.log,
# exit code from lanes/rc.<name> (default 0); rc0 writes <adir>/<name>.md
set -u
here="$(cd "$(dirname "$0")" && pwd)"
name="$(basename "$0")"
adir="$1"; shift
echo "$name $*" >> "$here/calls.log"
rc=0
[ -f "$here/rc.$name" ] && rc="$(tr -d '[:space:]' < "$here/rc.$name")"
if [ "$rc" != "0" ]; then exit "$rc"; fi
mkdir -p "$adir"
printf 'stub %s fetched %s\\n' "$name" "$*" > "$adir/$name.md"
exit 0
"""

CONNECTORS = ["zhcli", "tardis", "scraper", "jina", "firecrawl"]

# lane/route 结构镜像 packs/zhihu/pack.toml（zhihu-get:435-515 级联逐一对齐）
PACK_TOML = """
[pack]
name = "zhifix"
abi = 1
ns = "zhihu-skill"
kinds = ["ans", "art", "q", "col", "ppl", "zv", "pin", "misc"]
kind_required = true

[match]
hosts = ["127.0.0.1"]
schemes = ["http"]

[identity]
keyexpr = "{kind}:{id}{variant}"
key_params = ["variant"]
probe_base_variants = ["+f"]
kind_by_url = { ans = 'answer/[0-9]+', art = '/p/[0-9]+', q = 'question/[0-9]+', col = 'column/[A-Za-z0-9_-]+', ppl = 'people/[A-Za-z0-9_-]+', zv = 'zvideo/[0-9]+', pin = 'pin/[0-9]+', misc = 'misc/[0-9]+' }
capture = { id = { ans = 'answer/([0-9]+)', art = '/p/([0-9]+)', q = 'question/([0-9]+)', col = 'column/([A-Za-z0-9_-]+)', ppl = 'people/([A-Za-z0-9_-]+)', zv = 'zvideo/([0-9]+)', pin = 'pin/([0-9]+)', misc = 'misc/([0-9]+)' } }

[[lanes]]
name = "tardis"
exec = "monolith"
connector = "lanes/tardis"
needs = { tools = ["bash"] }
fail_note = false
rc_map = { "2" = "notcovered" }
[lanes.monolith]
argv = ["{artifact_dir}", "{url}"]

[[lanes]]
name = "jina"
exec = "monolith"
connector = "lanes/jina"
store = "base"
needs = { tools = ["bash"] }
[lanes.monolith]
argv = ["{artifact_dir}", "{url}"]

[[lanes]]
name = "firecrawl"
exec = "monolith"
connector = "lanes/firecrawl"
store = "base"
needs = { tools = ["bash"], env = ["ZHIFIX_FC_KEY"] }
[lanes.monolith]
argv = ["{artifact_dir}", "{url}"]

[[lanes]]
name = "scraper"
exec = "monolith"
connector = "lanes/scraper"
needs = { tools = ["bash"] }
[lanes.monolith]
argv = ["{artifact_dir}", "{url}"]
flag_params = { comments = "--comments" }

[[lanes]]
name = "zhcli"
exec = "monolith"
connector = "lanes/zhcli"
needs = { tools = ["bash"] }
[lanes.monolith]
argv = ["{artifact_dir}", "{kind}", "{url}"]

[[routes]]
kinds = ["ans"]
params = { comments = true }
lanes = ["scraper"]

[[routes]]
kinds = ["ans"]
params = { fast = true }
lanes = ["tardis", "jina"]

[[routes]]
kinds = ["ans"]
lanes = ["tardis", "scraper", "jina", "firecrawl"]

[[routes]]
kinds = ["art"]
params = { fast = true }
lanes = ["tardis", "jina"]

[[routes]]
kinds = ["art"]
lanes = ["zhcli", "tardis", "jina", "firecrawl"]

[[routes]]
kinds = ["q"]
params = { fast = true }
lanes = ["jina"]

[[routes]]
kinds = ["q"]
lanes = ["zhcli", "jina", "firecrawl"]

[[routes]]
kinds = ["col"]
lanes = ["scraper"]

[[routes]]
kinds = ["ppl", "zv", "pin"]
lanes = ["zhcli"]
"""


def run_cli(args, env, timeout=60):
    e = dict(os.environ)
    e.update(env)
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=e,
    )


def lgc(env, *args):
    e = dict(os.environ)
    e.update(env)
    return subprocess.run(
        ["lgc", *args], capture_output=True, text=True, timeout=30, env=e
    )


def calls(lanes_dir):
    log = lanes_dir / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def set_rc(lanes_dir, name, rc):
    f = lanes_dir / f"rc.{name}"
    if rc in (None, 0):
        f.unlink(missing_ok=True)
    else:
        f.write_text(str(rc))


def decisions(env_):
    out = []
    for line in Path(env_["journal"]).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "decision":
            out.append(rec)
    return out


def envelope_of(proc):
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture
def zhifix(tmp_path):
    pdir = tmp_path / "packs" / "zhifix"
    lanes = pdir / "lanes"
    lanes.mkdir(parents=True)
    (pdir / "pack.toml").write_text(PACK_TOML)
    for name in CONNECTORS:
        c = lanes / name
        c.write_text(STUB)
        c.chmod(0o755)
    env = {
        "LGC_HOME": str(tmp_path / "lgc-home"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_ALLOW_PRIVATE": "1",
        "ZHIFIX_FC_KEY": "test-key",
    }
    return lanes, env, tmp_path


# ------------------------------------------------------- cascade matrix
# 分发层契约（link-get:181-195）：--fast/--comments 原样透传 + variant 变体键
# 按 kind 分支规则推导注入——测试同时携带两者，与真实 dispatch 一致。

MATRIX = [
    # (url path, params, expected connector-call order) — zhihu-get parity
    ("answer/101", [], ["tardis", "scraper", "jina", "firecrawl"]),
    ("answer/102", ["fast", "variant=+f"], ["tardis", "jina"]),
    ("answer/103", ["comments", "variant=+c"], ["scraper"]),
    ("p/104", [], ["zhcli art", "tardis", "jina", "firecrawl"]),
    ("p/105", ["fast", "variant=+f"], ["tardis", "jina"]),
    ("question/106", [], ["zhcli q", "jina", "firecrawl"]),
    ("question/107", ["fast", "variant=+f"], ["jina"]),
    ("column/c108", [], ["scraper"]),
    ("people/u109", [], ["zhcli ppl"]),
    ("zvideo/110", [], ["zhcli zv"]),
    ("pin/111", [], ["zhcli pin"]),
]


@pytest.mark.parametrize(("path", "params", "expect"), MATRIX)
def test_cascade_matrix(zhifix, path, params, expect):
    """All stubs notcovered (rc3) → every route-armed lane fires in declared
    order; unmatched kinds/params never spawn. Envelope rc 3 (notcovered)."""
    lanes, env, _ = zhifix
    for n in CONNECTORS:
        set_rc(lanes, n, 3)
    url = f"http://127.0.0.1:9/{path}"
    p = run_cli(["run", url, *params, "--json"], env)
    assert p.returncode == 3, (p.returncode, p.stderr)
    got = calls(lanes)
    assert len(got) == len(expect), got
    for line, exp in zip(got, expect, strict=True):
        assert line.startswith(exp), (line, exp)


def test_route_arm_journaled(zhifix):
    """+f run on ans: journal records the route decision with the armed lanes."""
    lanes, env, _ = zhifix
    for n in CONNECTORS:
        set_rc(lanes, n, 3)
    p = run_cli(
        [
            "run",
            "http://127.0.0.1:9/answer/201",
            "fast",
            "variant=+f",
            "--json",
        ],
        env,
    )
    dec = decisions(envelope_of(p))
    assert any(
        d.get("stage") == "route" and d.get("lanes") == ["tardis", "jina"] for d in dec
    ), dec


def test_kind_required_refused(zhifix):
    """URL matching no kind_by_url → kind_required refusal (rc2), no lanes."""
    lanes, env, _ = zhifix
    p = run_cli(["run", "http://127.0.0.1:9/org/unknown", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stderr)
    assert calls(lanes) == []
    dec = decisions(envelope_of(p))
    assert any(d.get("stage") == "identity" and d.get("kind_miss") for d in dec), dec


def test_route_miss_refused(zhifix):
    """kind matched but no route arm covers it → refused (rc2), no lanes."""
    lanes, env, _ = zhifix
    p = run_cli(["run", "http://127.0.0.1:9/misc/401", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stderr)
    assert calls(lanes) == []


def test_cascade_first_hit_wins(zhifix):
    """scraper rc0 mid-cascade → earlier lanes logged, later never fire."""
    lanes, env, tmp = zhifix
    for n in CONNECTORS:
        set_rc(lanes, n, 3)
    set_rc(lanes, "scraper", 0)
    out = tmp / "out"
    p = run_cli(["run", "http://127.0.0.1:9/answer/801", "-o", str(out), "--json"], env)
    assert p.returncode == 0, p.stderr
    assert [c.split()[0] for c in calls(lanes)] == ["tardis", "scraper"]
    env_ = envelope_of(p)
    assert env_["items"][0]["name"] == "scraper.md"
    assert (out / "scraper.md").exists()


def test_flag_params_comments(zhifix):
    """ans + comments → scraper arm; shim appends --comments to argv."""
    lanes, env, _ = zhifix
    for n in CONNECTORS:
        set_rc(lanes, n, 3)
    p = run_cli(
        [
            "run",
            "http://127.0.0.1:9/answer/901",
            "comments",
            "variant=+c",
            "--json",
        ],
        env,
    )
    assert p.returncode == 3
    got = calls(lanes)
    assert len(got) == 1, got
    assert got[0].startswith("scraper"), got
    assert "--comments" in got[0]


def test_needs_env_gate(zhifix):
    """firecrawl needs.env absent → admit-skipped, journaled as needs."""
    lanes, env, _ = zhifix
    for n in CONNECTORS:
        set_rc(lanes, n, 3)
    env = dict(env)
    env.pop("ZHIFIX_FC_KEY")
    p = run_cli(["run", "http://127.0.0.1:9/answer/701", "--json"], env)
    assert p.returncode == 3
    assert [c.split()[0] for c in calls(lanes)] == ["tardis", "scraper", "jina"]
    dec = decisions(envelope_of(p))
    assert any(
        d.get("gate") == "needs" and d.get("lane") == "firecrawl" for d in dec
    ), dec


# -------------------------------------------------- probe chain / store / neg


def test_probe_serves_base_key_on_variant(zhifix):
    """art+f: jina store="base" puts under the base key; a second +f run is
    served by the probe chain on the base key without firing any lane."""
    lanes, env, tmp = zhifix
    for n in CONNECTORS:
        set_rc(lanes, n, 3)
    set_rc(lanes, "jina", 0)
    url = "http://127.0.0.1:9/p/301"
    p1 = run_cli(["run", url, "fast", "variant=+f", "--json"], env)
    assert p1.returncode == 0, p1.stderr
    # store=base：全文产物入基键 art:301；变体键 art:301+f 不存
    g_base = lgc(env, "get", NS, "art:301", "--into", str(tmp / "gb"))
    assert g_base.returncode == 0, g_base.stderr
    g_var = lgc(env, "get", NS, "art:301+f", "--into", str(tmp / "gv"))
    assert g_var.returncode != 0
    n_calls = len(calls(lanes))

    p2 = run_cli(["run", url, "fast", "variant=+f", "--json"], env)
    assert p2.returncode == 0, p2.stderr
    assert "cache: hit" in p2.stderr
    assert len(calls(lanes)) == n_calls, "probe hit must not fire lanes"
    dec = decisions(envelope_of(p2))
    assert any(
        d.get("gate") == "cache"
        and d.get("key") == "art:301"
        and d.get("verdict") == "hit"
        for d in dec
    ), dec


def test_probe_neg_shortcircuit(zhifix):
    """Base-key tombstone serves a +f run via probe chain → permanent, no lanes."""
    lanes, env, _ = zhifix
    r = lgc(env, "neg", NS, "art:311", "--reason", "deleted")
    assert r.returncode == 0, r.stderr
    p = run_cli(
        ["run", "http://127.0.0.1:9/p/311", "fast", "variant=+f", "--json"],
        env,
    )
    assert p.returncode == 4, (p.returncode, p.stderr)
    assert calls(lanes) == []
    dec = decisions(envelope_of(p))
    assert any(
        d.get("gate") == "cache"
        and d.get("key") == "art:311"
        and d.get("verdict") == "neg"
        and d.get("reason") == "deleted"
        for d in dec
    ), dec


def test_permanent_double_neg_and_stop(zhifix):
    """Lane permanent (rc4) → STOP_CLASS break + negs BOTH variant key and
    base_key (zhihu deleted-evidence parity)."""
    lanes, env, tmp = zhifix
    set_rc(lanes, "tardis", 4)
    p = run_cli(
        ["run", "http://127.0.0.1:9/p/321", "fast", "variant=+f", "--json"],
        env,
    )
    assert p.returncode == 4, (p.returncode, p.stderr)
    assert [c.split()[0] for c in calls(lanes)] == ["tardis"]
    g_var = lgc(env, "get", NS, "art:321+f", "--into", str(tmp / "gv"))
    assert g_var.returncode == 4, g_var.stdout
    g_base = lgc(env, "get", NS, "art:321", "--into", str(tmp / "gb"))
    assert g_base.returncode == 4, g_base.stdout


# ------------------------------------------------------- lane accounting


def test_lane_accounting_scope(zhifix):
    """base_key shares lane accounting across variants: jina rc5 (transient)
    → lane_fail + per-key note on the BASE key, 3 fails trip the global
    breaker; tardis fail_note=false → nothing recorded even on transient."""
    lanes, env, _ = zhifix
    set_rc(lanes, "tardis", 5)  # transient — but fail_note=false
    set_rc(lanes, "jina", 5)
    p = run_cli(
        ["run", "http://127.0.0.1:9/p/501", "fast", "variant=+f", "--json"], env
    )
    assert p.returncode == 5, (p.returncode, p.stderr)
    # 1 次 fail（<3 不熔断）：lane-fail note 记 base_key——同键冷却，变体键无 note
    assert lgc(env, "lane", NS, "probe", "jina", "art:501").returncode == 1
    assert lgc(env, "lane", NS, "probe", "jina", "art:501+f").returncode == 0
    assert lgc(env, "lane", NS, "probe", "jina", "art:999").returncode == 0
    # tardis fail_note=false：transient 不上账——同键不冷，breaker 不动
    assert lgc(env, "lane", NS, "probe", "tardis", "art:501").returncode == 0
    for i in (502, 503):
        p = run_cli(
            ["run", f"http://127.0.0.1:9/p/{i}", "fast", "variant=+f", "--json"],
            env,
        )
        assert p.returncode == 5, (i, p.returncode, p.stderr)
    # jina 3 次 fail → 全局 breaker：任意键冷却
    assert lgc(env, "lane", NS, "probe", "jina", "art:999").returncode == 1
    # tardis 仍不冷
    assert lgc(env, "lane", NS, "probe", "tardis", "art:999").returncode == 0


def test_notcovered_perkey_note(zhifix):
    """notcovered (rc3) → per-key lane note on base_key, never a breaker."""
    lanes, env, _ = zhifix
    set_rc(lanes, "jina", 3)
    set_rc(lanes, "firecrawl", 3)
    set_rc(lanes, "zhcli", 3)
    p = run_cli(["run", "http://127.0.0.1:9/question/601", "--json"], env)
    assert p.returncode == 3
    # q base arm: zhcli → jina → firecrawl；zhcli/jina notcovered 记 note
    assert lgc(env, "lane", NS, "probe", "jina", "q:601").returncode == 1
    assert lgc(env, "lane", NS, "probe", "jina", "q:999").returncode == 0


def test_pack_ns_isolation(zhifix):
    """pack.ns is honored: artifacts land under zhihu-skill, not link-get."""
    lanes, env, tmp = zhifix
    set_rc(lanes, "tardis", 3)
    set_rc(lanes, "jina", 0)
    p = run_cli(
        ["run", "http://127.0.0.1:9/p/801", "fast", "variant=+f", "--json"], env
    )
    assert p.returncode == 0, p.stderr
    g = lgc(env, "get", NS, "art:801", "--into", str(tmp / "gz"))
    assert g.returncode == 0
    g2 = lgc(env, "get", "link-get", "art:801", "--into", str(tmp / "gl"))
    assert g2.returncode != 0, "link-get ns must not see zhihu-skill entries"


# ------------------------------------------------------- self-managed pack
# lgc_off=false（media/canvas wrap 形态）：connector 自管缓存全套——
# engine 对内容键零接触，探测/入库/记账全归 connector。

SELF_PACK_TOML = (
    PACK_TOML.replace('name = "zhifix"', 'name = "selffix"', 1)
    + "\n[monolith]\nlgc_off = false\n"
)


@pytest.fixture
def selffix(tmp_path):
    pdir = tmp_path / "packs" / "selffix"
    lanes = pdir / "lanes"
    lanes.mkdir(parents=True)
    (pdir / "pack.toml").write_text(SELF_PACK_TOML)
    for name in CONNECTORS:
        c = lanes / name
        c.write_text(STUB)
        c.chmod(0o755)
    env = {
        "LGC_HOME": str(tmp_path / "lgc-home"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_ALLOW_PRIVATE": "1",
        "ZHIFIX_FC_KEY": "test-key",
    }
    return lanes, env, tmp_path


def test_self_managed_no_probe_no_store(selffix):
    """self-managed：admit 记 verdict=self-managed、无 cache key 探测行；
    lane 照常跑成，但 engine 不落 entry（put 全归 connector——stub 不写）。"""
    lanes, env, tmp = selffix
    for n in ("zhcli", "tardis"):
        set_rc(lanes, n, 3)
    set_rc(lanes, "jina", 0)
    p = run_cli(["run", "http://127.0.0.1:9/p/601", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    dec = decisions(envelope_of(p))
    caches = [d for d in dec if d.get("stage") == "admit" and d.get("gate") == "cache"]
    assert [d.get("verdict") for d in caches] == ["self-managed"], caches
    # 管线没短路——art 臂前两条 notcovered 后 jina 真跑成
    assert [c.split()[0] for c in calls(lanes)] == ["zhcli", "tardis", "jina"]
    # engine 未入库：内容键裸 miss rc1（无 claim → 非 rc6）
    g = lgc(env, "get", NS, "art:601", "--into", str(tmp / "g"))
    assert g.returncode == 1, (g.returncode, g.stdout, g.stderr)


def test_self_managed_no_error_accounting(selffix):
    """self-managed lane 失败不上账：transient 后 lane probe 全绿——
    record_error/lane note/breaker 全是 connector 自己的账。"""
    lanes, env, _ = selffix
    for n in CONNECTORS:
        set_rc(lanes, n, 5)
    p = run_cli(["run", "http://127.0.0.1:9/question/611", "--json"], env)
    assert p.returncode == 5, (p.returncode, p.stderr)
    # q 臂 zhcli→jina→firecrawl 全 transient——一个 keyed/keyless note 都不该有
    for lane_name in ("zhcli", "jina", "firecrawl"):
        lp = lgc(env, "lane", NS, "probe", lane_name, "q:611")
        assert lp.returncode == 0, (lane_name, lp.returncode, lp.stdout)
        lp2 = lgc(env, "lane", NS, "probe", lane_name)
        assert lp2.returncode == 0, (lane_name, lp2.returncode, lp2.stdout)


# ------------------------------------------------------- satisfies probe
# [identity].satisfies：请求 params → --satisfies 断言束（media-get:774 同构）。
# entry params 为产物侧语义：height/req_cap/langs_obtained/subs_known。

SAT_PACK_TOML = """
[pack]
name = "satfix"
abi = 1
ns = "zhihu-skill"
kinds = ["art"]

[match]
hosts = ["127.0.0.1"]
schemes = ["http"]

[identity]
keyexpr = "art:{url}"
satisfies = { max_height = { param = "max_height", default = 1080, type = "int" }, langs = { param = "langs", default = "en", type = "csv" } }

[[lanes]]
name = "stub"
exec = "monolith"
connector = "lanes/stub"
needs = { tools = ["bash"] }
[lanes.monolith]
argv = ["{artifact_dir}", "{url}"]
"""

SAT_NS = "zhihu-skill"  # lgc ns 白名单（canvas-skill/link-get/zhihu-skill）


@pytest.fixture
def satfix(tmp_path):
    pdir = tmp_path / "packs" / "satfix"
    lanes = pdir / "lanes"
    lanes.mkdir(parents=True)
    (pdir / "pack.toml").write_text(SAT_PACK_TOML)
    c = lanes / "stub"
    c.write_text(STUB)
    c.chmod(0o755)
    env = {
        "LGC_HOME": str(tmp_path / "lgc-home"),
        "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
        "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
        "FETCH_ENGINE_ALLOW_PRIVATE": "1",
    }
    return lanes, env, tmp_path


def seed_bundle(env, tmp, key):
    """手工 put 一束带产物侧 params 的 entry（media-get 入库形态）：
    height=req_cap=1080、拿到 en 轨、上游有 en/zh-CN 两个字幕。"""
    src = tmp / "seed-src"
    src.mkdir(exist_ok=True)
    (src / "v.mp4").write_text("seed video\n")
    p = lgc(
        env,
        "put",
        SAT_NS,
        key,
        "--from",
        str(src),
        "--params",
        json.dumps(
            {
                "height": 1080,
                "req_cap": 1080,
                "langs_obtained": ["en"],
                "subs_known": ["en", "zh-CN"],
            }
        ),
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)


def test_satisfies_hit_serves_defaults(satfix):
    """无参请求 → 默认值注入断言（max_height=1080/langs=en）→ 命中种子束，
    probe served、lane 零调用、journal 记 satisfies=2。"""
    lanes, env, tmp = satfix
    url = "http://127.0.0.1:9/p/1"
    seed_bundle(env, tmp, f"art:{url}")
    p = run_cli(["run", url, "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    assert "cache: hit" in p.stderr
    assert calls(lanes) == []
    dec = decisions(envelope_of(p))
    assert any(
        d.get("gate") == "cache"
        and d.get("verdict") == "hit"
        and d.get("satisfies") == 2
        for d in dec
    ), dec


def test_satisfies_unknown_lang_served(satfix):
    """langs=fr：fr 不在 langs_obtained 但也不在 subs_known（上游无此字幕）
    → 视为可满足 → hit、lane 不跑。"""
    lanes, env, tmp = satfix
    url = "http://127.0.0.1:9/p/2"
    seed_bundle(env, tmp, f"art:{url}")
    p = run_cli(["run", url, "langs=fr", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    assert calls(lanes) == []


def test_satisfies_miss_below_height(satfix):
    """max_height=720 < entry.height 1080 → 断言失败 miss → lane 真跑。"""
    lanes, env, tmp = satfix
    url = "http://127.0.0.1:9/p/3"
    seed_bundle(env, tmp, f"art:{url}")
    p = run_cli(["run", url, "max_height=720", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    assert [c.split()[0] for c in calls(lanes)] == ["stub"]
    dec = decisions(envelope_of(p))
    assert any(d.get("gate") == "cache" and d.get("verdict") == "miss" for d in dec), (
        dec
    )


def test_satisfies_miss_known_sub_not_obtained(satfix):
    """langs=zh-CN：zh-CN 在 subs_known（上游确有此轨）但束内未取 → miss。"""
    lanes, env, tmp = satfix
    url = "http://127.0.0.1:9/p/4"
    seed_bundle(env, tmp, f"art:{url}")
    p = run_cli(["run", url, "langs=zh-CN", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    assert [c.split()[0] for c in calls(lanes)] == ["stub"]
