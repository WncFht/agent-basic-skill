"""test_pack_zhihu.py — zhihu 拆解包 arm 真值表 parity。

真值表：zhihu-get:435-515（kind × comments/fast → 有序 lane 臂 + 变体缓存键）。
全部离线：真 pack.toml 复制进 tmp packs/，每条 [[lanes]] 的 exec 重指到
生成的 stub lane（读 stdin req → STUB_CALLS 记录 {lane,key,base_key,kind,
params} → 写 artifact → result；modes 指定时改吐对应 class 的 error）。
needs 门由 fakebin（zhihu-scraper/curl）+ FIRECRAWL_API_KEY 满足；LGC_BIN
指向仓内 lgc，LGC_HOME/HOME 全 tmp 化——cred 文件按 missing 处理，不读
真凭证。

分发合同（link-get:181-197）：--comments/--fast 由分发层翻成 --param
comments / --param fast，并按 URL 形态补 variant=+c/+f。engine 自身不从
旗标派生 variant——调用层必须伴随 variant param，否则 keyexpr 拿不到
+f/+c 后缀。本测试按同一合同传参。
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
LGC = ROOT / "scripts" / "lgc"
PACK_TOML = ROOT / "packs" / "zhihu" / "pack.toml"

ZH = "https://www.zhihu.com"
ZL = "https://zhuanlan.zhihu.com"
NS = "zhihu-skill"  # pack.toml [pack].ns —— lgc 断言必须同 ns

# lane 名 → 真 pack.toml 中的相对 exec（重指时按名映射）
LANE_FILES = {
    "tardis": "lanes/tardis_lane.py",
    "jina": "lanes/jina_lane.py",
    "firecrawl": "lanes/firecrawl_lane.py",
    "scraper": "lanes/scraper_lane.py",
    "zhcli": "lanes/zhcli_lane.py",
}
ALL_LANES = list(LANE_FILES)

# stub lane —— lane ABI v1 最小实现：stdin 一行 req → calls.jsonl 追加一条
# 记录；CLS 非空吐 error 终态，否则写 <lane>.md 进 artifact_dir 吐 result。
# 特殊 CLS："__skip__" = rc10 无终态静默跳过；"__tree__" = 产子目录树包
# （answers/x.md + articles/x.md 撞 basename，专验 put --from 保 relpath）；
# "__pmeta__" = result 携带产物侧 params（height/req_cap/files_meta），
# 专验 collect 把 lane 上报语义并入 entry params。
STUB_TMPL = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

LANE = __LANE__
CLS = __CLS__
CALLS_DEFAULT = __CALLS__

req = json.loads(sys.stdin.readline() or "{}")
ident = req.get("identity") or {}
ctx = req.get("ctx") or {}
calls = os.environ.get("STUB_CALLS") or CALLS_DEFAULT
with open(calls, "a", encoding="utf-8") as fh:
    fh.write(
        json.dumps(
            {
                "lane": LANE,
                "key": ident.get("key"),
                "base_key": ident.get("base_key"),
                "kind": ident.get("kind"),
                "params": ident.get("params"),
            },
            ensure_ascii=False,
        )
        + "\\n"
    )
adir = Path(ctx.get("artifact_dir") or ".")
adir.mkdir(parents=True, exist_ok=True)
if CLS == "__skip__":
    sys.exit(10)
if CLS == "__tree__":
    items = []
    for rel in ("answers/x.md", "articles/x.md"):
        fp = adir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("stub tree " + rel + "\\n", encoding="utf-8")
        items.append({"path": str(fp), "name": rel})
    print(json.dumps({"type": "result", "items": items}))
    sys.exit(0)
if CLS == "__pmeta__":
    items = []
    for rel in (LANE + ".md", "v2.mp4"):
        fp = adir / rel
        fp.write_text("stub pmeta " + rel + "\\n", encoding="utf-8")
        items.append({"path": str(fp), "name": rel})
    print(
        json.dumps(
            {
                "type": "result",
                "items": items,
                "params": {
                    "height": 720,
                    "req_cap": 1080,
                    "files_meta": {"v2.mp4": {"kind": "screen", "viewNum": 2}},
                },
            }
        )
    )
    sys.exit(0)
if CLS:
    print(json.dumps({"type": "error", "class": CLS, "evidence": "stub " + CLS}))
    sys.exit(0)
art = adir / (LANE + ".md")
art.write_text("stub artifact " + LANE + "\\n", encoding="utf-8")
print(
    json.dumps({"type": "result", "items": [{"path": str(art), "name": art.name}]})
)
"""


