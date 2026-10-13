"""test_pack_bilibili_mint.py — bilibili pack mint meta-lane e2e。

真 pack.toml 复制进 tmp packs/；lanes/ 软链回真身（bili_mint 经 __file__
解析到真 scripts/refresh-cookies.sh——与生产同一条解析路径）；refresh
脚本依赖的 ssh/scp/curl 全 fakebin stub，行为由旁文件控制（rc.ssh/
ssh.failat/ssh.mode/rc.scp/nav.mode/rc.curl——canvas rc.canvas 平价）。
monolith 臂的 connector 按 pack.toml 相对位 ../../scripts/connectors/
bilibili-get stub 进 tmp 树。凭证文件落 tmp HOME。全离线无真实网络。

覆盖（任务契约）：kind=mint 只进 bili_mint（永不落抓取臂——含同键已存
内容时的缓存变体）；mint 成功 → data 终态 + 凭证文件落预期路径（600、
BBDown.data 由 netscape 重写）；ssh 不可达 → dep_absent（permission
denied 带 needs_human）；isLogin false → auth_expired + needs_human +
cred8 域账（冷却防 hammer）；transient 不上账（fail_note=false 死循环
陷阱回归）；裸 --param mint 由 params 兜底臂同锁；正常抓取不受影响；
link-get --mint 分发带 kind=mint 覆盖。
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
LINK_GET = ROOT / "scripts" / "link-get"
PACK_TOML = ROOT / "packs" / "bilibili" / "pack.toml"
PROBE = ROOT / "packs" / "bilibili" / "probe.sh"
REFRESH = ROOT / "scripts" / "refresh-cookies.sh"
NS = "link-get"

BVID_URL = "https://www.bilibili.com/video/BV1xx411c7mD"
MINT_KEY = "bili:meta:mint"

# --- fakebin stubs（旁文件控错，不依赖 env 透传——lane env 白名单剥壳） ---

SSH_STUB = """#!/bin/bash
here="$(cd "$(dirname "$0")" && pwd)"
echo "ssh $*" >> "$here/ssh.log"
n=$(cat "$here/ssh.count" 2>/dev/null || echo 0)
n=$((n + 1)); echo "$n" > "$here/ssh.count"
rc=0
failat="$(tr -d '[:space:]' < "$here/ssh.failat" 2>/dev/null || true)"
[ -n "$failat" ] && [ "$n" -ge "$failat" ] && rc=255
[ -f "$here/rc.ssh" ] && rc="$(tr -d '[:space:]' < "$here/rc.ssh")"
if [ "$rc" != "0" ]; then
  mode="$(tr -d '[:space:]' < "$here/ssh.mode" 2>/dev/null || echo timeout)"
  case "$mode" in
  denied) echo "ssh: Permission denied (publickey)." >&2 ;;
  *) echo "ssh: connect to host fht-mba port 22: Connection timed out" >&2 ;;
  esac
fi
exit "$rc"
"""

SCP_STUB = """#!/bin/bash
here="$(cd "$(dirname "$0")" && pwd)"
echo "scp $*" >> "$here/scp.log"
rc=0
[ -f "$here/rc.scp" ] && rc="$(tr -d '[:space:]' < "$here/rc.scp")"
if [ "$rc" != "0" ]; then echo "scp: lost connection" >&2; exit "$rc"; fi
src=""; dest=""
for a in "$@"; do
  case "$a" in
  -*) ;;
  *) if [ -z "$src" ]; then src="$a"; else dest="$a"; fi ;;
  esac
done
case "$src" in
*:*) # 远端源 → dest 本机路径：造一份 netscape cookie（本地 src 是上传不写）
  if [ -n "$dest" ]; then
    printf '# Netscape HTTP Cookie File\\n' > "$dest"
    printf '.bilibili.com\\tTRUE\\t/\\tFALSE\\t1999999999\\tSESSDATA\\tstub-sess\\n' >> "$dest"
    printf '.bilibili.com\\tTRUE\\t/\\tFALSE\\t1999999999\\tbili_jct\\tstub-jct\\n' >> "$dest"
  fi
  ;;
