"""test_pack_arxiv.py — arxiv pack e2e（全离线）。

真 pack.toml 复制进 tmp packs/，lanes/ 软链；arxiv_tex 原生 lane 三段解析
到 fakebin 里的 stub arxiv-tex（PATH + ARXIV_TEX 双保险）。stub 复刻
wrapper 契约面：

- 剥自有旗标（--refresh/--no-cache/--cache-ttl/--force-download）后取裸 id；
- stamp_put：lgc put link-get "arxiv:<id>" --value（显式 vN → SKIP，同 wrapper:76）；
- 失败面由 fail.mode 文件驱动——arxiv-to-prompt 的真实失败形态几乎全是
  rc0+空 stdout，只有 argparse 互斥 rc2、wrapper uvx 缺席 rc5。

断言面：bare_resolve 重写（journal）→ arxiv pack 路由 → 产物收集 →
arxivtex:<id> 内容键；二次 run cache hit；wrapper 戳键 arxiv:<id> 与内容键
arxivtex:<id> 共存不互毁（lgc 探针实查）；失败分类 rc；satisfies{mode}
互逐语义（full 束不供 abstract，反之亦然）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
LGC = ROOT / "scripts" / "lgc"
PACK_TOML = ROOT / "packs" / "arxiv" / "pack.toml"
NS = "link-get"

# stub arxiv-tex —— wrapper 契约面的最小复刻（语义注释见文件头）
STUB = """#!/bin/bash
set -u
here="$(cd "$(dirname "$0")" && pwd)"
echo "arxiv-tex $*" >> "$here/calls.log"
ARGS=(); ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --refresh|--no-cache|--force-download) ARGS+=("$1") ;;
    --cache-ttl) ARGS+=("$1" "$2"); shift ;;
    --section) ARGS+=("$1" "$2"); shift ;;
    *) ARGS+=("$1")
       case "$1" in
         -*|*://*) ;;
         *) [ -z "$ID" ] && ID="$1" ;;
       esac ;;
  esac
  shift
done
# stamp_put（wrapper:26-29 同构；显式 vN → SKIP=1 直通，wrapper:76）
case "$ID" in
  ""|*v[0-9]*) ;;
  *) "${LGC_BIN:-lgc}" put link-get "arxiv:$ID" --value "v3 1700000000" >/dev/null 2>&1 || true ;;
esac
mode=""
[ -f "$here/fail.mode" ] && mode="$(tr -d '[:space:]' < "$here/fail.mode")"
case "$mode" in
  notfound) echo "TeX source files not available for $ID" >&2; exit 0 ;;
  network) echo "Error checking source availability: boom" >&2; exit 0 ;;
  empty) exit 0 ;;
  section-miss) echo "Warning: Section 'Intro' not found" >&2; exit 0 ;;
  usage) echo "usage: arxiv-to-prompt [-h] arxiv_id" >&2; exit 2 ;;
  uvx-miss) echo "arxiv-tex: uvx 未装" >&2; exit 5 ;;
