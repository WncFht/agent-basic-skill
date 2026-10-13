# test_bilibili_get.py — bilibili-get connector regressions. Run:
#   TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests/test_bilibili_get.py -x -q
# Offline: yt-dlp/BBDown/curl/lgc are all PATH/env stubs. Temp dirs land
# under $HOME/.cache (never /tmp — tmpfs is full).

import glob
import json
import os
import shutil
import subprocess
import tempfile
import time

import pytest

CONN = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "connectors", "bilibili-get"
)
TMPBASE = os.path.expanduser("~/.cache")

# lgc `has` caps line：覆盖 z_* 全部 cap 查询（flag-veto 缺 cap 会整条 no-op）
LGC_CAPS = (
    "get put neg cat lane key list into wait satisfies claim json "
    "atomic keep-flag producer params owner-pid cred value from ttl "
    "delguard denylist breaker"
)

LGC_STUB = """#!/bin/bash
# lgc stub：记录全部 argv；get 恒 miss；put/lane 的 rc 由 env 控制；
# cat 吐 $LGC_STUB_CAT（b23 值缓存毒化注入用）
printf '%s\\n' "$*" >>"$LGC_STUB_LOG"
case "$1" in
has)
  printf 'lgc 1.0\\n%s\\n' "$LGC_STUB_CAPS"
  exit 0
  ;;
get)
  printf 'cache: miss\\n'
  exit "${LGC_STUB_GET_RC:-1}"
  ;;
put)
  exit "${LGC_STUB_PUT_RC:-0}"
  ;;
cat)
  printf '%s' "$LGC_STUB_CAT"
  exit "${LGC_STUB_CAT_RC:-0}"
  ;;
*)
  exit 0
  ;;
esac
"""

YTDLP_STUB = """#!/bin/bash
# -J/--dump-json → 单行 meta；--write-subs → 静默成功但不出 srt（逼进 BBDown 兜底）
for _a in "$@"; do
  case "$_a" in
  -J | --dump-json)
    printf '{"title":"Stub BV"}\\n'
    exit 0
    ;;
  esac
done
exit 0
"""

BBDOWN_STUB = """#!/bin/bash
# 记录 cwd 与其权限位 + 预置凭证首行 + 原始 argv；在 --work-dir 落 BBDown.data 与假字幕
_wd="$PWD"
_args="$*"
while [ $# -gt 0 ]; do
  case "$1" in
  --work-dir)
    _wd="$2"
    shift 2
    ;;
  *) shift ;;
  esac
done
{
  pwd
  stat -c '%a' . 2>/dev/null || stat -f '%Lp' .
  if [ -f "$_wd/BBDown.data" ]; then
    printf 'precopied\\n'
    head -1 "$_wd/BBDown.data"
  fi
  printf 'argv:%s\\n' "$_args"
} >>"$BILI_STUB_LOG" 2>&1
mkdir -p "$_wd"
printf 'DUMMY-CRED\\n' >"$_wd/BBDown.data"
printf '1\\n00:00:00,000 --> 00:00:01,000\\nstub\\n' >"$_wd/stub.zh.srt"
exit 0
"""

BBDOWN_FAIL_STUB = """#!/bin/bash
# 无字幕产出即失败：逼连接器走「无轨」优雅路径且不触真实 BBDown
exit 1
"""

CURL_STUB = """#!/bin/bash
# CURL_STUB_MODE=ok → stdout 给 $CURL_STUB_BODY；否则 rc6 空输出（瞬时故障）
case "${CURL_STUB_MODE:-fail}" in
ok)
  printf '%s' "$CURL_STUB_BODY"
  exit 0
  ;;
*)
  exit 6
  ;;
esac
"""

CURL_B23_STUB = """#!/bin/bash
# b23 解析调用（-w %{url_effective}）→ stdout 给 $CURL_STUB_REDIRECT；
# 其余调用（opus API 等）→ stdout 给 $CURL_STUB_BODY。MODE!=ok → rc6。
_seen_w=""
for _a in "$@"; do
  case "$_a" in
  *url_effective*) _seen_w=1 ;;
  esac
done
if [ "${CURL_STUB_MODE:-fail}" != ok ]; then
  exit 6
fi
if [ -n "$_seen_w" ]; then
  printf '%s' "$CURL_STUB_REDIRECT"
else
  printf '%s' "$CURL_STUB_BODY"
fi
exit 0
"""

