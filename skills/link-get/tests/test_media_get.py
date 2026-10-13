# test_media_get.py — media-get Phase-0 修补的离线回归矩阵。
#   A) b23.tv 解析进键（同视频同键）  B) fail() 按类记账  C) 字面 host SSRF 闸
# Run:
#   TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests/test_media_get.py -x -q
# 无真实外网：解析/记账全部打桩；SSRF 用本地 http.server 证零外呼。
# All temp dirs land under $HOME/.cache (never /tmp — tmpfs is full).

import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

MEDIA_GET = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "connectors", "media-get"
)
TMPBASE = os.path.expanduser("~/.cache")

BV = "https://www.bilibili.com/video/BV1xx411c7mD/"


@pytest.fixture
def mg(monkeypatch):
    """隔离加载 media-get（无 .py 后缀→SourceFileLoader）；LGC_OFF + 伪 HOME，
    真 lgc/真凭证文件一律不可见。"""
    home = tempfile.mkdtemp(prefix="mg-test-", dir=TMPBASE)
    monkeypatch.setenv("LGC_OFF", "1")
    monkeypatch.setenv("LGC_HOME", os.path.join(home, "lgc"))
    monkeypatch.setenv("HOME", home)
    monkeypatch.delenv("LGC_CAPS", raising=False)
    monkeypatch.delenv("LGC_REFRESH", raising=False)
    loader = importlib.machinery.SourceFileLoader("media_get", MEDIA_GET)
    spec = importlib.util.spec_from_loader("media_get", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    yield m
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def outdir():
    d = tempfile.mkdtemp(prefix="mg-out-", dir=TMPBASE)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# --- A) b23.tv 解析进键 -------------------------------------------------------


def test_b23_resolve_adopts_and_caches(mg, monkeypatch):
    """打桩解析成功 → canonical URL 进键，写 bili:b23:<code> 值缓存。"""
    vput = []
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)
    monkeypatch.setattr(mg, "cache_vput", lambda k, v: vput.append((k, v)))
    monkeypatch.setattr(mg, "_resolve_redirects", lambda _u: BV)
    assert mg.resolve_b23("https://b23.tv/abc123") == BV
    assert vput == [("bili:b23:abc123", BV)]
    # 同视频同键：短链键 == 直链键（修复前是双键双抓）
    assert "media:" + mg.resolve_b23("https://b23.tv/abc123") == "media:" + BV


def test_b23_cache_hit_skips_network(mg, monkeypatch):
    """值缓存命中 → 零触网（bilibili-get:26-47 的 30d 模式）。"""
    monkeypatch.setattr(mg, "cache_cat", lambda _k: BV)
    monkeypatch.setattr(
        mg, "_resolve_redirects", lambda _u: pytest.fail("缓存命中不应触网")
    )
    assert mg.resolve_b23("https://b23.tv/abc123") == BV


def test_b23_non_allowlist_target_not_adopted(mg, monkeypatch):
    """重定向出 bilibili 域 → 不采用、不缓存、原样返回（errtax 缺陷8不复刻）。"""
    vput = []
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)
    monkeypatch.setattr(mg, "cache_vput", lambda k, _v: vput.append(k))
    monkeypatch.setattr(mg, "_resolve_redirects", lambda _u: "https://evil.example/x")
    assert mg.resolve_b23("https://b23.tv/abc") == "https://b23.tv/abc"
    assert vput == []


def test_b23_resolve_failure_keeps_original(mg, monkeypatch, capsys):
    """纯网络失败 → 原 URL（bilibili-get 同款降级：yt-dlp 自己还能解），
    但 stderr 必须明示'未检'——未检链不假装已核。"""
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)
    monkeypatch.setattr(mg, "cache_vput", lambda _k, _v: None)
    monkeypatch.setattr(mg, "_resolve_redirects", lambda _u: None)
    assert mg.resolve_b23("https://b23.tv/abc") == "https://b23.tv/abc"
    assert "未检" in capsys.readouterr().err


def test_b23_blocked_chain_refused_exit2(mg, monkeypatch):
    """解析链触 SSRF 闸 → exit2 拒抓：原链交 yt-dlp 自跟 = 绕过逐跳闸。"""
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)

    def blocked(u):
        raise mg._SsrfBlocked("redirect to http://10.0.0.1/x: private")

    monkeypatch.setattr(mg, "_resolve_redirects", blocked)
    with pytest.raises(SystemExit) as e:
        mg.resolve_b23("https://b23.tv/abc")
    assert e.value.code == 2


