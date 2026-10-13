"""test_pack_generic_doc.py — generic pack kind=doc 臂（MinerU 云解析车道）e2e。

真 pack.toml 复制进 tmp packs/；lanes/ 软链（或复制）进 pack 目录；stub
`mineru` 落 fakebin 上 PATH——lane 解析序 $MINERU_BIN → which → 兄弟 skill
脚本，which 先于仓内真 mineru.py 命中。monolith connector 的 pack.dir 相对
路径 ../../scripts/connectors/generic-get → tmp 下同位落 stub。全部离线。

隐私边界 e2e（mineru_lane docstring 两层设计）：
- 路由层：签名类/非 https 文档 URL → [kind_by_url] doc-signed 伪 kind →
  route_miss rc2，lane 根本不被 spawn（journal 无 exec 记录）；
- engine SSRF 闸：字面私网 host → admit 闸 rc2（先于 identity）；
- lane 层兜底：lane-run 旁路直送私域/凭据 URL → 自检 notcovered。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts" / "fetch_engine.py"
LGC = ROOT / "scripts" / "lgc"
PACK_TOML = ROOT / "packs" / "generic" / "pack.toml"
LANES_DIR = ROOT / "packs" / "generic" / "lanes"
LANE = LANES_DIR / "mineru_lane.py"

DOC_URL = "https://example.com/paper.pdf"

# stub mineru：记录 argv → $LGC_HOME/calls.log；rc.mineru 存在则按 err.mineru
# 吐错+failed 状态报告退出（分类测试）；正常路径在 -o 目录写 <stem>/<stem>.md
# + images/p1.png（dir-diff 收产物），stdout 吐 --json 合同的状态行。
MINERU_STUB = """#!/bin/bash
set -u
lgc_home="${LGC_HOME:-/tmp}"
echo "mineru $*" >> "$lgc_home/calls.log"
if [ -f "$lgc_home/rc.mineru" ]; then
  rc="$(tr -d '[:space:]' < "$lgc_home/rc.mineru")"
  msg="stub failure rc=$rc"
  [ -f "$lgc_home/err.mineru" ] && msg="$(cat "$lgc_home/err.mineru")"
  echo "$msg" >&2
  printf '{"total":1,"done":0,"skipped":0,"failed":1,"results":[{"state":"failed","error":"%s"}]}\\n' "$msg"
  exit "$rc"
fi
url=""
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --timeout|--lang|--pages|--model|--api|--format) shift 2 ;;
    *) case "$1" in -*) shift ;; *) [ -z "$url" ] && url="$1"; shift ;; esac ;;
  esac
done
base="${url%%\\?*}"
base="${base##*/}"
stem="${base%.*}"
[ -n "$stem" ] || stem="doc"
mkdir -p "$out/$stem/images"
printf '# stub doc\\n\\nparsed %s\\n' "$url" > "$out/$stem/$stem.md"
printf 'fakepng' > "$out/$stem/images/p1.png"
printf '{"total":1,"done":1,"skipped":0,"failed":0,"results":[{"state":"done","api":"agent","modality":"pdf","task_id":"stub-task-1"}]}\\n'
exit 0
"""

# stub generic-get connector（monolith argv = {url} -o {artifact_dir}）：
# 产物 out.md 经 shim dir-diff 收进 result；argv 记同一 calls.log。
CONNECTOR_STUB = """#!/bin/bash
set -u
echo "generic-get $*" >> "${LGC_HOME:-/tmp}/calls.log"
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then
    mkdir -p "$a"
    printf 'stub article\\n' > "$a/out.md"
  fi
  prev="$a"