def make_zhihu_pack(tmp_path, modes=None):
    """真 pack.toml → tmp packs/zhihu/；每条 lane exec 改指 stub。

    modes: {lane: "transient"|"permanent"|...} —— 缺席的 lane 吐 result。
    needs 表追加 env_optional=["STUB_CALLS"]，让 calls 路径穿 lane_env 白名单
    进 stub（真 needs 门其余项原样保留）。
    """
    modes = modes or {}
    pdir = tmp_path / "packs" / "zhihu"
    pdir.mkdir(parents=True)
    stubdir = tmp_path / "stubs"
    stubdir.mkdir(exist_ok=True)
    calls = tmp_path / "calls.jsonl"
    text = PACK_TOML.read_text(encoding="utf-8")
    for lane, real_exec in LANE_FILES.items():
        stub = stubdir / f"stub_{lane}.py"
        stub.write_text(
            STUB_TMPL.replace("__LANE__", repr(lane))
            .replace("__CLS__", repr(modes.get(lane) or ""))
            .replace("__CALLS__", repr(str(calls))),
            encoding="utf-8",
        )
        stub.chmod(0o755)
        needle = f'exec = "{real_exec}"'
        assert needle in text, f"pack.toml drifted: {needle}"
        text = text.replace(needle, f'exec = "{stub}"')
    text, n = re.subn(r"needs = \{([^}]*)\}", _inject_stub_env, text)
    assert n == len(LANE_FILES), f"needs rewrite hit {n}, want {len(LANE_FILES)}"
    (pdir / "pack.toml").write_text(text, encoding="utf-8")
    return tmp_path / "packs", calls


def _inject_stub_env(m):
    """needs 内联表注入 STUB_CALLS 透传；已有 env_optional 则并入其列表。"""
    inner = m.group(1)
    if '"STUB_CALLS"' in inner:
        return m.group(0)
    mm = re.search(r"env_optional\s*=\s*\[([^\]]*)\]", inner)
    if mm:
        items = mm.group(1)
        sep = ", " if items.strip() else ""
        return (
            "needs = {"
            + inner[: mm.start(1)]
            + items
            + sep
            + '"STUB_CALLS"'
            + inner[mm.end(1) :].rstrip()
            + " }"
        )
    return "needs = {" + inner.rstrip() + ', env_optional = ["STUB_CALLS"]}'


def zh_fixture(tmp_path, modes=None, patch=None):
    """pack + stub + fakebin + env —— 一次 engine run 所需全部。

    patch: 可选 callable，make_zhihu_pack 落盘后回调 pack.toml 路径——
    测试用来加声明字段（store_keep/store_atomic 等）。"""
    packs, calls = make_zhihu_pack(tmp_path, modes)
    if patch:
        patch(packs / "zhihu" / "pack.toml")
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    # needs.tools 门：lane exec 已是 stub，这些工具只被 which() 查不被真跑
    for tool in ("zhihu-scraper", "curl"):
        t = bindir / tool
        t.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        t.chmod(0o755)
    (tmp_path / "home").mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "LGC_HOME": str(tmp_path / "lgc-home"),
            "LGC_BIN": str(LGC),
            "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
            "FETCH_ENGINE_PACKS": str(packs),
            # zhihu 域名是公网字面 host，SSRF 闸天然放行，无需私网开关
            "FETCH_ENGINE_ALLOW_PRIVATE": "",
            "HOME": str(tmp_path / "home"),
            "FIRECRAWL_API_KEY": "test-key",  # needs.env 门
            "STUB_CALLS": str(calls),
            "PATH": str(bindir) + os.pathsep + env["PATH"],
        }
    )
    env.pop("LGC_REFRESH", None)
    return packs, calls, env