@pytest.mark.parametrize(
    "cached",
    [
        "file:///etc/passwd",
        "file://www.bilibili.com/video/BV1xx",
        "ftp://www.bilibili.com/video/BV1xx",
        "gopher://www.bilibili.com/video/BV1xx",
        "//www.bilibili.com/video/BV1xx",
        # 控制字符拼接：urlsplit 只取首段 host 照样放行——必须整串拒
        "https://www.bilibili.com/video/BV1xx\nhttp://127.0.0.1/",
        "https://www.bilibili.com/video/BV1xx\thttp://10.0.0.1/",
        "https://www.bilibili.com/video/BV1xx http://192.168.1.1/",
    ],
)
def test_b23_cached_scheme_injection_not_adopted(mg, monkeypatch, cached):
    """值缓存读出非 http(s)/含控制空白字符的串 → 不采用、不命中
    （cache_cat 可被写任意串——\\n 拼接会同时污染 yt-dlp argv 与 media: 键）。"""
    monkeypatch.setattr(mg, "cache_cat", lambda _k: cached)
    monkeypatch.setattr(mg, "_resolve_redirects", lambda _u: None)
    monkeypatch.setattr(mg, "cache_vput", lambda _k, _v: None)
    assert mg.resolve_b23("https://b23.tv/abc") == "https://b23.tv/abc"


def test_bili_target_ok_scheme_gate(mg):
    """白名单判 scheme：非 http(s) 一律拒（旧版只看 host/path 会漏 file://）。"""
    assert mg._bili_target_ok("https://www.bilibili.com/video/BV1xx")
    assert mg._bili_target_ok("https://t.bilibili.com/123")
    for u in (
        "file://www.bilibili.com/video/BV1xx",
        "ftp://www.bilibili.com/video/BV1xx",
        "gopher://www.bilibili.com/video/BV1xx",
        "//www.bilibili.com/video/BV1xx",
    ):
        assert not mg._bili_target_ok(u)


def test_bili_target_ok_rejects_control_bytes(mg):
    """白名单整串审：空白/控制/非 ASCII 字节一律拒——urlsplit 只取首段
    host，'\\nhttp://内网' 拼接会漏进 yt-dlp argv 与 media: 键。"""
    for u in (
        "https://www.bilibili.com/video/BV1xx\nhttp://127.0.0.1/",
        "https://www.bilibili.com/video/BV1xx\tevil",
        "https://www.bilibili.com/video/BV1 xx",
        "https://www.bilibili.com/video/BV1xx\x00.evil",
        "https://www.bilibili.com/video/BV1\u4e2d",
    ):
        assert not mg._bili_target_ok(u)


def test_b23_fqdn_trailing_dot_resolves(mg, monkeypatch):
    """FQDN 尾点归一：'b23.tv.' 与 'b23.tv' 同走解析+白名单——未归一时
    host 'b23.tv.' != 'b23.tv'，短链裸奔交 yt-dlp 自跟（绕逐跳闸）。"""
    vput = []
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)
    monkeypatch.setattr(mg, "cache_vput", lambda k, v: vput.append((k, v)))
    monkeypatch.setattr(mg, "_resolve_redirects", lambda _u: BV)
    assert mg.resolve_b23("https://b23.tv./abc123") == BV
    assert vput == [("bili:b23:abc123", BV)]


def test_b23_fqdn_trailing_dot_blocked_exit2(mg, monkeypatch):
    """尾点链触闸同样 exit2——尾点不是绕闸通道。"""
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)

    def blocked(_u):
        raise mg._SsrfBlocked("redirect to http://10.0.0.1/x: private")

    monkeypatch.setattr(mg, "_resolve_redirects", blocked)
    with pytest.raises(SystemExit) as e:
        mg.resolve_b23("https://b23.tv./abc")
    assert e.value.code == 2


def test_non_b23_urls_untouched(mg, monkeypatch):
    """非 b23 域零行为变化——含 evilb23.tv 与 ?u=b23.tv/ 子串撞车。"""
    monkeypatch.setattr(
        mg, "_resolve_redirects", lambda _u: pytest.fail("非 b23 不应解析")
    )
    monkeypatch.setattr(mg, "cache_cat", lambda _k: pytest.fail("非 b23 不读值缓存"))
    for u in (
        "https://www.bilibili.com/video/BV1xx",
        "https://www.youtube.com/watch?v=x",
        "https://evilb23.tv/x",
        "https://x.com/?u=b23.tv/abc",
    ):
        assert mg.resolve_b23(u) == u


