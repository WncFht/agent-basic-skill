"""test_zhihu_lanes.py — zhihu pack native lanes (zhcli_lane / scraper_lane) 离线自测。

无真实外网：fake `zhihu` / `uvx` / `zhihu-scraper` 放 tmp bin 目录上 PATH，
emit canned 文件 + 可控 rc/stderr；断言 lane stdout JSONL 纯净、恰一个终态行、
分类正确、产物在 artifact_dir 内、rc10 静默跳过路径。
"""

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

LANES = Path(__file__).resolve().parent.parent / "packs" / "zhihu" / "lanes"
ZHCLI = LANES / "zhcli_lane.py"
SCRAPER = LANES / "scraper_lane.py"

# fake zhihu-cli：`download <mode> <url> -o <dir>`；行为由 FAKE_MODE/FAKE_RC/
# FAKE_ERR/FAKE_STDOUT 控制；argv 记入 $FAKE_LOG 供断言。
FAKE_ZHIHU = r"""#!/bin/sh
PATH=/usr/bin:/bin; export PATH  # lane 只给 bindir；fake 内部需要 mkdir 等
echo "$@" >> "$FAKE_LOG"
out=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
case "${FAKE_MODE:-ok}" in
ok)
  mkdir -p "$out/answers"
  echo "# answer" > "$out/answers/0001_某人.md"
  echo "# top" > "$out/标题_作者_2026.md"
  exit 0
  ;;
empty)
  mkdir -p "$out"
  exit 0
  ;;
*)
  [ -n "${FAKE_ERR:-}" ] && printf '%s\n' "$FAKE_ERR" >&2
  [ -n "${FAKE_STDOUT:-}" ] && printf '%s\n' "$FAKE_STDOUT"
  exit "${FAKE_RC:-1}"
  ;;
esac
"""

# fake zhihu-scraper：`fetch <url> -s <settings> -o <dir> [--comments]`
FAKE_SCRAPER = r"""#!/bin/sh
PATH=/usr/bin:/bin; export PATH
echo "$@" >> "$FAKE_LOG"
out=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
case "${FAKE_MODE:-ok}" in
ok)
  mkdir -p "$out/某专栏/内容" "$out/某专栏/assets"
  echo "# 第一篇" > "$out/某专栏/内容/第一篇.md"
  echo "bin" > "$out/某专栏/assets/cover.bin"
  echo "# progress" > "$out/归档进度.md"
  exit 0
  ;;
empty)
  mkdir -p "$out"
  exit 0
  ;;
*)
  [ -n "${FAKE_ERR:-}" ] && printf '%s\n' "$FAKE_ERR" >&2
  [ -n "${FAKE_STDOUT:-}" ] && printf '%s\n' "$FAKE_STDOUT"
  exit "${FAKE_RC:-1}"
  ;;
esac
"""

LEGAL_TYPES = {"progress", "artifact", "data", "error", "call", "result"}
TERMINAL_TYPES = {"result", "data", "error"}


@pytest.fixture
def fakebin(tmp_path):
    d = tmp_path / "bin"
    d.mkdir()
    log = tmp_path / "faketool.log"
    return d, log