def run_engine(args, env, timeout=120):
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def lgc(args, env, timeout=30):
    return subprocess.run(
        [str(LGC), *args], capture_output=True, text=True, timeout=timeout, env=env
    )


def _envelope(p):
    return json.loads(p.stdout.strip().splitlines()[-1])


def _journal_decisions(envelope):
    out = []
    for line in Path(envelope["journal"]).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "decision":
            out.append(rec)
    return out


def _exec_lanes(decs):
    """journal 'exec' spawn 决策（带 argv 的那条）的 lane 序。"""
    return [d["lane"] for d in decs if d.get("stage") == "exec" and "argv" in d]


def _read_calls(calls):
    if not calls.exists():
        return []
    return [json.loads(line) for line in calls.read_text().splitlines() if line.strip()]


def _want_params(params):
    """--param 列表 → engine params 形态（裸旗标 → True，k=v → str）。"""
    out = {}
    for kv in params:
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
        else:
            out[kv] = True
    return out


# ---------------------------------------------------------------- arms
# 真值表（zhihu-get:435-515 逐臂复刻）：
#   url, params, lanes, kind, key, base_key, probe_keys
# probe_keys：+f 臂先探 base_key 再探变体键（probe_base_variants=["+f"]，对应
# connector probe_and_serve ZBASE → ZK）；+c/无变体臂只探内容键本身。

ARMS = [
    (
        f"{ZH}/question/111/answer/456",
        ["comments", "variant=+c"],
        ["scraper"],
        "ans",
        "ans:456+c",
        "ans:456",
        ["ans:456+c"],
    ),
    (
        f"{ZH}/answer/456",
        ["fast", "variant=+f"],
        ["tardis", "jina"],
        "ans",
        "ans:456+f",
        "ans:456",
        ["ans:456", "ans:456+f"],
    ),
    (
        f"{ZH}/answer/456",
        [],
        ["tardis", "scraper", "jina", "firecrawl"],
        "ans",
        "ans:456",
        "ans:456",
        ["ans:456"],
    ),
    # connector：answer 支 comments 先于 fast 判定 —— 双旗标仍走 +c 臂
    (
        f"{ZH}/answer/456",
        ["comments", "fast", "variant=+c"],
        ["scraper"],
        "ans",
        "ans:456+c",
        "ans:456",
        ["ans:456+c"],
    ),
    (
        f"{ZL}/p/12345",
        ["fast", "variant=+f"],
        ["tardis", "jina"],
        "art",
        "art:12345+f",
        "art:12345",
        ["art:12345", "art:12345+f"],
    ),
    (
        f"{ZH}/p/12345",
        [],
        ["zhcli", "tardis", "jina", "firecrawl"],
        "art",
        "art:12345",
        "art:12345",
        ["art:12345"],
    ),
    # /p/ 支 --comments 被忽略：无 +c 变体，落 default 臂
    (
        f"{ZH}/p/12345",
        ["comments"],
        ["zhcli", "tardis", "jina", "firecrawl"],
        "art",
        "art:12345",
        "art:12345",
        ["art:12345"],
    ),
    (
        f"{ZH}/question/789",
        ["fast", "variant=+f"],
        ["jina"],
        "q",
        "q:789+f",
        "q:789",
        ["q:789", "q:789+f"],
    ),
    (
        f"{ZH}/question/789",
        [],
        ["zhcli", "jina", "firecrawl"],
        "q",
        "q:789",
        "q:789",
        ["q:789"],
    ),
    # question 支 --comments 同样被忽略
    (
        f"{ZH}/question/789",
        ["comments"],
        ["zhcli", "jina", "firecrawl"],
        "q",
        "q:789",
        "q:789",
        ["q:789"],
    ),
    (
        f"{ZH}/column/mycol",
        [],
        ["scraper"],
        "col",
        "col:mycol",
        "col:mycol",
        ["col:mycol"],
    ),
    (
        f"{ZH}/column/mycol",
        ["comments", "variant=+c"],
        ["scraper"],
        "col",
        "col:mycol+c",
        "col:mycol",
        ["col:mycol+c"],
    ),
    # column 支 --fast 被忽略：无 +f 变体
    (
        f"{ZH}/column/mycol",
        ["fast"],
        ["scraper"],
        "col",
        "col:mycol",
        "col:mycol",
        ["col:mycol"],
    ),
    # zhuanlan 专栏短链 → 同一 col arm
    (
        f"{ZL}/mycol",
        [],
        ["scraper"],
        "col",
        "col:mycol",
        "col:mycol",
        ["col:mycol"],
    ),
    (
        f"{ZH}/people/someone",
        [],
        ["zhcli"],
        "ppl",
        "ppl:someone",
        "ppl:someone",
        ["ppl:someone"],
    ),
    (
        f"{ZH}/zvideo/321",
        [],
        ["zhcli"],
        "zv",
        "zv:321",
        "zv:321",
        ["zv:321"],
    ),
    (
        f"{ZH}/pin/654",
        [],
        ["zhcli"],
        "pin",
        "pin:654",
        "pin:654",
        ["pin:654"],
    ),
]