def test_main_key_uses_resolved_url(mg, monkeypatch, outdir):
    """端到端键推导：argv 进 b23 → cache_get 见到的是 BV 键。"""
    seen = {}
    monkeypatch.setattr(mg, "cred8", lambda: "anon")
    monkeypatch.setattr(mg, "cache_cat", lambda _k: None)
    monkeypatch.setattr(mg, "cache_vput", lambda _k, _v: None)
    monkeypatch.setattr(mg, "_resolve_redirects", lambda _u: BV)

    def fake_get(key, out, satisfies, cred):
        seen["key"] = key
        return 5, []  # neg 回放 rc5 → sys.exit(5)，停在抓取前

    monkeypatch.setattr(mg, "cache_get", fake_get)
    monkeypatch.setattr(sys, "argv", ["media-get", "https://b23.tv/abc", "-o", outdir])
    with pytest.raises(SystemExit) as e:
        mg.main()
    assert e.value.code == 5
    assert seen["key"] == "media:" + BV


def test_main_key_non_b23_passthrough(mg, monkeypatch, outdir):
    """对照组：非 b23 URL 键原样。"""
    seen = {}
    monkeypatch.setattr(mg, "cred8", lambda: "anon")
    url = "https://www.youtube.com/watch?v=abcDEF12345"

    def fake_get(key, out, satisfies, cred):
        seen["key"] = key
        return 5, []

    monkeypatch.setattr(mg, "cache_get", fake_get)
    monkeypatch.setattr(sys, "argv", ["media-get", url, "-o", outdir])
    with pytest.raises(SystemExit) as e:
        mg.main()
    assert e.value.code == 5
    assert seen["key"] == "media:" + url


# --- B) fail() 按类记账 --------------------------------------------------------


@pytest.fixture
def spy(mg, monkeypatch):
    """记账面打桩：neg=内容墓碑，lane=车道记账(带 reason)，rel=inflight 释放。"""
    rec = {"neg": [], "lane": [], "rel": []}
    monkeypatch.setattr(mg, "cache_neg", lambda _k, r, _c: rec["neg"].append(r))
    monkeypatch.setattr(
        mg,
        "lane_fail",
        lambda lane, _k=None, reason="lane-fail", _ttl=None: rec["lane"].append(
            (lane, reason)
        ),
    )
    monkeypatch.setattr(mg, "cache_release", lambda k, _c: rec["rel"].append(k))
    return rec


@pytest.mark.parametrize(
    "msg",
    [
        "yt-dlp metadata failed:\nERROR: [youtube] x: Video unavailable",
        "yt-dlp metadata failed:\nERROR: [BiliBili] BV1: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\nERROR: [BiliBili] BV1: Unable to download webpage: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\nERROR: 视频不见了，或已被删除",
        "yt-dlp metadata failed:\nERROR: This video has been removed by the uploader",
        "yt-dlp metadata failed:\nERROR: account associated with this video has been terminated",
        "yt-dlp metadata failed:\nERROR: copyright takedown",
        "yt-dlp metadata failed:\nERROR: 该内容已被发布者删除",
        "yt-dlp metadata failed:\nERROR: [BiliBili] BV1: 该视频已下架",
        "yt-dlp metadata failed:\nERROR: 该视频已设为私密",
        "yt-dlp metadata failed:\nERROR: 账号已注销",
    ],
)
def test_fail_permanent_writes_tombstone(mg, spy, msg):
    """删除/下架实锤 → deleted 墓碑 + exit4（下轮 replay rc4），不记车道。"""
    with pytest.raises(SystemExit) as e:
        mg.fail("media:u", "anon", msg, lane="yt-dlp")
    assert e.value.code == 4
    assert spy["neg"] == ["deleted"]
    assert spy["lane"] == []
    assert spy["rel"] == ["media:u"]


