# test_url_guard.py — SSRF 闸（_common.sh::_guard_url）单测矩阵 + connector 入口拒用回归。
# 复现缺陷：generic-get 曾能抓 http://127.0.0.1:8877 产出 article--*.md exit 0（PLAN §1.1）。
# Run:
#   TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests/test_url_guard.py -x -q
# All temp dirs land under $HOME/.cache (never /tmp — tmpfs is full).

import functools
import glob
import http.server
import os
import shutil
import subprocess
import tempfile
import threading

import pytest

HERE = os.path.dirname(__file__)
CONN = os.path.join(HERE, "..", "scripts", "connectors")
COMMON = os.path.join(CONN, "_common.sh")
GENERIC = os.path.join(CONN, "generic-get")
WECHAT = os.path.join(CONN, "wechat-get")
YOUTUBE = os.path.join(CONN, "youtube-get")
LGC = os.path.join(HERE, "..", "scripts", "lgc")
TMPBASE = os.path.expanduser("~/.cache")
BASH = "/bin/bash"  # 连接器 shebang 同壳——3.2 底线契约的验证对象


def guard_rc(urls):
    """batch: 一次 bash 进程求每个 url 的 _guard_url rc → {url: rc}."""
    script = (
        'source "$1"; shift; for u in "$@"; do '
        '_guard_url "$u" >/dev/null 2>&1; printf "%s\\t%s\\n" "$?" "$u"; done'
    )
    r = subprocess.run(
        [BASH, "-c", script, "_", COMMON, *list(urls)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    out = {}
    for line in r.stdout.splitlines():
        rc, _, u = line.partition("\t")
        out[u] = int(rc)
    return out


REJECT = [
    # 原缺陷复现 + 127/8 全形态（dword/短形/hex/octal/尾点）
    "http://127.0.0.1:8877/x",
    "http://127.0.0.1/",
    "http://127.1/",
    "http://127.0.1/",
    "http://127.0.0.1./",
    "http://2130706433/",
    "http://340282366920938463463374607431768211455/",  # >19 位 dword 溢出 int64 回绕 → 畸形拒
    "http://0x7f000001/",
    "http://0x7f.0.0.1/",
    "http://0177.0.0.1/",
    "http://0177.0.0.1./",
    # 10/8 · 172.16/12 · 192.168/16 · 169.254/16 · 0/8
    "http://10.0.0.1/",
    "http://10.255.255.255/",
    "http://172.16.0.1/",
    "http://172.31.255.255/",
    "http://192.168.0.1/",
    "http://169.254.169.254/latest/meta-data",
    "http://0.0.0.0/",
    "http://0/",
    # 私网段补齐：CGNAT 100.64/10（tailnet 文档内地址）、192.0.0/24、
    # 198.18/15、224/4 组播、240/4 保留
    "http://100.64.0.1/",
    "http://100.100.100.100/",
    "http://100.127.255.254/",
    "http://1681915905/",  # 100.64.0.1 dword
    "http://192.0.0.1/",
    "http://192.0.0.255/",
    "http://192.88.99.1/",  # 6to4 relay anycast 192.88.99/24（python is_global parity）
    "http://192.88.99.254/",
    "http://198.18.0.1/",
    "http://198.19.255.254/",
    "http://224.0.0.1/",
    "http://239.255.255.255/",
    "http://240.0.0.1/",
    "http://255.255.255.255/",
    # 非 http(s) scheme / 无 scheme / 空 authority
    "ftp://127.0.0.1/",
    "file:///etc/passwd",
    "gopher://127.0.0.1/",
    "127.0.0.1",
    "http://",
    "http:///path",
    "http://:8080/",
    # 本地/内网主机名（大小写 + FQDN 尾点）
    "http://localhost/",
    "http://localhost:8080/",
    "http://foo.localhost/",
    "http://printer.local/",
    "http://nas.internal/",
    "http://nas.lan/",  # .lan 本地后缀（python parity）
    "http://gw.home/",  # .home 本地后缀
    "http://nas.home.arpa/",  # RFC8375 家庭网域
    "http://home.arpa/",  # 裸 home.arpa——*.arpa 整段拒
    "http://b.in-addr.arpa/",  # 反查域同属 .arpa
    "http://LOCALHOST./",
    # userinfo 障眼——真 host 在最末 @ 之后
    "http://evil@127.0.0.1/",
    "http://user:pass@10.0.0.1/",
    "http://evil.com@127.0.0.1/",
    "http://user@",
    # IDNA/UTS46 障眼：authority 含非 ASCII 字节一律拒（不解码）
    # 全角点。．｡ / 全角数字 / 圈码①②⑦ / 全角字母——resolver 归一成 127.0.0.1/localhost
    "http://127。0。0。1/",
    "http://127．0．0．1/",
    "http://127｡0｡0｡1/",
    "http://１２７．０．０．１/",
    "http://①②⑦.0.0.1/",
    "http://ｌｏｃａｌｈｏｓｔ/",
    "http://example。com/",
    "http://用户@127.0.0.1/",
    # percent-encoded host：curl 自解 %31%32%37%2e%30%2e%30%2e%31 → 127.0.0.1
    "http://%31%32%37%2e%30%2e%30%2e%31/",
    "http://%6c%6f%63%61%6c%68%6f%73%74/",
    "http://%31%32%37.0.0.1/",
    "http://127.0.0.1%2f.evil/",
    "http://user%40evil.com@127.0.0.1/",
    # IPv6 字面：回环/链路本地/ULA + 压缩/展开/裸形
    "http://[::1]/",
    "http://[::1]:8080/",
    "http://[0:0:0:0:0:0:0:1]/",
    "http://[0::1]/",
    "http://::1/",
    "http://[::]/",
    "http://[fe80::1]/",
    "http://[febf::1]/",
    "http://[fe80:0:0:0:0:0:0:1]/",
    "http://[FE80::1]/",
    "http://[fc00::1]/",
    "http://[fdff::1]/",
    # v6 补齐：ff00::/8 组播、fec0::/10 站点本地（已废形）
    "http://[ff00::1]/",
    "http://[ff02::1]/",
    "http://[ffff::ffff]/",
    "http://[fec0::1]/",
    "http://[fed0::1]/",
    "http://[feff::1]/",
    # v4 嵌入 v6：mapped/translated/compat/NAT64/6to4/ISATAP/teredo 语义
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:7f00:1]/",
    "http://[0::ffff:127.0.0.1]/",
    "http://[::ffff:0:127.0.0.1]/",
    "http://[::ffff:0:7f00:1]/",
    "http://[::127.0.0.1]/",
    "http://[64:ff9b::127.0.0.1]/",
    # NAT64 本地前缀 64:ff9b:1::/48（RFC8215 local-use）→ 整段拒：前缀内可
    # 切 /56 /64 /96 NSP，内嵌 v4 位置随前缀长漂移，按 /48 偏移解码不可靠
    "http://[64:ff9b:1:7f00:0:100::]/",  # /48 编码内嵌 127.0.0.1
    "http://[64:ff9b:1:a00::]/",  # /48 编码内嵌 10.0.0.0
    "http://[64:ff9b:1::127.0.0.1]/",
    "http://[64:ff9b:1::7f00:1]/",
    "http://[64:ff9b:1:0808:0808::7f00:1]/",  # /96 NSP 内嵌 127.0.0.1（round-2 实锤绕过）
    "http://[64:ff9b:1:0808:0808::a00:1]/",  # /96 NSP 内嵌 10.0.0.1
    "http://[64:ff9b:1:087f:0808:0100::]/",  # 错位编码绕过 /48 解码
    "http://[64:ff9b:1:808:808::]/",  # 按 /48 解码会是公网 8.8.8.x——整段拒同拒
    "http://[2002:7f00:1::]/",
    "http://[2002:a00:1::]/",
    "http://[2001:db8::5efe:7f00:1]/",  # ISATAP IID ::5efe:v4
    "http://[fe80::200:5efe:a00:1]/",  # ISATAP ::200:5efe:v4
    "http://[fe80::1%25eth0]/",  # zone id → 畸形拒
    "http://[v1.x::]/",  # IPvFuture → 畸形拒
    # 畸形数字字面——fail-safe 拒（0x 错位/段溢出）
    "http://10.0.0.256/",
    "http://256.1.1.1/",
    "http://0.0.0.1/",
    "HTTPS://127.0.0.1/",  # 大写 scheme——严格拒
    # 解析差异：authority 内反斜杠、URL 内空白
    "http://example.com\\@127.0.0.1/",
    "http://127.0.0.1\\@example.com/",
    "http://127.0.0.1/ x",
    "http://user @127.0.0.1/",  # authority 内空白
    "http://127.0.0.1 :8080/",
]

ALLOW = [
    "https://example.com/article",
    "http://example.com:8080/x?y=1#frag",
    "https://EXAMPLE.com/",
    "https://mp.weixin.qq.com/s/abcdef",
    "http://user@example.com/",  # userinfo + 公网 host → 放行
    "http://localhost.evil.com/",  # 非 *.localhost——DNS 归 engine 管
    "http://foo.lan.evil.com/",  # 非 *.lan 后缀——同归 DNS 层
    "http://example.com/%2f%2f",  # % 在 path 不在 authority → 放行
    # 公网字面 IP——边界外一格
    "http://8.8.8.8/",
    "http://1.2.3.4/",
    "http://11.0.0.1/",
    "http://126.0.0.1/",
    "http://100.63.255.255/",  # CGNAT 边界外一格
    "http://100.128.0.1/",
    "http://172.15.0.1/",
    "http://172.32.0.1/",
    "http://169.255.0.1/",
    "http://192.0.1.1/",  # 192.0.0/24 边界外
    "http://192.88.100.1/",  # 192.88.99/24 边界外
    "http://192.167.0.1/",
    "http://198.17.0.1/",  # 198.18/15 边界外两侧
    "http://198.20.0.1/",
    "http://223.255.255.255/",  # 组播边界外一格
    # 公网 v6 + mapped/ISATAP 公网
    "http://[2606:4700:4700::1111]/",
    "http://[2001:4860:4860::8888]/",
    "http://[::ffff:8.8.8.8]/",
    "http://[2001:db8::5efe:808:808]/",
    "http://[fe70::1]/",  # fe80/10 与 fec0/10 边界外
    # userinfo 中藏 IP 字面但真 host 公网 → 语义正确放行
    "http://127.0.0.1:8080@evil.com/",
]


def test_guard_reject_matrix():
    rcs = guard_rc(REJECT)
    for u in REJECT:
        assert rcs[u] == 2, f"should reject: {u} (rc={rcs[u]})"


def test_guard_allow_matrix():
    rcs = guard_rc(ALLOW)
    for u in ALLOW:
        assert rcs[u] == 0, f"should allow: {u} (rc={rcs[u]})"


def test_guard_reject_reports_stderr():
    r = subprocess.run(
        [BASH, "-c", 'source "$1"; _guard_url "$2"', "_", COMMON, "http://127.0.0.1/"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2
    assert "ssrf-guard" in r.stderr
    assert "127.0.0.1" in r.stderr


# --- e2e：本地 fixture 拒用（复刻原实测）--------------------------------------


@pytest.fixture
def live_http():
    """127.0.0.1 真起服务——证明被闸的是可达目标而非假阴性。"""
    d = tempfile.mkdtemp(prefix="ssrf-www-", dir=TMPBASE)
    with open(os.path.join(d, "a.html"), "w") as f:
        f.write("<html><body><h1>Title: secret intranet page</h1></body></html>")
    hits = []

    class H(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            super().do_GET()

        def log_message(self, *a):
            pass

    handler = functools.partial(H, directory=d)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield d, srv.server_address[1], hits
    srv.shutdown()
    srv.server_close()
    t.join(5)
    shutil.rmtree(d, ignore_errors=True)


def _env(home):
    e = dict(os.environ)
    e["LGC_HOME"] = home
    e["LGC_BIN"] = LGC
    e["LGC_CONFIG"] = os.path.join(home, "no-config")
    e.pop("LGC_OFF", None)
    e.pop("LGC_REFRESH", None)
    return e


@pytest.mark.parametrize("connector", [GENERIC, WECHAT, YOUTUBE])
def test_connector_rejects_loopback_e2e(connector, live_http):
    _, port, hits = live_http
    out = tempfile.mkdtemp(prefix="ssrf-out-", dir=TMPBASE)
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    try:
        r = subprocess.run(
            [connector, f"http://127.0.0.1:{port}/a.html", "-o", out],
            env=_env(home),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
        assert "ssrf-guard" in r.stderr
        assert glob.glob(os.path.join(out, "*.md")) == []
        assert hits == []  # 服务零命中——fetch 未发生
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_generic_rejects_bypass_forms_e2e(live_http):
    """dword/localhost 障眼同一服务同样拒。"""
    _, port, hits = live_http
    out = tempfile.mkdtemp(prefix="ssrf-out-", dir=TMPBASE)
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    try:
        for u in (
            f"http://2130706433:{port}/a.html",  # 127.0.0.1 dword
            f"http://localhost:{port}/a.html",
            f"http://evil@127.0.0.1:{port}/a.html",
        ):
            r = subprocess.run(
                [GENERIC, u, "-o", out],
                env=_env(home),
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert r.returncode == 2, f"{u}: {r.stdout}\n{r.stderr}"
        assert glob.glob(os.path.join(out, "*.md")) == []
        assert hits == []
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_outdir_file_collision_rc5():
    """-o 撞上已存在文件 → lg_args 显式拒 rc5（修前 mkdir 裸奔 rc1 无因）。"""
    d = tempfile.mkdtemp(prefix="out-coll-", dir=TMPBASE)
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    try:
        blocker = os.path.join(d, "plain-file")
        with open(blocker, "w") as f:
            f.write("x")
        r = subprocess.run(
            [GENERIC, "https://example.com/", "-o", blocker],
            env=_env(home),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 5, (r.stdout, r.stderr)
        assert blocker in r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)