esac
printf 'STUB-TEX id=%s args=%s\\n' "$ID" "${ARGS[*]}"
exit 0
"""


@pytest.fixture
def afix(tmp_path):
    """pack + stub connector + fakebin + 隔离 env。"""
    pdir = tmp_path / "packs" / "arxiv"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(PACK_TOML.read_text(encoding="utf-8"))
    os.symlink(ROOT / "packs" / "arxiv" / "lanes", pdir / "lanes")
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    stub = bindir / "arxiv-tex"
    stub.write_text(STUB)
    stub.chmod(0o755)
    # needs.tools 门：lane exec 已是 .py，uvx 只被 which() 查不被真跑
    uvx = bindir / "uvx"
    uvx.write_text("#!/bin/sh\nexit 0\n")
    uvx.chmod(0o755)
    (tmp_path / "home").mkdir()
    env = dict(os.environ)
    env.update(
        {
            "LGC_HOME": str(tmp_path / "lgc-home"),
            "LGC_BIN": str(LGC),
            "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
            "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
            "HOME": str(tmp_path / "home"),
            "ARXIV_TEX": str(stub),
            "PATH": str(bindir) + os.pathsep + env["PATH"],
        }
    )
    for k in ("LGC_REFRESH", "LGC_OFF", "LGC_TTL"):
        env.pop(k, None)
    return bindir, env, tmp_path


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


def _decisions(env_):
    return [
        json.loads(line)
        for line in Path(env_["journal"]).read_text().splitlines()
        if json.loads(line).get("type") == "decision"
    ]


def _calls(bindir):
    log = bindir / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def _safe(arxiv_id):
    """与 lane safe_name 同则。"""
    import re

    return re.sub(r"[^A-Za-z0-9_.-]", "_", arxiv_id)


# ---------------------------------------------------------------- bare 矩阵


BARE = [
    ("arxiv:2305.1234", "2305.1234"),
    ("ARXIV:2305.1234", "2305.1234"),
    ("2305.1234v2", "2305.1234v2"),
    ("math.AG/0601234", "math.AG/0601234"),
    ("hep-th/0601234v2", "hep-th/0601234v2"),
]


@pytest.mark.parametrize(("target", "arxiv_id"), BARE, ids=[b[0] for b in BARE])
def test_bare_inputs(afix, target, arxiv_id):
    """裸输入（arxiv:/ARXIV:/新式带 vN/旧式带 archive 前缀+vN）→
    bare_resolve 重写 abs URL → arxiv pack 路由 → lane 收裸 id 位置参 →
    产物 <safeid>.tex 收集 → identity 键 arxivtex:<id>。

    math.AG/0601234 是 canon 劫持实锤：不重写会被归一成 https://math.AG/…
    落 generic 抓停车页返 rc0。"""
    bindir, env, _ = afix
    p = run_engine(["run", target, "--json"], env)
    assert p.returncode == 0, (target, p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)

    bare = [d for d in decs if d.get("stage") == "bare_resolve"]
    assert bare, (target, decs)
    assert bare[0]["pack"] == "arxiv", (target, decs)
    assert bare[0]["target"] == f"https://arxiv.org/abs/{arxiv_id}"

    assert any(d.get("stage") == "route" and d.get("pack") == "arxiv" for d in decs), (
        decs
    )
    ident = next(d for d in decs if d.get("stage") == "identity")
    assert ident["key"] == f"arxivtex:{arxiv_id}"
    assert ident["kind"] == "arxivtex"

    # lane 收裸 id 位置参（URL 会丢 vN/旧式 404——proven bug）
    calls = _calls(bindir)
    assert calls == [f"arxiv-tex {arxiv_id}"], calls

    items = env_["items"]
    assert len(items) == 1, items
    assert items[0]["name"] == _safe(arxiv_id) + ".tex"
    assert Path(items[0]["path"]).read_text().startswith("STUB-TEX")


URLS = [
    ("https://arxiv.org/abs/2305.1234", "2305.1234"),
    ("https://arxiv.org/pdf/2305.1234v2", "2305.1234v2"),
    ("https://arxiv.org/pdf/2305.1234.pdf", "2305.1234"),
    ("https://export.arxiv.org/abs/2305.1234", "2305.1234"),
    ("arxiv.org/abs/2305.1234", "2305.1234"),  # 裸 host 补 scheme
]


@pytest.mark.parametrize(("url", "arxiv_id"), URLS, ids=[u[0] for u in URLS])
def test_url_inputs(afix, url, arxiv_id):
    """URL 形（abs/pdf/export/裸 host）：不经 bare_resolve（journal 无重写
    决策），route 落 arxiv，lane 仍收裸 id。"""
    bindir, env, _ = afix
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 0, (url, p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    assert not [d for d in decs if d.get("stage") == "bare_resolve"], decs
    ident = next(d for d in decs if d.get("stage") == "identity")
    assert ident["key"] == f"arxivtex:{arxiv_id}"
    assert _calls(bindir)[0] == f"arxiv-tex {arxiv_id}"


# ---------------------------------------------------------------- 缓存/戳键


def test_cache_hit_second_run(afix):
    """同输入二跑：satisfies 五键全等（含 mode=full 默认断言）→ cache hit，
    connector 不再被 spawn。"""
    bindir, env, _ = afix
    for i in range(2):
        p = run_engine(["run", "arxiv:2305.1234", "--json"], env)
        assert p.returncode == 0, (i, p.returncode, p.stderr)
    assert len(_calls(bindir)) == 1, _calls(bindir)
    assert "cache: hit" in p.stderr
    decs = _decisions(_envelope(p))
    hit = next(
        d for d in decs if d.get("stage") == "admit" and d.get("verdict") == "hit"
    )
    assert hit["key"] == "arxivtex:2305.1234"
    assert hit.get("satisfies") == 5  # mode+section+三修饰旗标全断言


def test_stamp_and_content_keys_coexist(afix):
    """wrapper 版本戳 arxiv:<id>（value entry）与内容键 arxivtex:<id>
    （file entry）同 ns 共存不互毁——历史上 arxiv:tex:<id> 被规范化器收敛
    回 arxiv:<id>、与同键 value entry INSERT OR REPLACE 互删；arxivtex
    kind 专为拆此冲突而设。"""
    _, env, tmp = afix
    p = run_engine(["run", "arxiv:2305.1234", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    c = lgc(["cat", NS, "arxiv:2305.1234"], env)
    assert c.returncode == 0, (c.returncode, c.stdout, c.stderr)
    assert c.stdout.strip() == "v3 1700000000"
    gdir = tmp / "mat"
    g = lgc(["get", NS, "arxivtex:2305.1234", "--into", str(gdir)], env)
    assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)
    assert (gdir / "2305.1234.tex").read_text().startswith("STUB-TEX")
    # 互查：内容键的 put/get 不曾清掉戳键
    c2 = lgc(["cat", NS, "arxiv:2305.1234"], env)
    assert c2.returncode == 0
    assert c2.stdout.strip() == "v3 1700000000"


# ---------------------------------------------------------------- 失败分类


FAILS = [
    ("notfound", 3, "notcovered"),  # 无 e-print 源/404——能力判词非墓碑
    ("network", 5, "transient"),  # check_source_available 网络异常
    ("empty", 3, "noresults"),  # rc0+空 stdout 无诊断——真实失败形态
    ("section-miss", 3, "notcovered"),  # 节名缺席——参数级不覆盖
    ("usage", 3, "notcovered"),  # argparse rc2——请求形不覆盖
    ("uvx-miss", 5, "dep_absent"),  # wrapper: uvx 未装
]


@pytest.mark.parametrize(("mode", "rc", "cls"), FAILS, ids=[f[0] for f in FAILS])
def test_failure_classification(afix, mode, rc, cls):
    """fail.mode 驱动 connector 失败面 → lane classify → envelope rc/class。"""
    bindir, env, _ = afix
    (bindir / "fail.mode").write_text(mode)
    p = run_engine(["run", "arxiv:2305.1234", "--json"], env)
    assert p.returncode == rc, (mode, p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == cls, env_
    assert _calls(bindir) == ["arxiv-tex 2305.1234"]


# ---------------------------------------------------------------- satisfies{mode}


def test_mode_satisfies_mutual_eviction(afix):
    """satisfies{mode}：full 束不供 abstract 请求，反之亦然——互逐末写赢。

    run1 mode=full → entry params.mode=full；
    run2 无参 → 断言 mode=full → hit；
    run3 mode=abstract → 断言 mode=abstract vs entry full → miss → 重抓 →
    entry 改写 mode=abstract；run4 mode=abstract → hit；
    run5 无参 → 断言 mode=full vs entry abstract → miss → 重抓回 full。
    """
    bindir, env, tmp = afix
    target = "arxiv:2305.1234"

    def entry_mode():
        g = lgc(["get", NS, "arxivtex:2305.1234", "--json"], env)
        assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)
        payload = json.loads(g.stdout.strip().splitlines()[-1])
        return payload["params"]["mode"]

    p1 = run_engine(["run", target, "--json"], env)
    assert p1.returncode == 0
    assert entry_mode() == "full"
    p2 = run_engine(["run", target, "--json"], env)
    assert p2.returncode == 0
    assert "cache: hit" in p2.stderr
    assert len(_calls(bindir)) == 1

    p3 = run_engine(["run", target, "--param", "mode=abstract", "--json"], env)
    assert p3.returncode == 0, (p3.returncode, p3.stderr)
    assert "cache: hit" not in p3.stderr
    assert len(_calls(bindir)) == 2
    assert "--abstract" in _calls(bindir)[-1]
    assert entry_mode() == "abstract"

    p4 = run_engine(["run", target, "--param", "mode=abstract", "--json"], env)
    assert p4.returncode == 0
    assert "cache: hit" in p4.stderr
    assert len(_calls(bindir)) == 2

    p5 = run_engine(["run", target, "--json"], env)
    assert p5.returncode == 0
    assert "cache: hit" not in p5.stderr
    assert len(_calls(bindir)) == 3
    assert entry_mode() == "full"


def test_mode_sections_flags_and_artifact(afix):
    """mode=sections&section=A,B → 复数 --section 旗标 + .sections.tex 产物；
    entry params 记 mode=sections/section 原值。"""
    bindir, env, _ = afix
    p = run_engine(
        [
            "run",
            "arxiv:2305.1234",
            "--param",
            "mode=sections",
            "--param",
            "section=Intro,Methods",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    call = _calls(bindir)[-1]
    assert "--section Intro" in call
    assert "--section Methods" in call
    assert _envelope(p)["items"][0]["name"] == "2305.1234.sections.tex"
    g = lgc(["get", NS, "arxivtex:2305.1234", "--json"], env)
    params = json.loads(g.stdout.strip().splitlines()[-1])["params"]
    assert params["mode"] == "sections"
    assert params["section"] == "Intro,Methods"


def test_stamp_flags_passthrough(afix):
    """engine 保留 param refresh/no_cache/cache_ttl → wrapper 同名旗标透传
    （戳层语义 LGC_REFRESH/LGC_OFF/LGC_TTL 的壳面入口）。"""
    bindir, env, _ = afix
    p = run_engine(
        [
            "run",
            "arxiv:2305.1234",
            "--param",
            "refresh",
            "--param",
            "cache_ttl=60",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stderr)
    call = _calls(bindir)[-1]
    assert "--refresh" in call
    assert "--cache-ttl 60" in call


def test_modifier_flags_satisfies(afix):
    """修饰旗标进 satisfies：no_comments 束不供无修饰请求（等值断言）。"""
    bindir, env, _ = afix
    target = "arxiv:2305.1234"
    p1 = run_engine(["run", target, "--param", "no_comments", "--json"], env)
    assert p1.returncode == 0, (p1.returncode, p1.stderr)
    assert "--no-comments" in _calls(bindir)[-1]
    # 无修饰请求 → 断言 no_comments=false vs entry true → miss → 重抓
    p2 = run_engine(["run", target, "--json"], env)
    assert p2.returncode == 0
    assert "cache: hit" not in p2.stderr
    assert len(_calls(bindir)) == 2
    # 同修饰请求 → 断言 no_comments=false vs entry false（互逐后新束）→ hit
    p3 = run_engine(["run", target, "--json"], env)
    assert p3.returncode == 0
    assert "cache: hit" in p3.stderr
    assert len(_calls(bindir)) == 2


# ---------------------------------------------------------------- 闸/路由


def test_unknown_param_rc2(afix):
    """未声明 param → rc2 refused，stderr 列合法集（含 mode/section/保留名）。"""
    _, env, _ = afix
    p = run_engine(["run", "arxiv:2305.1234", "--param", "bogus=1"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "bogus" in p.stderr
    for k in ("mode", "section", "no_comments", "refresh", "kind"):
        assert k in p.stderr


def test_route_miss_nonarxiv(afix):
    """非 arxiv host → 无 pack 覆盖 rc3 notcovered（本测试 packs 面只挂 arxiv）。"""
    _, env, _ = afix
    p = run_engine(["run", "https://example.com/x", "--json"], env)
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    assert "no pack covers" in p.stderr


def test_no_id_in_url_notcovered(afix):
    """arxiv.org 非论文页（/list/…）→ lane 解不出 id → notcovered rc3。"""
    _, env, _ = afix
    p = run_engine(["run", "https://arxiv.org/list/cs.AI/recent", "--json"], env)
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    assert _envelope(p)["class"] == "notcovered"