@pytest.mark.parametrize(
    "msg",
    [
        # 实测复现：geo 文案含 'video unavailable'，旧闸误落 90d deleted 墓碑
        "yt-dlp metadata failed:\nERROR: [youtube] x: Video unavailable. "
        "The uploader has not made this video available in your country",
        "yt-dlp metadata failed:\nERROR: [youtube] x: This video is not available in your country",
        "yt-dlp metadata failed:\nERROR: [BiliBili] BV1: 该视频在您所在的地区无法播放",
        "yt-dlp metadata failed:\nERROR: Private video. Sign in if you've been granted access",
        "yt-dlp metadata failed:\nERROR: This video is available to this channel's members",
        # round-3 分类补齐：年龄确认/付费/Premium/版权地域锁 —— 均 cred 域可解
        "yt-dlp metadata failed:\nERROR: [youtube] x: Sign in to confirm your age",
        "yt-dlp metadata failed:\nERROR: This video requires payment to watch",
        "yt-dlp metadata failed:\nERROR: This video is only available to Music Premium members",
        "yt-dlp metadata failed:\nERROR: [youtube] x: Video unavailable. "
        "This video contains content from SME, who has blocked it in your country "
        "on copyright grounds",
    ],
)
def test_fail_auth_scope_no_tombstone(mg, spy, msg):
    """auth/scope 类（地区锁/私有/会员）→ cred 域 auth-expired 负缓存 + exit5：
    可换凭证/地区重试，绝不写 deleted 墓碑、不撞共享 breaker。"""
    with pytest.raises(SystemExit) as e:
        mg.fail("media:u", "anon", msg, lane="yt-dlp")
    assert e.value.code == 5
    assert spy["neg"] == ["auth-expired"]
    assert spy["lane"] == []
    assert spy["rel"] == ["media:u"]


@pytest.mark.parametrize(
    "msg",
    [
        "yt-dlp metadata failed:\nERROR: unable to download video data: HTTP Error 503",
        # 下载/传输阶段 404——CDN/manifest 抖动不是内容终态，不得墓碑
        "yt-dlp metadata failed:\nERROR: unable to download video data: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\nERROR: Unable to download manifest: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\nGot error: HTTP Error 404: Not Found. Retrying fragment 2",
        "yt-dlp metadata failed:\nERROR: Unable to download video subtitles: HTTP Error 404: Not Found",
        # round-3：segment/chunk/[download] 标的传输面 404 同样不墓碑
        "yt-dlp metadata failed:\nERROR: [download] Got error: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\nERROR: unable to download segment 3: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\nERROR: unable to download chunk 7: HTTP Error 404: Not Found",
        "yt-dlp metadata failed:\ntimed out",
        "yt-dlp metadata unparseable",
        "video download failed; login-gated? try: BBDown <URL>",
        "video download produced no video.* file",
    ],
)
def test_fail_transient_lane_only(mg, spy, msg):
    """transient/网络/下载阶段类 → 只记 lane 失败 + exit5，绝不写内容墓碑。"""
    with pytest.raises(SystemExit) as e:
        mg.fail("media:u", "anon", msg, lane="yt-dlp")
    assert e.value.code == 5
    assert spy["neg"] == []
    assert spy["lane"] == [("yt-dlp", "lane-fail")]
    assert spy["rel"] == ["media:u"]


def test_fail_runtime_no_lane_no_tombstone(mg, spy):
    """本地运行异常（无 lane 可归）→ exit5 + 零记账，只释放 marker。"""
    with pytest.raises(SystemExit) as e:
        mg.fail("media:u", "anon", "runtime failure: disk full")
    assert e.value.code == 5
    assert spy["neg"] == []
    assert spy["lane"] == []
    assert spy["rel"] == ["media:u"]


