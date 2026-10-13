"""test_pack_canvas.py — canvas pack enum/data-lane + meta-lane e2e。

真 pack.toml 复制进 tmp packs/；canvas-rest/canvas-mint 是原生 lane，
直接 spawn PATH 上的 stub canvas-get（fakebin + CANVAS_GET 双保险）。
stub 记录 argv、按 rc.canvas 吐错、--mint 时真 lgc vput 铸键——meta-lane
cred 写入路径的离线证据。全部离线，无真实网络。

kind=enum 由分发层注入（link-get:--files→kind=enum enum=files 平价）；
engine 自身不从旗标派生 enum——测试按同一合同传参。
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
PACK_TOML = ROOT / "packs" / "canvas" / "pack.toml"

OC = "https://oc.sjtu.edu.cn/courses/97882"
NS = "canvas-skill"

# stub canvas-get：记录 argv → calls.log；rc.canvas 控错；--mint 真 lgc vput；
# monolith 形态（<url> -o <adir>）写 out.md 产物；零 dash 参（裸课程位置参）
# 吐 fixture 讲次表——lectures 臂的 argv 纯净断言；其余打印行为行。
STUB = """#!/bin/bash
set -u
here="$(cd "$(dirname "$0")" && pwd)"
echo "canvas-get $*" >> "$here/calls.log"
rc=0
[ -f "$here/rc.canvas" ] && rc="$(tr -d '[:space:]' < "$here/rc.canvas")"
if [ "$rc" != "0" ]; then echo "stub failure rc=$rc" >&2; exit "$rc"; fi
prev=""
hasflag=0
for a in "$@"; do
  if [ "$a" = "--mint" ]; then
    "${LGC_BIN:-lgc}" put canvas-skill "jwt:deadbeef:97882" --value "stub-jwt" >/dev/null
    "${LGC_BIN:-lgc}" put canvas-skill "tecl:deadbeef:97882" --value "4321" >/dev/null
    printf 'minted jwt:deadbeef:97882\\nminted tecl:deadbeef:97882 = 4321\\n'
    exit 0
  fi
  case "$a" in -*) hasflag=1 ;; esac
  if [ "$prev" = "-o" ]; then
    mkdir -p "$a"
    printf 'stub artifact\\n' > "$a/out.md"
  fi
  prev="$a"
done
if [ "$hasflag" = "0" ]; then
  printf ' 1. [cour_id=1001] stub lecture one\\n 2. [cour_id=1002] stub lecture two\\n'
  exit 0