RM_STUB = """#!/bin/bash
# rm 全线失败——死卫测试：清理性 rm -rf 不得杀死脚本
printf 'rm %s\\n' "$*" >>"$RM_STUB_LOG"
exit 1
"""

# 最小 PATH 构造：除 drop 列出的工具外全部符号链接进 minbin——
# 模拟 stock macOS 无 GNU timeout / BBDown 缺席这类 dep-absent 环境
BASE_TOOLS = [
    "bash",
    "find",
    "grep",
    "sed",
    "head",
    "tail",
    "ls",
    "tr",
    "basename",
    "dirname",
    "mkdir",
    "rm",
    "mv",
    "cp",
    "chmod",
    "python3",
    "stat",
    "sleep",
    "cat",
    "awk",
    "cksum",
    "readlink",
    "timeout",
]


def restrict_path(e, home, stub, drop=()):
    """PATH := stub 目录 + minbin（BASE_TOOLS 去掉 drop 的符号链接）。"""
    minbin = os.path.join(home, "minbin")
    os.makedirs(minbin, exist_ok=True)
    for tool in BASE_TOOLS:
        if tool in drop:
            continue
        src = shutil.which(tool)
        assert src, f"测试机缺 {tool}"
        dst = os.path.join(minbin, tool)
        if not os.path.exists(dst):
            os.symlink(src, dst)
    e["PATH"] = stub + os.pathsep + minbin


OPUS_JSON = json.dumps(
    {
        "code": 0,
        "data": {
            "item": {
                "basic": {"comment_id_str": "1"},
                "modules": {
                    "module_dynamic": {
                        "major": {
                            "opus": {
                                "title": "stub opus",
                                "summary": {"text": "正文 stub"},
                            }
                        }
                    }
                },
            }
        },
    }
)


@pytest.fixture
def env():
    home = tempfile.mkdtemp(prefix="biliget-test-", dir=TMPBASE)
    stub = os.path.join(home, "bin")
    out = os.path.join(home, "out")
    os.makedirs(stub)
    os.makedirs(out)
    e = dict(os.environ)
    e["HOME"] = home  # bbdir 应落在 fake $HOME/.cache 下
    e["PATH"] = stub + os.pathsep + e["PATH"]
    e.pop("LGC_OFF", None)
    e.pop("LGC_REFRESH", None)
    e.pop("LGC_CAPS", None)
    e["BILI_STUB_LOG"] = os.path.join(home, "bbdown.log")
    e["LGC_STUB_LOG"] = os.path.join(home, "lgc.log")
    e["LGC_STUB_CAPS"] = LGC_CAPS
    e["LGC_BIN"] = os.path.join(stub, "lgc")
    yield e, home, stub, out
    shutil.rmtree(home, ignore_errors=True)


def put_stub(stubdir, name, body):
    p = os.path.join(stubdir, name)
    with open(p, "w") as f:
        f.write(body)
    os.chmod(p, 0o755)
    return p


def run_conn(e, url, out, cwd=None):
    return subprocess.run(
        ["bash", CONN, url, "-o", out],
        env=e,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )


def test_bbdown_data_never_lands_in_out(env):
    """凭证卫生：BBDown work-dir 必须是 0700 的 ~/.cache 固定目录；
    $OUT（含 .lgc-stage-* staging）全程不得出现 BBDown.data。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"
    # 预置登录态：应对齐 media-get 拷入 work-dir 复用
    with open(os.path.join(home, "BBDown.data"), "w") as f:
        f.write("SESSDATA=fake\n")

    r = run_conn(e, "https://www.bilibili.com/video/BV1stub23456", out)
    assert r.returncode == 0, r.stderr

    # 产物区无凭证文件，staging 已清理
    for dp, _dn, fns in os.walk(out):
        assert "BBDown.data" not in fns
    assert not glob.glob(os.path.join(out, ".lgc-stage-*"))

    # BBDown 确实跑了，且 cwd 是 0700 的固定缓存目录
    with open(e["BILI_STUB_LOG"]) as f:
        lines = f.read().splitlines()
    assert lines, "BBDown stub 未被调用"
    bbdir = lines[0]
    assert bbdir.startswith(
        os.path.join(home, ".cache", "link-get", "tmp", "bbdown-")
    ), bbdir
    assert lines[1] == "700", lines
    assert "precopied" in lines  # ~/BBDown.data 被复用而非新建匿名态

    # 兜底字幕照常收编；用完的 work-dir 已删（凭证不滞留）
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))
    assert not glob.glob(os.path.join(home, ".cache", "link-get", "tmp", "bbdown-*"))


def test_opus_transient_failure_writes_no_tombstone(env):
    """opus curl/API 瞬时失败：只记车道账（lane fail+note），
    绝不写内容级 neg 墓碑（与 transient 政策一致）。"""
    e, home, stub, out = env
    put_stub(stub, "lgc", LGC_STUB)
    put_stub(stub, "curl", CURL_STUB)
    e["CURL_STUB_MODE"] = "fail"

    r = run_conn(e, "https://www.bilibili.com/opus/1234567890", out)
    assert r.returncode == 5, r.stderr

    with open(e["LGC_STUB_LOG"]) as f:
        log = f.read().splitlines()
    assert any(line.startswith("lane link-get fail bili-api") for line in log), log
    assert any(
        line.startswith("lane link-get note bili-api") and "lane-fail" in line
        for line in log
    ), log
    # 内容键墓碑缺席：没有任何 `lgc neg ...` 调用
    assert not any(line.startswith("neg ") for line in log), log


def test_opus_deleted_still_writes_tombstone(env):
    """对照组：delguard 拒收（put rc4 → ZDEL=1）= 内容级删除证据，
    仍要写 deleted 内容墓碑并 exit4。"""
    e, home, stub, out = env
    put_stub(stub, "lgc", LGC_STUB)
    put_stub(stub, "curl", CURL_STUB)
    e["CURL_STUB_MODE"] = "ok"
    e["CURL_STUB_BODY"] = OPUS_JSON
    e["LGC_STUB_PUT_RC"] = "4"  # delguard 命中删除签名

    r = run_conn(e, "https://www.bilibili.com/opus/1234567890", out)
    assert r.returncode == 4, r.stderr

    with open(e["LGC_STUB_LOG"]) as f:
        log = f.read().splitlines()
    assert any(
        line.startswith("neg link-get bili:opus:1234567890") and "deleted" in line
        for line in log
    ), log


def test_non_bv_urls_hit_graceful_notrack(env):
    """bangumi/space 等非 BV 链接：BVID 解不出不得 rc1 静默猝死（pipefail 死卫）——
    D3 空键 graceful 走到底，meta 在但无轨 → exit3 交视频管线。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_FAIL_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"

    for url in (
        "https://www.bilibili.com/bangumi/play/ep123456",
        "https://space.bilibili.com/123456",
    ):
        r = run_conn(e, url, out)
        assert r.returncode == 3, (url, r.returncode, r.stderr)
        assert "无字幕轨" in r.stderr