# --- C) SSRF 字面 host 闸 ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/video/BV1xx411c7mD/",
        "https://b23.tv/abc123",
        "https://www.youtube.com/watch?v=x",
        "https://v.sjtu.edu.cn/play-center/x",
        "https://8.8.8.8/",
        "http://example.com:8080/a?b=c",
        "http://user@example.com/",  # userinfo + 公网 host
        "http://dead.beef/",  # 全 hex 字母段 → 主机名非字面
        "http://1.2.3/",  # inet_aton a.b.c → 1.2.0.3 公网
        # --- 主机名优先（round-3）：含 [0-9a-fx.] 外字符的标签不当字面解析 ----
        "http://01net.com/",  # 'n'/'e'/'t' 非字面字符 → 主机名
        "http://0x.org/",  # 'o'/'r'/'g' → 主机名
        "http://00abc.com/",  # 'o'/'m' → 主机名
        "http://09abc.com/",
        "http://0x4k.tv/",
        "http://0x.com/",
        "http://0xzz.1.1.1/",  # 'z' 非 hex 字面字符 → 主机名（bash 同款放行）
    ],
)
def test_ssrf_allow(mg, url):
    assert mg._ssrf_check(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/x",  # loopback v4
        "http://[::1]/",  # loopback v6
        "http://169.254.169.254/latest",  # link-local 云元数据
        "http://10.0.0.5/",  # RFC1918
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://localhost/x",  # 主机名表
        "http://a.localhost/",
        "http://nas.local/",
        "http://0.0.0.0/",  # unspecified
        "http://2130706433/",  # inet_aton 整数
        "http://127.1/",  # inet_aton 短写
        "http://0x7f000001/",  # inet_aton 十六进制
        "http://0177.0.0.1/",  # inet_aton 八进制
        "http://[::ffff:127.0.0.1]/",  # v4-mapped v6
        "file:///etc/passwd",  # 非 http(s) 方案
        "ftp://example.com/x",
        "gopher://127.0.0.1/",
        "http://",  # 空 host
        "not-a-url",
        # --- parity 修补（对齐 _common.sh::_guard_url）----------------------
        "http://example.com\\@127.0.0.1/",  # authority 含 \\——BBDown 把 \\@ 前段当 host
        "http://127.0.0.1\\@example.com/",  #   urllib 取末 @ 后段 → 旧版放行
        "http://foo\\bar.evil.com/",
        "http://127.0.0.1/ x",  # URL 空白字符
        "http://example.com/ x",
        "http://%31%32%37%2e%30%2e%30%2e%31/",  # %-编码 host——curl 自解成字面
        "http://例.com/",  # authority 非 ASCII（全角/UTF-8 障眼）
        "http://08.0.0.1/",  # 畸形：坏八进制段
        "http://999.1.2.3/",  # 畸形：段溢出
        "http://1.2.3.4.5/",  # 畸形：全数字 >4 段
        "http://1..2.3/",  # 畸形：空段（连点）
        "http://0x.1.1.1/",  # 畸形：'0x' 裸前缀空段
        "http://0xx.1.1.1/",  # 畸形：'0x' 后非 hex 字面字符
        "http://fe80::1/",  # 裸 v6 字面（缺 bracket）链路本地
        "http://::1/",  # 裸 v6 回环
        # --- is_global 收口（F）---------------------------------------------
        "http://100.64.1.1/",  # CGNAT 共享段
        "http://198.18.0.1/",  # benchmark 段
        "http://224.0.0.1/",  # multicast
        "http://[2001:db8::1]/",  # documentation 段
        "http://192.0.0.9/",  # 192.0.0/24 整段拒（bash 同款；anycast 也拒）
        # --- round-3 parity：glob 字符 + 大写 scheme --------------------------
        "http://ex*ample.com/",  # host 含 glob 字符
        "HTTP://example.com/",  # 大写 scheme（bash 闸按字节匹配）
        # --- v6 内嵌 v4 一律拒（F）-------------------------------------------
        "http://[::ffff:8.8.8.8]/",  # mapped 公网也拒
        "http://[::8.8.8.8]/",  # v4-compat
        "http://[64:ff9b::127.0.0.1]/",  # NAT64 WKP
        "http://[2002:808:808::]/",  # 6to4
        "http://[2001:0::808:808]/",  # teredo
        "http://[2001:4860::5efe:808:808]/",  # ISATAP IID 公网前缀
    ],
)
def test_ssrf_reject(mg, url):
    assert mg._ssrf_check(url) is not None


def test_resolve_redirects_refuses_local(mg):
    """打真本地 http.server：入口被闸 → _SsrfBlocked（零请求）。"""
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(1)
            self.send_response(200)
            self.end_headers()

        def do_HEAD(self):
            hits.append(1)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(mg._SsrfBlocked):
            mg._resolve_redirects(f"http://127.0.0.1:{srv.server_port}/")
        assert hits == []
    finally:
        srv.shutdown()


def _quiet_hits():
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_HEAD(self):
            hits.append(("HEAD", self.path))
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            hits.append(("GET", self.path))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    return hits, H