ARM_IDS = [
    "ans+comments",
    "ans+fast",
    "ans-default",
    "ans+comments+fast",
    "art+fast",
    "art-default",
    "art+comments-ignored",
    "q+fast",
    "q-default",
    "q+comments-ignored",
    "col-default",
    "col+comments",
    "col+fast-ignored",
    "col-zhuanlan",
    "ppl",
    "zv",
    "pin",
]


@pytest.mark.parametrize(
    ("url", "params", "lanes", "kind", "key", "base", "probes"),
    ARMS,
    ids=ARM_IDS,
)
def test_arm_truth_table(tmp_path, url, params, lanes, kind, key, base, probes):
    """全臂 lane 以 transient 失败 → engine 按序走完整臂；断言选臂、执行
    顺序、identity.key/base_key、cache 探测链与真值表逐项一致。"""
    _, calls, env = zh_fixture(tmp_path, dict.fromkeys(ALL_LANES, "transient"))
    args = ["run", url]
    for kv in params:
        args += ["--param", kv]
    args += ["--json"]
    p = run_engine(args, env)
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "transient"

    decs = _journal_decisions(env_)
    ident = next(d for d in decs if d.get("stage") == "identity")
    assert ident["key"] == key
    assert ident["kind"] == kind

    routes = [d["lanes"] for d in decs if d.get("stage") == "route" and "lanes" in d]
    assert routes == [lanes]

    gates = [
        d
        for d in decs
        if d.get("stage") == "admit" and d.get("gate") == "cache" and "key" in d
    ]
    assert [d["key"] for d in gates] == probes
    assert [d["verdict"] for d in gates] == ["miss"] * len(probes)

    assert _exec_lanes(decs) == lanes
    got = _read_calls(calls)
    assert [c["lane"] for c in got] == lanes
    want = _want_params(params)
    for c in got:
        assert c["key"] == key
        assert c["base_key"] == base
        assert c["kind"] == kind
        for k, v in want.items():
            assert c["params"].get(k) == v


# ---------------------------------------------------------------- gates


@pytest.mark.parametrize(
    "url",
    [f"{ZH}/collection/123", f"{ZH}/org/x"],
    ids=["collection", "org"],
)
def test_kind_required_refused(tmp_path, url):
    """kind 判不出 → kind_required → rc2 refused；identity 记 kind_miss，
    无 lane 被执行。（people/ 已归 ppl 形状——connector */people/* 臂平价，
    id 解不出也照跑 zhcli，见 test_idless_shape_runs_lanes）"""
    _, calls, env = zh_fixture(tmp_path)
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "no kind" in p.stderr
    env_ = _envelope(p)
    assert env_["class"] == "refused"
    decs = _journal_decisions(env_)
    ident = next(d for d in decs if d.get("stage") == "identity")
    assert ident.get("kind_miss") is True
    assert _exec_lanes(decs) == []
    assert _read_calls(calls) == []