def test_b23_curl_failure_exit5(env):
    """b23.tv 短链 curl 解析失败 → 明确 stderr + exit5（瞬时故障），
    不得被 pipefail 拧成 rc1 静默猝死。"""
    e, home, stub, out = env
    put_stub(stub, "curl", CURL_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["CURL_STUB_MODE"] = "fail"
    e["LGC_OFF"] = "1"

    r = run_conn(e, "https://b23.tv/abc123", out)
    assert r.returncode == 5, (r.returncode, r.stderr)
    assert "解析失败" in r.stderr


def test_stale_bbdir_precleaned_on_pid_reuse(env):
    """PID 复用毒化：bbdown-$$ 撞名 SIGKILL 孤儿目录时，陈旧 .srt 不得进收编、
    陈旧 BBDown.data 不得赢过 precopy 守卫（先 rm -rf 再 mkdir）。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"
    # 新鲜凭证放家目录——预清后 precopy 应拿到它而非陈旧凭证
    with open(os.path.join(home, "BBDown.data"), "w") as f:
        f.write("SESSDATA=fresh\n")

    # bash -c + exec 保 pid：shim 按自身 $$ 预植陈旧 bbdir，连接器 bbdown-$$ 正撞名
    shim = (
        'd="$HOME/.cache/link-get/tmp/bbdown-$$";'
        'mkdir -p "$d";'
        'printf "1\\n00:00:00,000 --> 00:00:01,000\\nSTALE\\n" >"$d/stale.zh.srt";'
        'printf "STALE-CRED\\n" >"$d/BBDown.data";'
        'exec bash "$0" "$@"'
    )
    r = subprocess.run(
        [
            "bash",
            "-c",
            shim,
            CONN,
            "https://www.bilibili.com/video/BV1stub23456",
            "-o",
            out,
        ],
        env=e,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=home,  # ./BBDown.data 也指向家目录新鲜凭证
    )
    assert r.returncode == 0, r.stderr

    # 陈旧 .srt 未收编，新鲜 stub 字幕照常落地
    assert not os.path.exists(os.path.join(out, "stale.zh.srt"))
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))

    with open(e["BILI_STUB_LOG"]) as f:
        lines = f.read().splitlines()
    assert "STALE-CRED" not in lines  # 陈旧凭证被 rm -rf 清掉，没赢
    assert "SESSDATA=fresh" in lines  # precopy 拿到的是新鲜凭证


def test_bbdown_env_cookie_fallback(env):
    """BBDown.data 缺席时 BILI_SESSDATA/BILI_JCT/BILI_BUVID3 拼成 -c cookie
    传给 BBDown（对齐 media-get env-cookie 兜底）。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"
    e["BILI_SESSDATA"] = "sess-x"
    e["BILI_JCT"] = "jct-y"
    e["BILI_BUVID3"] = "buv-z"

    r = run_conn(e, "https://www.bilibili.com/video/BV1stub23456", out, cwd=home)
    assert r.returncode == 0, r.stderr

    with open(e["BILI_STUB_LOG"]) as f:
        lines = f.read().splitlines()
    assert "precopied" not in lines  # 无任何 BBDown.data 可预拷
    argv = next((line for line in lines if line.startswith("argv:")), "")
    assert "-c SESSDATA=sess-x;bili_jct=jct-y;buvid3=buv-z" in argv, argv


def test_stale_stage_dirs_swept(env):
    """>1h 的 .lgc-stage-*（SIGKILL 遗留，可能藏 BBDown.data）起跑即清扫；
    新鲜 staging 不误伤。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_FAIL_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"

    old = os.path.join(out, ".lgc-stage-111")
    fresh = os.path.join(out, ".lgc-stage-222")
    os.makedirs(old)
    os.makedirs(fresh)
    with open(os.path.join(old, "BBDown.data"), "w") as f:
        f.write("STALE-CRED")
    past = time.time() - 3700
    os.utime(old, (past, past))

    r = run_conn(e, "https://www.bilibili.com/video/BV1stub23456", out)
    assert r.returncode == 3, r.stderr  # 双挂 → notrack，流程不受清扫影响
    assert not os.path.exists(old)
    assert os.path.isdir(fresh)


def test_entry_url_guard(env):
    """入口 TARGET 先过 _guard_url：非 http(s)/回环/私网/伪 host 一律 rc2 拒于
    probe 与车道之前——闸后任何 lgc get 都说明漏了。"""
    e, home, stub, out = env
    put_stub(stub, "lgc", LGC_STUB)  # LGC 开着：若闸漏了能在 log 里看到 get

    for url in (
        "http://127.0.0.1:9/ssrf",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/x",
        "file:///etc/passwd",
        "ftp://www.bilibili.com/video/BV1stub23456",
    ):
        r = run_conn(e, url, out)
        assert r.returncode == 2, (url, r.returncode, r.stderr)
        assert "ssrf-guard" in r.stderr, (url, r.stderr)

    if os.path.exists(e["LGC_STUB_LOG"]):
        with open(e["LGC_STUB_LOG"]) as f:
            assert "get " not in f.read()


def test_b23_resolved_url_re_guarded(env):
    """b23 curl 解析的终态 URL 采纳前重过 _guard_url + authority 锚定白名单：
    私网字面/非 bilibili 域一律 rc2 拒收，且不过白名单的终态不落 30d 值缓存。"""
    e, home, stub, out = env
    put_stub(stub, "curl", CURL_B23_STUB)
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["CURL_STUB_MODE"] = "ok"

    for evil in (
        "http://169.254.169.254/latest/meta-data",  # SSRF：_guard_url 拒
        "https://notbilibili.com/video/BV1stub23456",  # 旧子串 glob 会误收
        "https://evil.com/?next=bilibili.com/video/BV1",  # query 藏白名单子串
    ):
        e["CURL_STUB_REDIRECT"] = evil
        r = run_conn(e, "https://b23.tv/abc123", out)
        assert r.returncode == 2, (evil, r.returncode, r.stderr)

    with open(e["LGC_STUB_LOG"]) as f:
        log = f.read().splitlines()
    assert not any("--value" in line for line in log), log  # 恶值不入缓存


def test_b23_cached_value_re_guarded(env):
    """lgc-cat 值缓存可被写任意串：读端采纳前同样过双闸——
    毒化 value（回环 SSRF / 非白名单公网域）→ rc2 拒收，不触 curl。"""
    e, home, stub, out = env
    put_stub(stub, "lgc", LGC_STUB)
    put_stub(stub, "curl", CURL_B23_STUB)  # 缓存命中短路——不应被调到
    e["CURL_STUB_MODE"] = "ok"

    for poison in (
        "http://127.0.0.1:9/ssrf",
        "https://evil.com/bilibili.com/video/BV1",
    ):
        e["LGC_STUB_CAT"] = poison
        r = run_conn(e, "https://b23.tv/abc123", out)
        assert r.returncode == 2, (poison, r.returncode, r.stderr)


def test_b23_resolved_adopted_after_recheck(env):
    """对照组：合法 bilibili 终态过双闸采纳为 TARGET 且入 30d 值缓存，
    字幕链照常产出。"""
    e, home, stub, out = env
    put_stub(stub, "curl", CURL_B23_STUB)
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["CURL_STUB_MODE"] = "ok"
    e["CURL_STUB_REDIRECT"] = "https://www.bilibili.com/video/BV1stub23456"

    r = run_conn(e, "https://b23.tv/abc123", out)
    assert r.returncode == 0, r.stderr
    assert "解析为 https://www.bilibili.com/video/BV1stub23456" in r.stderr
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))

    with open(e["LGC_STUB_LOG"]) as f:
        log = f.read().splitlines()
    assert any(
        line.startswith("put link-get bili:b23:abc123")
        and "--value" in line
        and "www.bilibili.com/video/BV1stub23456" in line
        for line in log
    ), log


def test_opus_branch_anchored_not_substring(env):
    """opus 分流锚定 authority/path：video URL 的 query 含 opus/t.bilibili.com
    子串不再误入 opus 分支（旧 grep 子串 → rc2「解不出动态 id」猝死）。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"

    for url in (
        "https://www.bilibili.com/video/BV1stub23456?foo=opus",
        "https://www.bilibili.com/video/BV1stub23456/?u=t.bilibili.com",
    ):
        r = run_conn(e, url, out)
        assert r.returncode == 0, (url, r.returncode, r.stderr)
        assert "解不出动态 id" not in r.stderr

    # 对照：真 /opus/ 与 t.bilibili.com 主机仍走动态分支
    put_stub(stub, "curl", CURL_STUB)
    e["CURL_STUB_MODE"] = "ok"
    e["CURL_STUB_BODY"] = OPUS_JSON
    for url in (
        "https://www.bilibili.com/opus/1234567890",
        "https://t.bilibili.com/1234567890",
    ):
        r = run_conn(e, url, out)
        assert r.returncode == 0, (url, r.returncode, r.stderr)
        assert os.path.isfile(os.path.join(out, "opus-1234567890.md"))


def test_fresh_stage_dir_precleaned(env):
    """同 PID 新鲜 .lgc-stage-$$（SIGKILL 孤儿，<1h 清扫网漏）：mkdir 前无条件
    rm -rf——陈旧 .srt 不得混进本轮收编。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"

    shim = (
        'd="$3/.lgc-stage-$$";'
        'mkdir -p "$d";'
        'printf "1\\n00:00:00,000 --> 00:00:01,000\\nSTALE\\n"'
        ' >"$d/stale--BV1stub23456_p1.zh.srt";'
        'exec bash "$0" "$@"'
    )
    r = subprocess.run(
        [
            "bash",
            "-c",
            shim,
            CONN,
            "https://www.bilibili.com/video/BV1stub23456",
            "-o",
            out,
        ],
        env=e,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))
    assert not glob.glob(os.path.join(out, "*stale*"))


def test_stage_symlink_escape_neutralized(env):
    """.lgc-stage-$$ 是软链 → 预清拆链重建真目录：不得沿链读陈旧 .srt
    进收编，也不得沿链把 yt-dlp 产物写进目标目录。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_FAIL_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"
    evil = os.path.join(home, "evil-target")
    os.makedirs(evil)
    with open(os.path.join(evil, "evil.zh.srt"), "w") as f:
        f.write("1\n00:00:00,000 --> 00:00:01,000\nEVIL\n")

    shim = 'ln -s "$4" "$3/.lgc-stage-$$";exec bash "$0" "$@"'
    r = subprocess.run(
        [
            "bash",
            "-c",
            shim,
            CONN,
            "https://www.bilibili.com/video/BV1stub23456",
            "-o",
            out,
            evil,
        ],
        env=e,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 3, (r.returncode, r.stderr)  # 双挂 → notrack 正常走
    assert os.path.isfile(os.path.join(evil, "evil.zh.srt"))  # 目标未被掏空
    assert not os.path.exists(os.path.join(out, "evil.zh.srt"))


def test_stage_nondir_collision_recovered(env):
    """.lgc-stage-$$ 撞名普通文件 → 预清后 mkdir 照常，不得 rc1 静默猝死。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"

    shim = 'printf x >"$3/.lgc-stage-$$";exec bash "$0" "$@"'
    r = subprocess.run(
        [
            "bash",
            "-c",
            shim,
            CONN,
            "https://www.bilibili.com/video/BV1stub23456",
            "-o",
            out,
        ],
        env=e,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))


def test_rm_failure_never_kills(env):
    """清理性 rm -rf 全线失败也只 warn 继续：兜底前/产物交付后都不得
    因 rm rc1 静默猝死。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    put_stub(stub, "rm", RM_STUB)
    e["LGC_OFF"] = "1"
    e["RM_STUB_LOG"] = os.path.join(home, "rm.log")

    r = run_conn(e, "https://www.bilibili.com/video/BV1stub23456", out)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))
    with open(e["RM_STUB_LOG"]) as f:
        assert "rm" in f.read()  # rm 确实被叫过且全失败了