def test_resolve_redirects_follows_chain_offline(mg, monkeypatch):
    """urllib 跟链管线验证（桩放行闸）：本地 A→B 302，终态取 geturl。"""
    monkeypatch.setattr(mg, "_ssrf_check", lambda _u: None)
    hits_b, hb = _quiet_hits()
    b = HTTPServer(("127.0.0.1", 0), hb)
    b_url = f"http://127.0.0.1:{b.server_port}/final"
    hits_a = []

    class RA(BaseHTTPRequestHandler):
        def do_HEAD(self):
            hits_a.append(self.path)
            self.send_response(302)
            self.send_header("Location", b_url)
            self.end_headers()

        def log_message(self, *a):
            pass

    a = HTTPServer(("127.0.0.1", 0), RA)
    threading.Thread(target=b.serve_forever, daemon=True).start()
    threading.Thread(target=a.serve_forever, daemon=True).start()
    try:
        assert mg._resolve_redirects(f"http://127.0.0.1:{a.server_port}/abc") == b_url
        assert hits_a == ["/abc"]  # HEAD 跟链、不读 body
    finally:
        a.shutdown()
        b.shutdown()


def test_resolve_redirects_blocked_midchain(mg, monkeypatch):
    """30x 跳往被闸目标 → _SsrfBlocked 断链（≠网络失败）、目标零命中。"""
    hits_b, hb = _quiet_hits()
    b = HTTPServer(("127.0.0.1", 0), hb)
    bad_url = f"http://127.0.0.1:{b.server_port}/internal"

    def guard(u):
        # 放行本地服务器自身，只拦 /internal 目标（模拟内网终态）
        return "simulated non-public" if "/internal" in u else None

    monkeypatch.setattr(mg, "_ssrf_check", guard)

    class RA(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(302)
            self.send_header("Location", bad_url)
            self.end_headers()

        def log_message(self, *a):
            pass

    a = HTTPServer(("127.0.0.1", 0), RA)
    threading.Thread(target=b.serve_forever, daemon=True).start()
    threading.Thread(target=a.serve_forever, daemon=True).start()
    try:
        with pytest.raises(mg._SsrfBlocked):
            mg._resolve_redirects(f"http://127.0.0.1:{a.server_port}/abc")
        assert hits_b == []  # 被拦目标零请求
    finally:
        a.shutdown()
        b.shutdown()


def test_cover_302_to_blocked_target_refused(mg, monkeypatch, outdir):
    """封面 302 跳进被闸目标 → _fetch_cover 断链拒写、目标零命中。
    旧版 urlopen 默认 opener 闭眼跟链——公网封面即可 SSRF 内网。"""
    hits_b, hb = _quiet_hits()
    b = HTTPServer(("127.0.0.1", 0), hb)
    bad_url = f"http://127.0.0.1:{b.server_port}/internal"

    def guard(u):
        return "simulated non-public" if "/internal" in u else None

    monkeypatch.setattr(mg, "_ssrf_check", guard)

    class RA(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", bad_url)
            self.end_headers()

        def log_message(self, *a):
            pass

    a = HTTPServer(("127.0.0.1", 0), RA)
    threading.Thread(target=b.serve_forever, daemon=True).start()
    threading.Thread(target=a.serve_forever, daemon=True).start()
    stage = os.path.join(outdir, "stage")
    os.mkdir(stage)
    try:
        with pytest.raises(mg._SsrfBlocked):
            mg._fetch_cover(f"http://127.0.0.1:{a.server_port}/t.jpg", Path(stage))
        assert hits_b == []  # 被拦目标零请求
        assert os.listdir(stage) == []  # 不落半截封面
    finally:
        a.shutdown()
        b.shutdown()


def test_fetch_cover_entry_blocked_zero_request(mg, outdir):
    """入口 URL 自身触闸 → _SsrfBlocked 零请求——与 _resolve_redirects 同款
    入口门（纵深防御：调用方查过也再查，直连调用不裸奔）。"""
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(1)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    stage = os.path.join(outdir, "stage")
    os.mkdir(stage)
    try:
        with pytest.raises(mg._SsrfBlocked):
            mg._fetch_cover(f"http://127.0.0.1:{srv.server_port}/t.jpg", Path(stage))
        assert hits == []  # 入口被闸零请求
        assert os.listdir(stage) == []
    finally:
        srv.shutdown()


def test_main_refuses_loopback_before_any_fetch(mg, monkeypatch, outdir):
    """main() 在 mkdir/spawn 前拒内网 URL：exit2 + 服务器零命中。"""
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(1)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(mg, "run", lambda *_a, **_k: pytest.fail("不应 spawn 子进程"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["media-get", f"http://127.0.0.1:{srv.server_port}/", "-o", outdir],
    )
    try:
        with pytest.raises(SystemExit) as e:
            mg.main()
        assert e.value.code == 2
        assert hits == []
    finally:
        srv.shutdown()