def test_route_gate_nonzhihu(tmp_path):
    """非 zhihu host / 非 URL 目标：route 闸拒，永远到不了本 pack。"""
    _, calls, env = zh_fixture(tmp_path)
    for target in ("https://example.com/x", "not-a-url"):
        p = run_engine(["run", target, "--json"], env)
        assert p.returncode == 3, (target, p.returncode, p.stdout, p.stderr)
        assert "no pack covers" in p.stderr
    assert _read_calls(calls) == []


def test_schemeless_zhihu_routes(tmp_path):
    """裸 zhihu.com/x（无 scheme）：canon 归一 https 后 zhihu pack 命中——
    connector 时代 curl 自补 scheme，engine 不得在 admit 前误拒。"""
    _, calls, env = zh_fixture(tmp_path)
    p = run_engine(["run", "zhihu.com/question/1/answer/2", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert _read_calls(calls)  # 确有 lane 执行（fixture stub）


# ---------------------------------------------------------------- store / neg / fail_note


def test_store_base_variant_key(tmp_path):
    """store='base'：jina 成功 → 产物入 base_key；variant key 保持为空。

    spec 写 "lgc cat of BASE key"——lgc cat 只服务 inline value/__value__，
    文件型 entry 需用 `lgc get`（rc0 + materialize）探存在性。
    """
    _, calls, env = zh_fixture(tmp_path, {"tardis": "transient"})
    url = f"{ZH}/p/2468"
    args = ["run", url, "--param", "fast", "--param", "variant=+f", "--json"]
    p = run_engine(args, env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert [c["lane"] for c in _read_calls(calls)] == ["tardis", "jina"]

    g = lgc(["get", NS, "art:2468", "--into", str(tmp_path / "m1"), "--json"], env)
    assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)
    assert list((tmp_path / "m1").rglob("*.md")), "base key must materialize"
    g2 = lgc(["get", NS, "art:2468+f", "--into", str(tmp_path / "m2")], env)
    assert g2.returncode != 0  # variant key 不得被 +f 快取回填

    # 基键被 +f 填好后，同一 +f 请求复跑应首探即中、零 lane 执行
    p2 = run_engine(args, env)
    assert p2.returncode == 0, p2.stderr
    assert "cache: hit" in p2.stderr
    decs2 = _journal_decisions(_envelope(p2))
    assert _exec_lanes(decs2) == []


def test_permanent_negs_base_and_variant(tmp_path):
    """permanent 终态 → 内容键与基键同碑（+f 是同一内容的视图）。"""
    _, calls, env = zh_fixture(tmp_path, {"tardis": "permanent"})
    url = f"{ZH}/p/357"
    p = run_engine(
        ["run", url, "--param", "fast", "--param", "variant=+f", "--json"], env
    )
    assert p.returncode == 4, (p.returncode, p.stdout, p.stderr)
    # permanent 是 stop class —— jina 不得执行
    assert [c["lane"] for c in _read_calls(calls)] == ["tardis"]
    for key in ("art:357", "art:357+f"):
        g = lgc(["get", NS, key, "--into", str(tmp_path / "neg")], env)
        assert g.returncode == 4, (key, g.returncode, g.stdout, g.stderr)


def test_lane_fail_accounting(tmp_path):
    """transient 上账（pack.toml:26-27 注释现行语义）：tardis 无 fail_note
    豁免——lane_fail+lane_note 照常写，下一 lane 仍按序执行；lane note 落在
    base_key（art:975）上，单次 fail 不触发 breaker。"""
    _, calls, env = zh_fixture(tmp_path, {"tardis": "transient", "jina": "transient"})
    url = f"{ZH}/p/975"
    p = run_engine(
        ["run", url, "--param", "fast", "--param", "variant=+f", "--json"], env
    )
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    assert [c["lane"] for c in _read_calls(calls)] == ["tardis", "jina"]
    # 两条 lane 的 lane-fail note 都记在 base_key 上 → keyed probe 冷却
    for lane in ("tardis", "jina"):
        g = lgc(["lane", NS, "probe", lane, "art:975"], env)
        assert g.returncode == 1, (lane, g.returncode, g.stdout, g.stderr)
    # 但单次 fail 不够 BREAKER_FAILS —— keyless probe 不放行 breaker
    g = lgc(["lane", NS, "probe", "tardis"], env)
    assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)


# ---------------------------------------------------------------- F9 形状臂


@pytest.mark.parametrize(
    ("url", "kind", "lanes"),
    [
        (f"{ZH}/question/abc", "q", ["zhcli", "jina", "firecrawl"]),
        (f"{ZL}/p/abc", "art", ["zhcli", "tardis", "jina", "firecrawl"]),
        (f"{ZH}/people/", "ppl", ["zhcli"]),
        (f"{ZL}/", "col", ["scraper"]),
    ],
    ids=["q-no-id", "art-no-id", "ppl-no-id", "col-zhuanlan-root"],
)
def test_idless_shape_runs_lanes(tmp_path, url, kind, lanes):
    """kind_by_url 只判形状（connector case 臂平价）：id 解不出照样走臂，
    keyexpr capture_miss 退化为 {kind}:{raw} per-URL 键——
    等价 connector 的 zkey-empty→uncached lane run，但多一层 per-URL 缓存。"""
    _, calls, env = zh_fixture(tmp_path, dict.fromkeys(ALL_LANES, "transient"))
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 5, (url, p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _journal_decisions(env_)
    ident = next(d for d in decs if d.get("stage") == "identity")
    assert ident["kind"] == kind, (url, ident)
    assert ident["key"] == f"{kind}:{url}", (url, ident)
    assert _exec_lanes(decs) == lanes
    got = _read_calls(calls)
    assert [c["lane"] for c in got] == lanes
    for c in got:
        assert c["key"] == f"{kind}:{url}"
        assert c["base_key"] == f"{kind}:{url}"
        assert c["kind"] == kind


def test_all_lanes_skip_dep_absent(tmp_path):
    """每条 armed lane 都 rc10 静默跳过（无终态行）→ envelope rc5 dep_absent：
    connector lanes_run 全 skip 收 rc5 平价；dep_absent 不记账、不成 last_error。"""
    _, calls, env = zh_fixture(tmp_path, dict.fromkeys(ALL_LANES, "__skip__"))
    url = f"{ZH}/p/777"
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "dep_absent"
    # stub 在 skip 前已记调用——证明四车道真被 spawn 过而非 admit 闸掉
    got = _read_calls(calls)
    assert [c["lane"] for c in got] == ["zhcli", "tardis", "jina", "firecrawl"]


def test_auth_expired_cascades_and_no_content_neg(tmp_path):
    """auth_expired 不是 stop class（connector lanes_run 只认 rc4 短路）：
    zhcli cred 死后匿名车道照常跑；内容键不落 neg（cred 死是车道事，
    落内容墓碑会毒死 connector 共享 store）；记账只写 cred-scoped lane note。"""
    _, calls, env = zh_fixture(
        tmp_path,
        {"zhcli": "auth_expired", "jina": "transient", "firecrawl": "transient"},
    )
    url = f"{ZH}/question/42"
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "transient"  # 终态取末条 lane 错误，非 auth_expired
    got = _read_calls(calls)
    assert [c["lane"] for c in got] == ["zhcli", "jina", "firecrawl"]
    # 内容键无墓碑：plain miss rc1（若有 auth-expired neg 会是 rc5/6）
    g = lgc(["get", NS, "q:42", "--into", str(tmp_path / "m")], env)
    assert g.returncode == 1, (g.returncode, g.stdout, g.stderr)
    # zhcli 车道账：auth-expired note 让同键 keyed probe 冷却（cred 域内）
    lp = lgc(["lane", NS, "probe", "zhcli", "q:42"], env)
    assert lp.returncode == 1, (lp.returncode, lp.stdout, lp.stderr)


def test_tree_bundle_store_and_deliver(tmp_path):
    """树包 lane（zhcli/scraper 真形）：put --from staging 保 relpath 入库，
    get 还原同树、-o 交付同树——旧 --files 拍扁会让 answers/ 与 articles/
    的同名 x.md 互撞丢件。"""
    _, calls, env = zh_fixture(tmp_path, {"zhcli": "__tree__"})
    url = f"{ZH}/p/88"
    outdir = tmp_path / "deliver"
    p = run_engine(["run", url, "-o", str(outdir), "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert [c["lane"] for c in _read_calls(calls)] == ["zhcli"]
    env_ = _envelope(p)
    assert sorted(i["name"] for i in env_["items"]) == [
        "answers/x.md",
        "articles/x.md",
    ]
    # -o 交付树完整（同名件分目录落）
    assert (outdir / "answers" / "x.md").read_text().strip() == (
        "stub tree answers/x.md"
    )
    assert (outdir / "articles" / "x.md").read_text().strip() == (
        "stub tree articles/x.md"
    )
    # 入库树完整：get --into 还原 relpath
    gdir = tmp_path / "m"
    g = lgc(["get", NS, "art:88", "--into", str(gdir)], env)
    assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)
    assert (gdir / "answers" / "x.md").read_text().strip() == ("stub tree answers/x.md")
    assert (gdir / "articles" / "x.md").read_text().strip() == (
        "stub tree articles/x.md"
    )


def test_result_params_and_store_flags(tmp_path):
    """lane result.params 并入 entry params（产物侧语义覆盖请求侧）：
    zhcli __pmeta__ 上报 height/files_meta + lane 声明 store_keep/store_atomic
    → get --json 见 params.height=720、files[].kind=screen/viewNum=2；
    keep=1 删掉一个 blob 仍 partial-hit（rc0）；journal store 决策带双旗标。"""

    def add_flags(pt):
        text = pt.read_text(encoding="utf-8")
        needle = 'name = "zhcli"'
        assert text.count(needle) == 1
        pt.write_text(
            text.replace(
                needle, needle + "\nstore_keep = true\nstore_atomic = true", 1
            ),
            encoding="utf-8",
        )

    _, calls, env = zh_fixture(tmp_path, {"zhcli": "__pmeta__"}, patch=add_flags)
    url = f"{ZH}/p/432"
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert [c["lane"] for c in _read_calls(calls)] == ["zhcli"]
    decs = _journal_decisions(_envelope(p))
    store = next(d for d in decs if d.get("gate") == "store")
    assert store["keep"] is True, store
    assert store["atomic"] is True, store

    # entry params：lane 上报的产物侧字段经 put --params 落库
    g = lgc(["get", NS, "art:432", "--json"], env)
    assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)
    payload = json.loads(g.stdout.strip().splitlines()[-1])
    assert payload["params"]["height"] == 720
    assert payload["params"]["req_cap"] == 1080
    f0 = next(f for f in payload["files"] if f["name"] == "v2.mp4")
    assert f0["kind"] == "screen", f0
    assert f0["viewNum"] == 2, f0

    # keep=1：删掉一个 blob 后仍 partial-hit（missing < files → REMISS 豁免）
    victim = next(p for p in payload["paths"] if p.endswith("v2.mp4"))
    Path(victim).unlink()
    g2 = lgc(["get", NS, "art:432", "--into", str(tmp_path / "m2"), "--json"], env)
    assert g2.returncode == 0, (g2.returncode, g2.stdout, g2.stderr)