fi
printf 'stub out for %s\\n' "$*"
exit 0
"""


@pytest.fixture
def cfix(tmp_path):
    pdir = tmp_path / "packs" / "canvas"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(PACK_TOML.read_text(encoding="utf-8"))
    # 原生 lane 以 pack.toml 相对路径解析——真 lanes/ 目录软链进来
    os.symlink(ROOT / "packs" / "canvas" / "lanes", pdir / "lanes")
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    stub = bindir / "canvas-get"
    stub.write_text(STUB)
    stub.chmod(0o755)
    # canvas-get lane 的 needs.tools（ffmpeg/curl）——which() 查不真跑
    for tool in ("ffmpeg", "curl"):
        t = bindir / tool
        t.write_text("#!/bin/sh\nexit 0\n")
        t.chmod(0o755)
    (tmp_path / "home").mkdir()
    env = dict(os.environ)
    env.update(
        {
            "LGC_HOME": str(tmp_path / "lgc-home"),
            "LGC_BIN": str(LGC),
            "FETCH_ENGINE_JOBS": str(tmp_path / "jobs"),
            "FETCH_ENGINE_PACKS": str(tmp_path / "packs"),
            "HOME": str(tmp_path / "home"),
            "CANVAS_GET": str(stub),
            "PATH": str(bindir) + os.pathsep + env["PATH"],
        }
    )
    env.pop("LGC_REFRESH", None)
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
    out = []
    for line in Path(env_["journal"]).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "decision":
            out.append(rec)
    return out


def _route_lanes(decs):
    return [d["lanes"] for d in decs if d.get("stage") == "route" and "lanes" in d]


def _calls(bindir):
    log = bindir / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


# ------------------------------------------------------- enum data lanes


def test_enum_courses_data(cfix):
    """kind=enum + enum=courses → canvas-rest：data 终态 payload 逐字带
    connector stdout；route 记 canvas-rest；argv 恰为 --list-courses。"""
    bindir, env, _ = cfix
    p = run_engine(
        [
            "run",
            "https://oc.sjtu.edu.cn/",
            "-p",
            "canvas",
            "--param",
            "kind=enum",
            "--param",
            "enum=courses",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stderr)
    env_ = _envelope(p)
    assert env_["data"] == "stub out for --list-courses\n"
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["canvas-rest"]]
    assert _calls(bindir) == ["canvas-get --list-courses"]


def test_enum_files_course_arg(cfix):
    """enum=files → canvas-rest 把 raw 作课程位置参：argv <url> --files。"""
    bindir, env, _ = cfix
    p = run_engine(
        [
            "run",
            OC,
            "-p",
            "canvas",
            "--param",
            "kind=enum",
            "--param",
            "enum=files",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stderr)
    env_ = _envelope(p)
    assert env_["data"] == f"stub out for {OC} --files\n"
    assert _calls(bindir) == [f"canvas-get {OC} --files"]


def test_enum_mint_writes_cred_keys(cfix):
    """enum=mint → canvas-mint meta-lane：stub 真 lgc vput 铸 jwt/tecl 键
    → get 命中——writes_cred cred 生产路径的端到端证据。"""
    bindir, env, tmp = cfix
    p = run_engine(
        [
            "run",
            OC,
            "-p",
            "canvas",
            "--param",
            "kind=enum",
            "--param",
            "enum=mint",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stderr)
    env_ = _envelope(p)
    assert "minted jwt:deadbeef:97882" in env_["data"]
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["canvas-mint"]]
    assert _calls(bindir) == [f"canvas-get {OC} --mint"]
    # cred value 键真落了隔离 LGC_HOME——jwt 20min/tecl 180d 语义归 lgc kind
    g = lgc(["get", NS, "jwt:deadbeef:97882"], env)
    assert g.returncode == 0, (g.returncode, g.stdout, g.stderr)
    assert g.stdout.strip() == "stub-jwt"
    g2 = lgc(["get", NS, "tecl:deadbeef:97882"], env)
    assert g2.returncode == 0
    assert g2.stdout.strip() == "4321"


def test_enum_error_maps_class(cfix):
    """canvas-rest 上游 rc5 → transient 终态 → envelope rc5 class=transient；
    self-managed 不上账——内容键无 lane note。"""
    bindir, env, _ = cfix
    (bindir / "rc.canvas").write_text("5")
    p = run_engine(
        [
            "run",
            "https://oc.sjtu.edu.cn/",
            "-p",
            "canvas",
            "--param",
            "kind=enum",
            "--param",
            "enum=courses",
            "--json",
        ],
        env,
    )
    assert p.returncode == 5, (p.returncode, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "transient"
    lp = lgc(["lane", NS, "probe", "canvas-rest"], env)
    assert lp.returncode == 0, (lp.returncode, lp.stdout, lp.stderr)


def test_lecture_arm_monolith(cfix):
    """显式 kind=lecture → canvas-get monolith wrap：shim argv 带 -o，
    stub 产物经 collect 进 envelope items——重排 lanes 后旧臂未回退。
    （裸跑课程根 URL 现在经 kind_by_url 判 enum——见 bare/默认臂测试）"""
    bindir, env, _ = cfix
    p = run_engine(
        ["run", OC, "-p", "canvas", "--param", "kind=lecture", "--json"], env
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["canvas-get"]]
    assert env_["items"], env_
    assert _calls(bindir)
    assert "-o" in _calls(bindir)[0]


# ------------------------------------------------------- bare 落地 + lectures 臂


def test_bare_course_id_lands_lectures_enum(cfix):
    """'fetch-engine run 97882'（裸课程号，无任何 param）：[[match.bare]] 重写
    课程根 URL → kind_by_url 判 kind=enum → canvas-rest 缺省 lectures 臂 →
    {type:data} 终态，不再是 monolith stdout 无产物的 noresults。"""
    bindir, env, _ = cfix
    p = run_engine(["run", "97882", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert "stub lecture one" in env_["data"], env_
    decs = _decisions(env_)
    bare = [d for d in decs if d.get("stage") == "bare_resolve"]
    assert bare, decs
    assert bare[0]["target"] == OC, decs
    ident = [d for d in decs if d.get("stage") == "identity"]
    assert ident, decs
    assert ident[0]["kind"] == "enum", decs
    assert _route_lanes(decs) == [["canvas-rest"]]
    # argv 恰为裸课程 URL——无旗标无 -o（fixture 讲次表只在零 dash 参时吐）
    assert _calls(bindir) == [f"canvas-get {OC}"]


def test_course_root_url_default_lectures(cfix):
    """课程根 URL 裸跑（无 -p 无 kind 注入）→ kind_by_url → enum →
    canvas-rest lectures 臂 {type:data}。"""
    bindir, env, _ = cfix
    p = run_engine(["run", OC, "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert "stub lecture two" in env_["data"], env_
    decs = _decisions(env_)
    assert not any(d.get("stage") == "bare_resolve" for d in decs)
    assert _route_lanes(decs) == [["canvas-rest"]]
    assert _calls(bindir) == [f"canvas-get {OC}"]


def test_bare_id_with_files_param(cfix):
    """'97882' + --files 形态（kind=enum enum=files 注入）：bare 重写后
    files 臂照常 —— argv <重写后课程 URL> --files。"""
    bindir, env, _ = cfix
    p = run_engine(
        [
            "run",
            "97882",
            "--param",
            "kind=enum",
            "--param",
            "enum=files",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert env_["data"] == f"stub out for {OC} --files\n"
    assert _route_lanes(_decisions(env_)) == [["canvas-rest"]]
    assert _calls(bindir) == [f"canvas-get {OC} --files"]


def test_bare_id_bool_flags_derive_enum(cfix):
    """裸课程号 + 布尔旗标回波（'link-get 97882 --files' 真形态——壳域名臂不
    认裸 ID，只透传回波不注 enum）：kind_by_url 判 enum → routes 兜
    canvas-rest → lane 从回波派生 enum 臂——6d 修复前静默打讲次表。"""
    bindir, env, _ = cfix
    for param, want_call, want_data in [
        ("files", f"canvas-get {OC} --files", f"stub out for {OC} --files\n"),
        (
            "announcements",
            f"canvas-get {OC} --announcements",
            f"stub out for {OC} --announcements\n",
        ),
        (
            "assignments",
            f"canvas-get {OC} --assignments",
            f"stub out for {OC} --assignments\n",
        ),
        (
            "list_courses",
            "canvas-get --list-courses",
            "stub out for --list-courses\n",
        ),
    ]:
        clog = bindir / "calls.log"
        if clog.exists():
            clog.unlink()
        p = run_engine(["run", "97882", "--param", param, "--json"], env)
        assert p.returncode == 0, (param, p.returncode, p.stderr)
        env_ = _envelope(p)
        assert env_["data"] == want_data, (param, env_)
        assert _route_lanes(_decisions(env_)) == [["canvas-rest"]], param
        assert _calls(bindir) == [want_call], param


def test_bare_id_mint_bool_routes_to_mint(cfix):
    """'97882 --param mint'（link-get --mint 真形态，无 enum 注入）→
    routes params={mint=true} 臂锁 canvas-mint——不落 canvas-rest 打讲次。"""
    bindir, env, _ = cfix
    p = run_engine(["run", "97882", "--param", "mint", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    env_ = _envelope(p)
    assert "minted jwt:deadbeef:97882" in env_["data"]
    assert _route_lanes(_decisions(env_)) == [["canvas-mint"]]
    assert _calls(bindir) == [f"canvas-get {OC} --mint"]
    g = lgc(["get", NS, "jwt:deadbeef:97882"], env)
    assert g.returncode == 0
    assert g.stdout.strip() == "stub-jwt"


def test_bare_id_download_falls_to_monolith(cfix, tmp_path):
    """'97882 --param download=DIR'（link-get --download 真形态——壳旁路只认
    sjtu host，bare ID 进 engine）→ arm2 download="" 闸漏过 → canvas-get
    monolith 带 --download DIR 真下载——不再静默打讲次表。"""
    bindir, env, _ = cfix
    dl = str(tmp_path / "dl")
    p = run_engine(["run", "97882", "--param", f"download={dl}", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert _route_lanes(_decisions(env_)) == [["canvas-get"]]
    call = _calls(bindir)[0]
    assert "-o" in call, call
    assert f"--download {dl}" in call, call


def test_enum_lectures_explicit_param(cfix):
    """显式 enum=lectures → 同一 lectures 臂（默认与显式同路径）。"""
    bindir, env, _ = cfix
    p = run_engine(
        [
            "run",
            OC,
            "-p",
            "canvas",
            "--param",
            "kind=enum",
            "--param",
            "enum=lectures",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert "stub lecture one" in env_["data"], env_
    assert _calls(bindir) == [f"canvas-get {OC}"]


def test_enum_kind_with_lecture_param_downloads(cfix):
    """kind=enum 落地但带 lecture=2（link-get --lecture 只注值不注 kind 的
    真实形态）→ 下载意图不被列表臂吃掉：route 漏过 lecture='' 闸 →
    canvas-get monolith --lecture 2。"""
    bindir, env, _ = cfix
    p = run_engine(["run", OC, "-p", "canvas", "--param", "lecture=2", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    ident = [d for d in decs if d.get("stage") == "identity"]
    assert ident, decs
    assert ident[0]["kind"] == "enum", decs  # kind_by_url 照常判 enum
    assert _route_lanes(decs) == [["canvas-get"]]
    assert env_["items"], env_
    call = _calls(bindir)[0]
    assert "-o" in call, call
    assert "--lecture 2" in call, call


def test_deep_course_url_stays_lecture_kind(cfix):
    """深路径 /courses/<id>/files（非课程根）不命中 kind_by_url →
    kinds[0]=lecture → monolith 臂照旧。"""
    bindir, env, _ = cfix
    deep = OC + "/files"
    p = run_engine(["run", deep, "-p", "canvas", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    ident = [d for d in decs if d.get("stage") == "identity"]
    assert ident, decs
    assert ident[0]["kind"] == "lecture", decs
    assert _route_lanes(decs) == [["canvas-get"]]
    assert env_["items"], env_
    assert "-o" in _calls(bindir)[0]


def test_enum_mint_route_still_wins(cfix):
    """enum=mint 在新增 lectures 默认臂之后仍优先路由 canvas-mint——
    route 臂序不回退。"""
    bindir, env, _ = cfix
    p = run_engine(
        [
            "run",
            OC,
            "-p",
            "canvas",
            "--param",
            "kind=enum",
            "--param",
            "enum=mint",
            "--json",
        ],
        env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    assert _route_lanes(_decisions(env_)) == [["canvas-mint"]]