def test_bbdown_runs_without_gnu_timeout(env):
    """stock macOS 无 GNU timeout：PATH 缺席 timeout 时 BBDown 降级裸跑照常
    兜底——旧代码 timeout rc127 被 || true 吞成零产出，还白计 lane-fail。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)
    put_stub(stub, "BBDown", BBDOWN_STUB)
    put_stub(stub, "lgc", LGC_STUB)
    e["LGC_OFF"] = "1"
    restrict_path(e, home, stub, drop=("timeout",))
    assert shutil.which("timeout", path=e["PATH"]) is None

    r = run_conn(e, "https://www.bilibili.com/video/BV1stub23456", out)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert os.path.isfile(os.path.join(out, "stub.zh.srt"))
    with open(e["BILI_STUB_LOG"]) as f:
        assert f.read().splitlines()  # BBDown 真被拉起


def test_bbdown_absent_never_writes_notrack(env):
    """BBDown dep-absent：meta 证零轨也不落 notrack 内容墓碑（AI 字幕未取证），
    按 transient exit5 记账——yt-dlp 车道账照记，bbdown 不计。"""
    e, home, stub, out = env
    put_stub(stub, "yt-dlp", YTDLP_STUB)  # meta 零轨证据
    put_stub(stub, "lgc", LGC_STUB)
    # 不放 BBDown stub 且 PATH 收编到 minbin：真 BBDown 也探不到
    restrict_path(e, home, stub)
    assert shutil.which("BBDown", path=e["PATH"]) is None

    r = run_conn(e, "https://www.bilibili.com/video/BV1stub23456", out)
    assert r.returncode == 5, (r.returncode, r.stderr)

    with open(e["LGC_STUB_LOG"]) as f:
        log = f.read().splitlines()
    assert not any(line.startswith("neg ") for line in log), log
    assert any(line.startswith("lane link-get fail yt-dlp") for line in log), log
    assert not any(line.startswith("lane link-get fail bbdown") for line in log), log