done
printf 'stub connector done\\n'
exit 0
"""


def _build(tmp_path, copy_lanes=False, with_mineru=True):
    """装 tmp packs/generic：真 pack.toml + lanes（软链真目录；copy_lanes 时
    复制到 tmp 深处让 SKILL_SCRIPT parents[4] 落空——dep_absent 测试用）。"""
    pdir = tmp_path / "packs" / "generic"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(PACK_TOML.read_text(encoding="utf-8"))
    if copy_lanes:
        # 复制而非软链：lane __file__ resolve 到 tmp 树下，parents[4]/mineru/
        # scripts/mineru.py 不存在 → resolve_mineru 只能依赖 PATH/MINERU_BIN
        ldir = tmp_path / "lane_copy" / "lanes"
        shutil.copytree(LANES_DIR, ldir)
        os.symlink(ldir, pdir / "lanes")
    else:
        os.symlink(LANES_DIR, pdir / "lanes")
    # monolith connector 的 pack.dir 相对路径：packs/generic/../../scripts/
    conn = tmp_path / "scripts" / "connectors" / "generic-get"
    conn.parent.mkdir(parents=True)
    conn.write_text(CONNECTOR_STUB)
    conn.chmod(0o755)
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    if with_mineru:
        stub = bindir / "mineru"
        stub.write_text(MINERU_STUB)
        stub.chmod(0o755)
    (tmp_path / "home").mkdir()
    env = dict(os.environ)
    env.update(
        {
            "LGC_HOME": str(tmp_path / "lgc-home"),
            "LGC_BIN": str(LGC),
            "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
            "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
            "HOME": str(tmp_path / "home"),
            "PATH": str(bindir) + os.pathsep + env["PATH"],
        }
    )
    # 私网 host 用例要靠 engine SSRF 闸；MINERU_BIN 不设（走 PATH stub）
    for k in (
        "FETCH_ENGINE_ALLOW_PRIVATE",
        "MINERU_BIN",
        "MINERU_TOKEN",
        "LGC_REFRESH",
    ):
        env.pop(k, None)
    return bindir, env, tmp_path


@pytest.fixture
def gfix(tmp_path):
    return _build(tmp_path)


def run_engine(args, env, timeout=120):
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _envelope(p):
    return json.loads(p.stdout.strip().splitlines()[-1])


def _decisions(env_):
    out = []
    for line in Path(env_["journal"]).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "decision":
            out.append(rec)
    return out


def _route_lanes(decs):
    return [d["lanes"] for d in decs if d.get("stage") == "route" and "lanes" in d]


def _identity_kind(decs):
    for d in decs:
        if d.get("stage") == "identity":
            return d.get("kind"), d.get("key"), bool(d.get("kind_miss"))
    return None, None, None


def _calls(env_):
    log = Path(env_["LGC_HOME"]) / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


# ------------------------------------------------------- doc 臂：路由 + 产物


def test_doc_url_routes_mineru_and_collects(gfix):
    """公网 .pdf URL → kind_by_url 判 doc → routes 臂 mineru → lane spawn
    PATH stub → <stem>/<stem>.md + images 产物 dir-diff 收进 items。"""
    _bindir, env, _tmp = gfix
    p = run_engine(["run", DOC_URL, "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    kind, key, miss = _identity_kind(decs)
    assert kind == "doc", decs
    assert key == f"doc:{DOC_URL}", decs
    assert not miss
    assert _route_lanes(decs) == [["mineru"]]
    names = {it["name"] for it in env_["items"]}
    assert {"paper/paper.md", "paper/images/p1.png"} <= names, env_
    md = next(it for it in env_["items"] if it["name"] == "paper/paper.md")
    assert f"parsed {DOC_URL}" in Path(md["path"]).read_text()
    calls = _calls(env)
    assert len(calls) == 1, calls
    assert calls[0].startswith(f"mineru {DOC_URL} "), calls
    assert " -o " in calls[0]
    assert " --json " in calls[0]


def test_doc_other_extensions_route_doc(gfix):
    """.docx/.epub 等其余 doc 扩展同样落 doc 臂（kind_by_url 第二正则）。"""
    _bindir, env, _tmp = gfix
    for ext in ("docx", "epub", "pptx"):
        url = f"https://example.com/files/report.{ext}"
        p = run_engine(["run", url, "--param", "no_cache", "--json"], env)
        assert p.returncode == 0, (ext, p.returncode, p.stderr)
        env_ = _envelope(p)
        decs = _decisions(env_)
        kind, _key, _miss = _identity_kind(decs)
        assert kind == "doc", (ext, decs)
        assert _route_lanes(decs) == [["mineru"]], (ext, decs)


def test_kind_forced_doc_overrides_url_shape(gfix):
    """--param kind=doc 强指时 kind_by_url 不参选：文章形 URL 也走 mineru 臂。"""
    _bindir, env, _tmp = gfix
    url = "https://example.com/post/123"
    p = run_engine(["run", url, "--param", "kind=doc", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    kind, _key, _miss = _identity_kind(decs)
    assert kind == "doc", decs
    assert _route_lanes(decs) == [["mineru"]]
    calls = _calls(env)
    assert len(calls) == 1, calls
    assert calls[0].startswith(f"mineru {url} -o "), calls
    assert "--json" in calls[0]
    assert "--timeout 597" in calls[0]


def test_doc_lane_params_pass_through(gfix):
    """[params] 声明的 mineru 旗标经 lane argv 透传（--lang/--ocr 进 stub argv）。"""
    _bindir, env, _tmp = gfix
    p = run_engine(
        [
            "run",
            DOC_URL,
            "--param",
            "lang=en",
            "--param",
            "ocr",
            "--param",
            "pages=1-5",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    call = _calls(env)[0]
    assert "--lang en" in call, call
    assert "--ocr" in call, call
    assert "--pages 1-5" in call, call


# ------------------------------------------------------- 隐私边界：路由层 rc2


def test_signed_doc_url_route_miss_rc2(gfix):
    """?X-Amz-Signature= 签名文档 URL → doc-signed 伪 kind（pack.kinds 外）→
    无臂 → route_miss rc2：lane 不 spawn，cache 不探测。"""
    _bindir, env, _tmp = gfix
    url = "https://example.com/paper.pdf?X-Amz-Signature=deadbeef&x=1"
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "refused"
    decs = _decisions(env_)
    kind, _key, _miss = _identity_kind(decs)
    assert kind == "doc-signed", decs
    rm = [d for d in decs if d.get("stage") == "route_miss"]
    assert rm, decs
    assert rm[0].get("kind") == "doc-signed", decs
    assert not any(d.get("stage") == "exec" for d in decs), decs
    assert not any(d.get("gate") == "cache" for d in decs), decs
    assert _calls(env) == []
    assert "no route" in p.stderr


def test_http_doc_url_route_miss_rc2(gfix):
    """非 https 的文档 URL 同落 doc-signed——明文链不喂云（路由层先行拒）。"""
    _bindir, env, _tmp = gfix
    p = run_engine(["run", "http://example.com/paper.pdf", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "refused"
    decs = _decisions(env_)
    kind, _key, _miss = _identity_kind(decs)
    assert kind == "doc-signed", decs
    assert _calls(env) == []


def test_token_param_doc_url_route_miss_rc2(gfix):
    """?token= 凭据参数形同样判 doc-signed（CRED_PARAMS 名表口径）。"""
    _bindir, env, _tmp = gfix
    p = run_engine(["run", "https://example.com/paper.pdf?token=sekrit", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    decs = _decisions(_envelope(p))
    kind, _key, _miss = _identity_kind(decs)
    assert kind == "doc-signed", decs


def test_private_host_doc_ssrf_rc2(gfix):
    """字面私网 host：engine admit SSRF 闸先行 rc2（identity 之前）——
    文档不查询是谁的 kind。"""
    _bindir, env, _tmp = gfix
    p = run_engine(["run", "https://127.0.0.1/paper.pdf", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "refused"
    decs = _decisions(env_)
    ssrf = [d for d in decs if d.get("gate") == "ssrf"]
    assert ssrf, decs
    assert "private" in ssrf[0].get("deny", ""), decs
    assert not any(d.get("stage") == "identity" for d in decs), decs
    assert _calls(env) == []


# ------------------------------------------------------- article 臂不回退


def test_article_url_still_routes_generic_get(gfix):
    """普通文章 URL：kind_by_url 不中 → kinds[0]=article（kind_miss）→
    routes article 臂 generic-get monolith——[[routes]] 存在后旧臂未 rc2。"""
    _bindir, env, _tmp = gfix
    url = "https://example.com/post/123"
    p = run_engine(["run", url, "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    kind, key, miss = _identity_kind(decs)
    assert kind == "article", decs
    assert key == f"article:{url}", decs  # article 键形未变（generic-get K 平价）
    assert miss
    assert _route_lanes(decs) == [["generic-get"]]
    names = {it["name"] for it in env_["items"]}
    assert "out.md" in names, env_
    calls = _calls(env)
    assert len(calls) == 1, calls
    assert calls[0].startswith(f"generic-get {url} -o "), calls


def test_unknown_param_still_rc2(gfix):
    """params 闸不受新参数面影响：未声明键照旧 rc2。"""
    _bindir, env, _tmp = gfix
    p = run_engine(["run", DOC_URL, "--param", "bogus=1", "--json"], env)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "bogus" in p.stderr


# ------------------------------------------------------- lane 错误分类 + dep


def test_mineru_failure_classifies_transient(gfix):
    """mineru 失败报告 rate limit 文本 → lane 归 transient（retryable）→
    envelope rc5——rate_limited 不在 engine RC 表，直发会 KeyError。"""
    _bindir, env, tmp = gfix
    (Path(env["LGC_HOME"])).mkdir(parents=True, exist_ok=True)
    (Path(env["LGC_HOME"]) / "rc.mineru").write_text("1")
    (Path(env["LGC_HOME"]) / "err.mineru").write_text(
        "rate limit exceeded (429), retry later"
    )
    p = run_engine(["run", DOC_URL, "--json"], env)
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "transient", env_
    assert _route_lanes(_decisions(env_)) == [["mineru"]]


def test_mineru_dep_absent(tmp_path):
    """mineru 不可解析（无 PATH/MINERU_BIN，兄弟 skill 路径落空）→ lane rc10
    静默跳过 → 全 skip → dep_absent rc5，不落账不崩。"""
    _bindir, env, _tmp = _build(tmp_path, copy_lanes=True, with_mineru=False)
    p = run_engine(["run", DOC_URL, "--json"], env)
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "dep_absent", env_
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["mineru"]]  # 臂选中但车道缺席
    assert _calls(env) == []


# ------------------------------------------------------- lane 层隐私兜底


@pytest.mark.parametrize(
    ("url", "frag"),
    [
        ("https://127.0.0.1/x.pdf", "private address"),
        ("http://example.com/x.pdf", "scheme 'http'"),
        ("https://user:pw@example.com/x.pdf", "userinfo"),
        ("https://example.com/x.pdf?sig=abc", "credential-ish query param"),
        ("https://192.168.1.1.nip.io/x.pdf", "dns-rebind"),
    ],
)
def test_lane_run_privacy_refuse(url, frag, tmp_path):
    """lane-run 旁路（绕过路由层 doc-signed/SSRF）直送私域/凭据 URL →
    lane 自检 refusal_reason → {type:error class:notcovered} 终态 rc0——
    深度防御层独立生效。"""
    adir = tmp_path / "ad"
    adir.mkdir()
    req = {
        "job_id": "t-priv",
        "identity": {"raw": url, "key": "doc:x", "kind": "doc", "params": {}},
        "ctx": {
            "artifact_dir": str(adir),
            "journal_dir": str(tmp_path),
            "budget_ms": 5000,
            "key": "doc:x",
        },
    }
    p = subprocess.run(
        [sys.executable, str(LANE)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    term = json.loads(p.stdout.strip().splitlines()[-1])
    assert term["type"] == "error", term
    assert term["class"] == "notcovered", term
    assert term["retryable"] is False, term
    assert frag in term["evidence"], term
    # 拒在 spawn 之前：产物目录零写入
    assert list(adir.rglob("*")) == []


def test_lane_run_happy_path_direct(tmp_path, gfix):
    """lane-run 直送公网 doc URL：隐私自检过 → spawn PATH stub → result。"""
    _bindir, env, _tmp = gfix
    adir = tmp_path / "ad2"
    adir.mkdir()
    req = {
        "job_id": "t-ok",
        "identity": {
            "raw": DOC_URL,
            "key": f"doc:{DOC_URL}",
            "kind": "doc",
            "params": {},
        },
        "ctx": {
            "artifact_dir": str(adir),
            "journal_dir": str(tmp_path),
            "budget_ms": 60000,
            "key": "doc:x",
        },
    }
    p = subprocess.run(
        [sys.executable, str(LANE)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    term = json.loads(p.stdout.strip().splitlines()[-1])
    assert term["type"] == "result", term
    assert {it["name"] for it in term["items"]} >= {"paper/paper.md"}, term
    assert term.get("params", {}).get("task_id") == "stub-task-1", term


# ------------------------------------------------------- routes 覆盖自检


def test_selftest_pack_generic_passes(gfix):
    """`fetch-engine selftest -p generic`：lane exec 可解析 + routes 覆盖
    全部 kind（doc/article 两臂）→ PASS——doc-signed 是 kinds 外伪 kind，
    不触发覆盖检查。"""
    _bindir, env, _tmp = gfix
    p = run_engine(["selftest", "-p", "generic"], env, timeout=60)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "selftest: PASS" in p.stdout, p.stdout
    assert "routes 覆盖全部" in p.stdout, p.stdout