esac
exit 0
"""

CURL_STUB = """#!/bin/bash
here="$(cd "$(dirname "$0")" && pwd)"
echo "curl $*" >> "$here/curl.log"
rc=0
[ -f "$here/rc.curl" ] && rc="$(tr -d '[:space:]' < "$here/rc.curl")"
[ "$rc" != "0" ] && exit "$rc"
mode="$(tr -d '[:space:]' < "$here/nav.mode" 2>/dev/null || echo login)"
case "$mode" in
logout) printf '{"code":0,"data":{"isLogin":false,"uname":""}}' ;;
challenge) printf '{"code":-412,"data":{"isLogin":false,"uname":""}}' ;;
garbage) printf '<html>intercepted</html>' ;;
*) printf '{"code":0,"data":{"isLogin":true,"uname":"stub-fan"}}' ;;
esac
exit 0
"""

# monolith 臂 stub connector：<url> -o <adir> → 落 out.md；rc.conn 控错
CONN_STUB = """#!/bin/bash
here="$(cd "$(dirname "$0")" && pwd)"
echo "bilibili-get $*" >> "$here/conn.log"
rc=0
[ -f "$here/rc.conn" ] && rc="$(tr -d '[:space:]' < "$here/rc.conn")"
if [ "$rc" != "0" ]; then echo "conn fail rc=$rc" >&2; exit "$rc"; fi
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then
    mkdir -p "$a"; printf 'stub subs artifact\\n' > "$a/out.md"
  fi
  prev="$a"