def put_tool(bindir, name, body):
    p = bindir / name
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def run_lane(lane, req, env):
    return subprocess.run(
        [sys.executable, str(lane)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def make_req(tmp_path, kind, raw="https://www.zhihu.com/x", params=None):
    jdir = tmp_path / "job"
    adir = jdir / "artifacts"
    adir.mkdir(parents=True, exist_ok=True)
    return {
        "job_id": "test-job",
        "identity": {
            "raw": raw,
            "key": f"{kind}:1",
            "kind": kind,
            "params": params or {},
        },
        "ctx": {
            "artifact_dir": str(adir),
            "journal_dir": str(jdir),
            "budget_ms": 15000,
            "cred_handle": "",
            "key": f"{kind}:1",
        },
    }


def lane_env(tmp_path, bindir, extra=None):
    env = {
        "PATH": str(bindir),
        "HOME": str(tmp_path / "home"),
        "FAKE_LOG": "",
        "LANG": "C.UTF-8",
    }
    env.update(extra or {})
    return env


def parse_jsonl(stdout):
    """断言 stdout 每行都是合法 JSONL 事件；返回事件列表。"""
    events = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        assert ev.get("type") in LEGAL_TYPES, ev
        events.append(ev)
    return events


def terminal(events):
    terms = [e for e in events if e["type"] in TERMINAL_TYPES]
    assert len(terms) == 1, terms
    return terms[0]


# ================================================================ zhcli_lane


def test_zhcli_dep_absent_rc10(tmp_path, fakebin):
    bindir, log = fakebin
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    p = run_lane(
        ZHCLI, make_req(tmp_path, "art", "https://zhuanlan.zhihu.com/p/1"), env
    )
    assert p.returncode == 10
    # 静默跳过：stdout 无终态行（progress 也不发）
    assert not [e for e in parse_jsonl(p.stdout) if e["type"] in TERMINAL_TYPES]


def test_zhcli_unknown_kind_rc10(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    p = run_lane(
        ZHCLI, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/1"), env
    )
    assert p.returncode == 10
    assert not [e for e in parse_jsonl(p.stdout) if e["type"] in TERMINAL_TYPES]


def test_zhcli_result_items(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    req = make_req(tmp_path, "art", "https://zhuanlan.zhihu.com/p/12345")
    p = run_lane(ZHCLI, req, env)
    assert p.returncode == 0, p.stderr
    events = parse_jsonl(p.stdout)
    term = terminal(events)
    assert term["type"] == "result"
    names = {i["name"] for i in term["items"]}
    assert names == {"answers/0001_某人.md", "标题_作者_2026.md"}
    adir = Path(req["ctx"]["artifact_dir"]).resolve()
    for it in term["items"]:
        rp = Path(it["path"]).resolve()
        assert adir in rp.parents  # 产物不得出 artifact_dir
        assert rp.is_file()
        assert it["bytes"] == rp.stat().st_size
    # argv 合同：download article <raw> -o <stage>
    argv = log.read_text().splitlines()[0].split()
    assert argv[0] == "download"
    assert argv[1] == "article"
    assert "https://zhuanlan.zhihu.com/p/12345" in argv


def test_zhcli_kind_modes(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    for kind, mode in [
        ("q", "question"),
        ("ppl", "user"),
        ("zv", "video"),
        ("pin", "pin"),
    ]:
        p = run_lane(ZHCLI, make_req(tmp_path, kind), env)
        assert p.returncode == 0, (kind, p.stderr)
        argv = log.read_text().splitlines()[-1].split()
        assert argv[1] == mode, (kind, argv)


def test_zhcli_uvx_fallback(tmp_path, fakebin):
    bindir, log = fakebin
    # zhihu 不在 PATH（藏进 off-PATH 的 pkgbin）；uvx 转交给它
    pkgbin = tmp_path / "pkgbin"
    pkgbin.mkdir()
    put_tool(pkgbin, "zhihu", FAKE_ZHIHU)
    uvx = bindir / "uvx"
    uvx.write_text(f'#!/bin/sh\nshift 3\nexec "{pkgbin}/zhihu" "$@"\n')
    uvx.chmod(uvx.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    p = run_lane(ZHCLI, make_req(tmp_path, "art"), env)
    assert p.returncode == 0, p.stderr
    argv = log.read_text().splitlines()[0].split()
    assert argv[0] == "download"  # uvx 剥掉 --from pkg zhihu 后转交


def test_zhcli_auth_expired(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = (
        "Zhihu returned HTTP 401; authentication is missing or expired. "
        "Check the z_c0 and d_c0 Cookie fields."
    )
    p = run_lane(ZHCLI, make_req(tmp_path, "q"), env)
    assert p.returncode == 0
    term = terminal(parse_jsonl(p.stdout))
    assert term["type"] == "error"
    assert term["class"] == "auth_expired"
    assert term["retryable"] is False
    assert term["needs_human"] is True


def test_zhcli_need_login_true_is_auth(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    # zhihu-cli 把 need_login 折进 captcha 管线：banner 带 unhuman+need_login=true
    env["FAKE_STDOUT"] = (
        "Zhihu Risk Control / Captcha Triggered\n"
        "https://www.zhihu.com/account/unhuman?type=S6E3V1&need_login=true&session=abc"
    )
    env["FAKE_ERR"] = "requests.HTTPError: 403 Client Error: Forbidden for url"
    p = run_lane(ZHCLI, make_req(tmp_path, "ppl"), env)
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "auth_expired"


def test_zhcli_challenge(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = (
        "RuntimeError: Zhihu returned an HTML zh-zse-ck "
        "risk-control challenge for https://www.zhihu.com/people/x"
    )
    p = run_lane(ZHCLI, make_req(tmp_path, "zv"), env)
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "challenge_needed"
    assert term["needs_human"] is True
    assert term["retryable"] is False


def test_zhcli_delsign_in_stderr_is_transient(tmp_path, fakebin):
    """stderr 里的删除签名样文本不是墓碑证据（枚举页会提到已删条目）——
    只在产出内容上判（connector z_store delguard → rc4 同层），
    工具侧按 transient 走，防把活内容误判成 permanent 90d。"""
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "ValueError: 该内容已被发布者删除"
    p = run_lane(ZHCLI, make_req(tmp_path, "art"), env)
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "transient"
    assert term["retryable"] is True


def test_zhcli_rate_limited(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "requests.HTTPError: 429 Client Error: Too Many Requests"
    p = run_lane(ZHCLI, make_req(tmp_path, "pin"), env)
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "rate_limited"
    assert term["retryable"] is True


def test_zhcli_transient(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "requests.ConnectionError: boom"
    p = run_lane(ZHCLI, make_req(tmp_path, "art"), env)
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "transient"
    assert term["retryable"] is True


def test_zhcli_rc0_no_files_noresults(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu", FAKE_ZHIHU)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "empty"
    p = run_lane(ZHCLI, make_req(tmp_path, "art"), env)
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "noresults"
    assert term["retryable"] is False


def test_zhcli_bad_stdin(tmp_path, fakebin):
    bindir, _ = fakebin
    env = lane_env(tmp_path, bindir)
    p = subprocess.run(
        [sys.executable, str(ZHCLI)],
        input="not json\n",
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "protocol_violation"


# ============================================================== scraper_lane


def test_scraper_dep_absent_rc10(tmp_path, fakebin):
    bindir, log = fakebin
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    p = run_lane(
        SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/1"), env
    )
    assert p.returncode == 10
    assert not [e for e in parse_jsonl(p.stdout) if e["type"] in TERMINAL_TYPES]


def test_scraper_unknown_kind_rc10(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    p = run_lane(
        SCRAPER, make_req(tmp_path, "q", "https://www.zhihu.com/question/1"), env
    )
    assert p.returncode == 10


def test_scraper_result_items_relpath(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    req = make_req(tmp_path, "col", "https://www.zhihu.com/column/mycol")
    p = run_lane(SCRAPER, req, env)
    assert p.returncode == 0, p.stderr
    term = terminal(parse_jsonl(p.stdout))
    assert term["type"] == "result"
    names = {i["name"] for i in term["items"]}
    assert "某专栏/内容/第一篇.md" in names
    assert "某专栏/assets/cover.bin" in names
    assert "归档进度.md" in names
    adir = Path(req["ctx"]["artifact_dir"]).resolve()
    for it in term["items"]:
        assert adir in Path(it["path"]).resolve().parents


def test_scraper_zhuanlan_rewrite(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    p = run_lane(
        SCRAPER,
        make_req(tmp_path, "col", "https://zhuanlan.zhihu.com/mycol"),
        env,
    )
    assert p.returncode == 0, p.stderr
    argv = log.read_text().splitlines()[0].split()
    assert argv[0] == "fetch"
    assert argv[1] == "https://www.zhihu.com/column/mycol"


def test_scraper_settings_arg(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    run_lane(SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env)
    argv = log.read_text().splitlines()[-1].split()
    si = argv.index("-s")
    assert argv[si + 1].endswith(".config/zhihu-skill/settings.toml")


def test_scraper_settings_env_override(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["ZHIHU_SETTINGS"] = "/custom/s.toml"
    run_lane(SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env)
    argv = log.read_text().splitlines()[-1].split()
    si = argv.index("-s")
    assert argv[si + 1] == "/custom/s.toml"


def test_scraper_comments_flag(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    run_lane(
        SCRAPER,
        make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9", {"comments": True}),
        env,
    )
    argv = log.read_text().splitlines()[-1].split()
    assert "--comments" in argv


def test_scraper_comments_flag_col(tmp_path, fakebin):
    """col 分支 COMMENTS=1 时 connector 同样加 --comments（lanes_run 平价）。"""
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    run_lane(
        SCRAPER,
        make_req(
            tmp_path, "col", "https://www.zhihu.com/column/c", {"comments": "true"}
        ),
        env,
    )
    argv = log.read_text().splitlines()[-1].split()
    assert "--comments" in argv


def test_scraper_no_comments_flag(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    run_lane(SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env)
    argv = log.read_text().splitlines()[-1].split()
    assert "--comments" not in argv


def test_scraper_auth_401(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = (
        "错误：Zhihu returned HTTP 401; authentication is missing or expired. "
        "Check the z_c0 and d_c0 Cookie fields."
    )
    p = run_lane(
        SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "auth_expired"
    assert term["needs_human"] is True


def test_scraper_auth_403_zc0(tmp_path, fakebin):
    """scraper 403 文案自带 'Refresh the z_c0'（死 cookie 是 403 的主因）。"""
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = (
        "错误：Zhihu returned HTTP 403; access was denied. "
        "Refresh the z_c0 and d_c0 Cookie fields or use browser fallback."
    )
    p = run_lane(
        SCRAPER, make_req(tmp_path, "col", "https://www.zhihu.com/column/c"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "auth_expired"


def test_scraper_browser_fallback_challenge(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "错误：HTTP 抓取失败，但当前没有配置浏览器回退。"
    p = run_lane(
        SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "challenge_needed"
    assert term["needs_human"] is True


def test_scraper_rate_limited(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = (
        "错误：Zhihu returned HTTP 429 after limited retries; "
        "reduce request frequency and try again later."
    )
    p = run_lane(
        SCRAPER, make_req(tmp_path, "col", "https://www.zhihu.com/column/c"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "rate_limited"
    assert term["retryable"] is True


def test_scraper_cookie_file_error_is_auth(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "错误：Could not safely load Cookie file cookies.json."
    p = run_lane(
        SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "auth_expired"


def test_scraper_delsign_in_stderr_is_transient(tmp_path, fakebin):
    """删除签名在工具 stderr 里不是墓碑证据（同 zhcli 侧）——产出内容才判。"""
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "错误：该回答已被删除"
    p = run_lane(
        SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "transient"
    assert term["retryable"] is True


def test_scraper_transient(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = (
        "错误：Zhihu request failed after limited retries; check the network or proxy."
    )
    p = run_lane(
        SCRAPER, make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "transient"
    assert term["retryable"] is True


def test_scraper_rc0_no_files_noresults(tmp_path, fakebin):
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "empty"
    p = run_lane(
        SCRAPER, make_req(tmp_path, "col", "https://www.zhihu.com/column/c"), env
    )
    term = terminal(parse_jsonl(p.stdout))
    assert term["class"] == "noresults"


def test_scraper_error_cleans_stage(tmp_path, fakebin):
    """失败终态不留 staging（staged_run rm -rf 平价）。"""
    bindir, log = fakebin
    put_tool(bindir, "zhihu-scraper", FAKE_SCRAPER)
    env = lane_env(tmp_path, bindir)
    env["FAKE_LOG"] = str(log)
    env["FAKE_MODE"] = "err"
    env["FAKE_ERR"] = "boom"
    req = make_req(tmp_path, "ans", "https://www.zhihu.com/answer/9")
    p = run_lane(SCRAPER, req, env)
    assert terminal(parse_jsonl(p.stdout))["type"] == "error"
    assert not (Path(req["ctx"]["artifact_dir"]) / ".scraper-stage").exists()