done
printf 'stub bilibili-get out\\n'
exit 0
"""


@pytest.fixture
def bfix(tmp_path):
    pdir = tmp_path / "packs" / "bilibili"
    pdir.mkdir(parents=True)
    (pdir / "pack.toml").write_text(PACK_TOML.read_text(encoding="utf-8"))
    shutil.copy(PROBE, pdir / "probe.sh")
    # 原生 lane 以 pack.toml 相对路径解析——真 lanes/ 目录软链进来
    # （bili_mint 的 __file__ resolve 穿过软链 → 真 scripts/refresh-cookies.sh）
    os.symlink(ROOT / "packs" / "bilibili" / "lanes", pdir / "lanes")
    # monolith connector 与 probe.sh 的 ../../scripts 相对位 → 真脚本+stub 摆进 tmp 树
    sdir = tmp_path / "scripts"
    (sdir / "connectors").mkdir(parents=True)
    shutil.copy(REFRESH, sdir / "refresh-cookies.sh")
    conn = sdir / "connectors" / "bilibili-get"
    conn.write_text(CONN_STUB)
    conn.chmod(0o755)
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    for name, body in (("ssh", SSH_STUB), ("scp", SCP_STUB), ("curl", CURL_STUB)):
        t = bindir / name
        t.write_text(body)
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
            "PATH": str(bindir) + os.pathsep + env["PATH"],
        }
    )
    env.pop("COOKIE_HOST", None)
    env.pop("REFRESH_COOKIES", None)
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


def _identity_key(decs):
    for d in decs:
        if d.get("stage") == "identity" and "key" in d:
            return d["key"]
    return None


def _conndir(tmp_path):
    return tmp_path / "scripts" / "connectors"


def run_mint(env, extra=None):
    return run_engine(
        ["run", BVID_URL, "-p", "bilibili", "--param", "kind=mint"]
        + (extra or [])
        + ["--json"],
        env,
    )


# ------------------------------------------------------- mint kind 路由独占


def test_mint_kind_routes_only_to_mint_lane(bfix):
    """kind=mint → routes 首臂命中 → 只有 bili_mint；stub connector 零调用——
    THE TRAP 回归断言：mint 请求永不落真抓取臂。"""
    bindir, env, tmp = bfix
    p = run_mint(env)
    assert p.returncode == 0, (p.returncode, p.stderr, p.stdout)
    env_ = _envelope(p)
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["bili_mint"]]
    assert _identity_key(decs) == MINT_KEY
    assert env_["data"], env_
    assert not (_conndir(tmp) / "conn.log").exists()  # 抓取臂从未被 spawn


def test_mint_success_writes_cred_files(bfix):
    """mint 成功：真 refresh-cookies.sh bilibili 臂 e2e——bilibili.txt +
    BBDown.data 落 tmp HOME 预期凭证路径，600 权限，netscape → cookie 头
    重写；data payload 报文件证据 + isLogin/uname。"""
    bindir, env, tmp = bfix
    p = run_mint(env)
    assert p.returncode == 0, (p.returncode, p.stderr)
    env_ = _envelope(p)
    payload = env_["data"]
    assert isinstance(payload, dict)
    home = Path(env["HOME"])
    txt = home / ".config/link-get/cookies/bilibili.txt"
    bb = home / "BBDown.data"
    assert txt.is_file()
    assert bb.is_file()
    assert (txt.stat().st_mode & 0o777) == 0o600
    assert (bb.stat().st_mode & 0o777) == 0o600
    # stub scp 造的 netscape 经脚本内 python 重写成 cookie 头串
    assert "SESSDATA=stub-sess" in bb.read_text()
    assert "bili_jct=stub-jct" in bb.read_text()
    minted = payload["minted"]
    assert minted["bilibili_txt"]["path"] == str(txt)
    assert minted["bbdown_data"]["path"] == str(bb)
    assert minted["bilibili_txt"]["bytes"] == txt.stat().st_size
    assert payload["isLogin"] == "True"
    assert payload["uname"] == "stub-fan"


def test_mint_ssh_unreachable_dep_absent(bfix):
    """ssh 探针 rc255（timeout）→ dep_absent：链路缺位不记账、不打内容键；
    脚本从未运行，凭证文件不存在。"""
    bindir, env, tmp = bfix
    (bindir / "rc.ssh").write_text("255")
    p = run_mint(env)
    assert p.returncode == 5, (p.returncode, p.stderr)
    env_ = _envelope(p)
    assert env_["class"] == "dep_absent"
    home = Path(env["HOME"])
    assert not (home / ".config/link-get/cookies/bilibili.txt").exists()
    # 探针一次调用即止——不 hammer（ssh 循环是禁项）
    assert (bindir / "ssh.log").read_text().count("ssh ") == 1


def test_mint_ssh_denied_needs_human(bfix):
    """ssh permission denied → dep_absent + needs_human：密钥/agent 要人修。"""
    bindir, env, _ = bfix
    (bindir / "rc.ssh").write_text("255")
    (bindir / "ssh.mode").write_text("denied")
    p = run_mint(env)
    assert p.returncode == 5, (p.returncode, p.stderr)
    assert _envelope(p)["class"] == "dep_absent"
    assert "needs human intervention" in p.stderr


def test_mint_islogin_false_auth_expired(bfix):
    """铸出但未登录（nav isLogin:false）→ auth_expired + needs_human；
    cred8 域账：lane probe 即见 scoped 冷却（同 cookie 期间不 hammer remint）。"""
    bindir, env, _ = bfix
    (bindir / "nav.mode").write_text("logout")
    p = run_mint(env)
    assert p.returncode == 6, (p.returncode, p.stderr)
    assert _envelope(p)["class"] == "auth_expired"
    assert "needs human intervention" in p.stderr
    lp = lgc(["lane", NS, "probe", "bili_mint", MINT_KEY], env)
    assert lp.returncode == 1, (lp.returncode, lp.stdout, lp.stderr)
    # 冷却中立刻 remint → 无 runnable → dep_absent（防 hammer 语义）
    p2 = run_mint(env)
    assert p2.returncode == 5
    assert _envelope(p2)["class"] == "dep_absent"


def test_mint_challenge_class(bfix):
    """上游风控码（-412）→ challenge_needed + needs_human。"""
    bindir, env, _ = bfix
    (bindir / "nav.mode").write_text("challenge")
    p = run_mint(env)
    assert p.returncode == 6, (p.returncode, p.stderr)
    assert _envelope(p)["class"] == "challenge_needed"


def test_mint_transient_fail_note_off(bfix):
    """fail_note=false 实锤回归：scp 断链 → transient，但 lane×key 不上账——
    probe 仍通，紧接 remint 不被 cooling 卡成 dep_absent（死循环陷阱）。"""
    bindir, env, _ = bfix
    (bindir / "rc.scp").write_text("1")
    p = run_mint(env)
    assert p.returncode == 5, (p.returncode, p.stderr)
    assert _envelope(p)["class"] == "transient"
    lp = lgc(["lane", NS, "probe", "bili_mint", MINT_KEY], env)
    assert lp.returncode == 0, (lp.returncode, lp.stdout, lp.stderr)
    (bindir / "rc.scp").unlink()
    p2 = run_mint(env)
    assert p2.returncode == 0, (p2.returncode, p2.stderr)


def test_mint_param_catchall_no_kind(bfix):
    """裸 --param mint（不带 kind 覆盖）→ routes params={mint=true} 兜底臂
    仍锁 bili_mint——mint 意图永不落抓取臂（残留边沿仅同键已存时供缓存，
    不跑 connector——pack.toml routes 注记）。"""
    bindir, env, tmp = bfix
    p = run_engine(
        ["run", BVID_URL, "-p", "bilibili", "--param", "mint", "--json"], env
    )
    assert p.returncode == 0, (p.returncode, p.stderr, p.stdout)
    env_ = _envelope(p)
    assert env_["data"], env_  # data 终态而非 items——铸了
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["bili_mint"]]
    assert _identity_key(decs) == "bili:subs:BV1xx411c7mD:p1"
    assert not (_conndir(tmp) / "conn.log").exists()


def test_mint_kind_never_serves_cached_subs(bfix):
    """kind=mint 正道：同 URL 的 subs 内容键已存 → 仍跑 mint（mint 键宇宙
    与内容键正交，探测永不 hit）——THE TRAP 的缓存变体断言。"""
    bindir, env, tmp = bfix
    fake = tmp / "seed.md"
    fake.write_text("seeded content")
    put = lgc(
        [
            "put",
            NS,
            "bili:subs:BV1xx411c7mD:p1",
            "--files",
            str(fake),
            "--lane",
            "x",
        ],
        env,
    )
    assert put.returncode == 0, (put.returncode, put.stdout, put.stderr)
    p = run_mint(env)
    assert p.returncode == 0, (p.returncode, p.stderr, p.stdout)
    env_ = _envelope(p)
    assert env_["data"], env_
    assert _route_lanes(_decisions(env_)) == [["bili_mint"]]
    assert not (_conndir(tmp) / "conn.log").exists()


def test_fetch_arm_unaffected(bfix):
    """无 mint 的常规请求 → subs kind → bilibili-get monolith 臂照常跑：
    既有抓取能力不受 routes 重排影响。"""
    bindir, env, tmp = bfix
    p = run_engine(["run", BVID_URL, "-p", "bilibili", "--json"], env)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    env_ = _envelope(p)
    decs = _decisions(env_)
    assert _route_lanes(decs) == [["bilibili-get"]]
    assert env_["items"], env_
    calls = (_conndir(tmp) / "conn.log").read_text()
    assert "-o" in calls


def test_params_gate_still_enforced(bfix):
    """[params] 闸仍在：未声明 param → rc2 拒（mint 已声明不受影响）。"""
    bindir, env, _ = bfix
    p = run_engine(
        ["run", BVID_URL, "-p", "bilibili", "--param", "bogus=1", "--json"], env
    )
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "bogus" in p.stderr


# ------------------------------------------------------- 壳分发 + 体检


@pytest.fixture
def lrig(tmp_path):
    """link-get 分发 rig（test_link_get 同款最小树）。"""
    sdir = tmp_path / "scripts"
    conn = sdir / "connectors"
    conn.mkdir(parents=True)
    lg = sdir / "link-get"
    shutil.copy(LINK_GET, lg)
    lg.chmod(0o755)
    for name in ("_common.sh", "_lgc.sh"):
        shutil.copy(ROOT / "scripts" / "connectors" / name, conn / name)
    eng = sdir / "fetch-engine"
    eng.write_text(
        '#!/bin/bash\n{ echo "fetch-engine"; printf \'%s\\n\' "$@"; } >> "$MOCK_OUT"\n'
    )
    eng.chmod(0o755)
    env = dict(os.environ)
    env["MOCK_OUT"] = str(tmp_path / "calls.txt")
    return lg, env, tmp_path


def test_link_get_mint_dispatch(lrig):
    """link-get --mint <bili-url> → engine --param mint + --param kind=mint
    （canvas --mint→kind=enum 平价：kind 覆盖经 param 表达）。"""
    lg, env, tmp = lrig
    r = subprocess.run(
        [str(lg), "--mint", BVID_URL],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert r.returncode == 0, (r.returncode, r.stderr)
    calls = Path(env["MOCK_OUT"]).read_text().splitlines()
    assert calls[0] == "fetch-engine"
    assert calls[1:3] == ["run", BVID_URL]
    assert (
        "-p" not in calls
    )  # 壳不选 pack——kind=mint 注入仍是壳契约；pack 归 engine [match]
    assert "--param" in calls
    assert "mint" in calls
    assert "kind=mint" in calls


def test_selftest_pack_bilibili(bfix):
    """selftest -p bilibili：lane exec 可解析、needs 工具齐、routes 覆盖
    全 kind、cred_domain/writes_cred=bili 合法、probe.sh rc0（ssh stub 可达，
    cookie 缺席只 advisory 不计 fail）。"""
    bindir, env, _ = bfix
    p = subprocess.run(
        [sys.executable, str(ENGINE), "selftest", "-p", "bilibili"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert "routes 覆盖全部 3 kind" in p.stdout
    assert "writes_cred" in p.stdout
    assert "bili" in p.stdout
