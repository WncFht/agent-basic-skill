# test_link_get.py — link-get dispatcher 回归：--mc 参数透传顺序 + 入口 host 闸（SSRF）
# + 旗标→param 域映射（variant/kind/enum 注入）。
# 闸实现 = connectors/_common.sh::_guard_url（link-get source 复用，单一实现）；
# REJECT/ALLOW 与 test_url_guard.py 同政策——inet_aton 全形态、v6 非规范/嵌入形、
# 反斜杠 authority 等对抗向量断言 rc2 + mock connector 零调用。
# Run: TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests/test_link_get.py -x -q
# 全 offline：connector 全 mock（被调时把名字+argv 追加到 $MOCK_OUT），临时目录在 ~/.cache（tmpfs /tmp 易满）。
#
# Phase-6d 壳瘦身（ARCH-FINAL §6）刻意变更，断言随之更新：
#   - 域名分发臂全删：engine 经 pack.toml [match]/bare_resolve 自路由——argv 不再
#     带 -p <pack>（唯 --media 仍强制 -p media）；断言改为核对裸 run+params。
#   - 裸 token（97882 / arxiv:ID / 裸 host / 裸 IP）直通 engine：bare_resolve →
#     canon → guard_url 在 engine 内裁决，壳不再「不是 URL」rc2。
#   - 未知 -* 旗标不再由壳白名单拒：一律 --param 透传，engine [params] 声明表
#     拒 rc2（含合法集报错）——rc2 执行面移入 engine。

import os
import shutil
import subprocess
import tempfile

import pytest

LINK_GET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts", "link-get")
)
TMPBASE = os.path.expanduser("~/.cache")

# mock connector：第一行记名字，之后每行一个 argv
MOCK = '#!/bin/bash\n{ basename "$0"; printf \'%s\\n\' "$@"; } >> "$MOCK_OUT"\n'

ZURL = "https://www.zhihu.com/question/12345/answer/67890"


@pytest.fixture
def rig():
    home = tempfile.mkdtemp(prefix="lg-dispatch-", dir=TMPBASE)
    bind = os.path.join(home, "bin")
    conn = os.path.join(home, "scripts", "connectors")
    os.makedirs(bind)
    os.makedirs(conn)
    # link-get 从自身真实路径解析 connectors/ → 拷进临时树替换
    lg = os.path.join(home, "scripts", "link-get")
    shutil.copy(LINK_GET, lg)
    os.chmod(lg, 0o755)
    # link-get source connectors/_common.sh 取 _guard_url → 拷真身（非 mock）；
    # _lgc.sh 一并拷：_common.sh 探测到就 source，与生产树同布局
    conn_real = os.path.join(os.path.dirname(LINK_GET), "connectors")
    for name in ("_common.sh", "_lgc.sh"):
        shutil.copy(os.path.join(conn_real, name), os.path.join(conn, name))
    # fetch-engine 是唯一分发路径（Phase-5d）：mock 在 scripts/ 同目录（非 PATH）
    eng = os.path.join(home, "scripts", "fetch-engine")
    with open(eng, "w") as f:
        f.write(
            '#!/bin/bash\n{ echo "fetch-engine"; printf \'%s\\n\' "$@"; } >> "$MOCK_OUT"\n'
        )
    os.chmod(eng, 0o755)
    # PATH mock：旁路依赖（zhihu-get --mc / canvas-get --download）
    for name in ("zhihu-get", "canvas-get"):
        p = os.path.join(bind, name)
        with open(p, "w") as f:
            f.write(MOCK)
        os.chmod(p, 0o755)
    env = dict(os.environ)
    env["PATH"] = bind + os.pathsep + env["PATH"]
    env["MOCK_OUT"] = os.path.join(home, "calls.txt")
    yield {"lg": lg, "env": env, "out": env["MOCK_OUT"], "home": home, "eng": eng}
    shutil.rmtree(home, ignore_errors=True)


def run(rig, *a):
    return subprocess.run(
        [rig["lg"], *a], env=rig["env"], capture_output=True, text=True, timeout=30
    )


def called(rig):
    """mock 被调 → [connector名, argv...]；未被调 → None"""
    if not os.path.exists(rig["out"]):
        return None
    with open(rig["out"]) as f:
        return [ln.rstrip("\n") for ln in f]


# --- A) --mc 旁路（非 fetch 管线，恒 exec zhihu-get；非知乎目标 rc2 拒）


def test_mc_url_before_flag(rig):
    """link-get <zhihu-url> --mc detail → zhihu-get --mc detail <url>"""
    r = run(rig, ZURL, "--mc", "detail")
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["zhihu-get", "--mc", "detail", ZURL]


def test_mc_flag_before_url(rig):
    """link-get --mc detail <zhihu-url>：TARGET 在 mc 尾部 → 借出路由，透传同序"""
    r = run(rig, "--mc", "detail", ZURL)
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["zhihu-get", "--mc", "detail", ZURL]


def test_mc_tail_verbatim_and_positionals_append(rig):
    """--mc 尾原样保留，link-get positionals 追加为 mc 目标"""
    u2 = "https://www.zhihu.com/p/99"
    r = run(rig, ZURL, "--mc", "detail", u2)
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["zhihu-get", "--mc", "detail", u2, ZURL]


def test_mc_nonzhihu_rejected(rig):
    """非知乎目标 + --mc（Phase-5d）：误用拒 rc2，engine/connector 均不被调"""
    u = "https://www.youtube.com/watch?v=x"
    r = run(rig, u, "--mc", "detail")
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert called(rig) is None


def test_mc_no_url_passthrough(rig):
    """link-get --mc search kw（尾部无 URL 形态）：整尾交 zhihu-get --mc"""
    r = run(rig, "--mc", "search", "kw")
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["zhihu-get", "--mc", "search", "kw"]


def test_plain_dispatch_via_engine(rig):
    """普通分发：zhihu --fast → engine 自路由（无 -p），壳注 fast+variant=+f"""
    r = run(rig, ZURL, "--fast")
    assert r.returncode == 0, r.stderr
    assert called(rig) == [
        "fetch-engine",
        "run",
        ZURL,
        "--param",
        "fast",
        "--param",
        "variant=+f",
    ]


# --- B) 入口 host 闸（policy = connectors/_common.sh::_guard_url，单一实现）

REJECT = [
    # 非 http(s) scheme / 畸形 / 空 authority / 空白
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://x/",
    "http://",
    "http:///path",
    "http://:8080/",
    "http://user@",
    "HTTPS://127.0.0.1/",  # 大写 scheme——严格拒
    "http://127.0.0.1/ x",  # URL 内空白
    # loopback——inet_aton 全形态（dword/短形/hex/octal/混合进制/FQDN 尾点）
    "http://127.0.0.1/",
    "https://127.0.0.1:8443/x",
    "http://127.1/",
    "http://127.0.1/",
    "http://127.0.0.1./",
    "http://2130706433/",
    "http://340282366920938463463374607431768211455/",  # >19 位 dword 溢出 int64 回绕 → 畸形拒
    "http://0x7f000001/",
    "http://0x7f.0.0.1/",
    "http://0x7f.1/",  # a.b 短形 hex——旧内联闸漏过
    "http://0x7f.0.1/",  # a.b.c 短形 hex——旧内联闸漏过
    "http://127.0x1/",  # 十进制+hex 混合——旧内联闸漏过
    "http://0177.0.0.1/",
    "http://0177.0.0.1./",
    "http://0/",
    "http://0.0.0.0/",
    "http://0.0.0.1/",
    # 畸形数字字面——fail-safe 拒（段溢出）
    "http://10.0.0.256/",
    "http://256.1.1.1/",
    # private / link-local
    "http://10.0.0.1/",
    "http://10.255.255.255/",
    "http://172.16.0.1/",
    "http://172.31.255.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/",
    # localhost / .local / .localhost / .internal（大小写 + FQDN 尾点）
    "http://localhost/",
    "http://LOCALHOST:8080/x",
    "http://LOCALHOST./",
    "http://foo.local/",
    "http://bar.localhost/",
    "http://nas.internal/",  # .internal——旧内联闸无此类，漏过
    "http://nas.lan/",  # .lan/.home/.arpa 本地后缀——round-3 补齐
    "http://gw.home/",
    "http://nas.home.arpa/",
    "http://home.arpa/",
    # userinfo 障眼不豁免（真 host 在最末 @ 之后）
    "http://user@127.0.0.1/",
    "http://u:p@10.1.1.1:8080/",
    "http://evil.com@127.0.0.1/",
    # 反斜杠 authority——旧内联闸漏过（WHATWG/curl 视 \ 为分隔符）
    "http://example.com\\@127.0.0.1/",
    "http://127.0.0.1\\@example.com/",
    # IPv6 字面：回环/未指定/link-local/ULA——含压缩/展开/大小写/裸形等非规范形
    "http://[::1]/",
    "http://[::1]:8080/",
    "http://[0:0:0:0:0:0:0:1]/",
    "http://[0::1]/",  # 非规范压缩——旧内联闸漏过
    "http://[00:0:0::0:1]/",
    "http://::1/",  # 裸 v6 无 bracket——旧内联闸按 host:port 误切
    "http://[::]/",
    "http://[fe80::1]/",
    "http://[fe80:0:0:0:0:0:0:1]/",
    "http://[FE80::1]/",
    "http://[febf::1]/",
    "http://[fd00::1]/",
    "http://[fc00::1]/",
    "http://[fdff::1]/",
    # v4 嵌入 v6：mapped/translated/compat/NAT64/6to4/ISATAP——旧内联闸无语义
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:7f00:1]/",
    "http://[0::ffff:127.0.0.1]/",  # 0:: 前缀变形——旧内联闸漏过
    "http://[::ffff:0:127.0.0.1]/",
    "http://[::ffff:0:7f00:1]/",
    "http://[::127.0.0.1]/",
    "http://[64:ff9b::127.0.0.1]/",
    "http://[64:ff9b::7f00:1]/",
    "http://[2002:7f00:1::]/",  # 6to4
    "http://[2002:a00:1::]/",
    "http://[2001:db8::5efe:7f00:1]/",  # ISATAP IID ::5efe:v4
    "http://[fe80::200:5efe:a00:1]/",  # ISATAP ::200:5efe:v4
    "http://[fe80::1%25eth0]/",  # zone id → 畸形拒
    "http://[v1.x::]/",  # IPvFuture → 畸形拒——旧内联闸漏过
    # CGNAT / benchmark / 多播 / 广播——round-2 起 _common.sh 全拒
    "http://100.64.0.1/",  # CGNAT（tailnet 段，真实内网）
    "http://100.105.212.52/",
    "http://198.18.0.1/",
    "http://198.19.255.1/",
    "http://224.0.0.1/",
    "http://239.255.255.255/",
    "http://255.255.255.255/",
    "http://240.0.0.1/",
    "http://192.0.0.1/",  # IETF protocol assignments
    "http://192.88.99.1/",  # 6to4 relay anycast 192.88.99/24
    # authority 含 % → 拒（%2f %2e 编码绕过；不解码、全拒）
    "http://127.0.0.1%2f.evil/",
    "http://%31%32%37%2e%30%2e%30%2e%31/",
    "http://%6c%6f%63%61%6c%68%6f%73%74/",
    # 非 ASCII host → 拒（IDNA/UTS46 归一绕过：全角点/全角数字/圈码）
    "http://127。0。0。1/",
    "http://１２７.０.０.１/",
    "http://①②⑦.0.0.1/",
    "http://ｌｏｃａｌｈｏｓｔ/",
    # NAT64 本地前缀 64:ff9b:1::/48 整段拒——含 /56 /64 /96 NSP 错位内嵌
    "http://[64:ff9b:1::7f00:1]/",
    "http://[64:ff9b:1::127.0.0.1]/",
    "http://[64:ff9b:1:0808:0808::7f00:1]/",  # /96 NSP 内嵌 127.0.0.1——/48 解码漏检
    "http://[64:ff9b:1:0808:0808::a00:1]/",
    "http://[64:ff9b:1:087f:0808:0100::]/",
    "http://[64:ff9b:1:808:808::]/",  # /48 解码会是公网——整段拒同拒
    "http://[fec0::1]/",
    "http://[ff02::1]/",
]

# 与 _common.sh 同政策（单一实现不漂）；rebinding/redirect 归 engine。
# 第二列 = engine 侧预期命中的 pack（文档锚——Phase-6d 起壳不再 -p 选 pack，
# 路由由 pack.toml [match] 决断；断言只核对 argv 直通、pack 列留作回归参照）。
ALLOW = [
    ("https://example.com/", "generic"),
    ("http://example.com:8080/x?y=1#frag", "generic"),
    ("http://8.8.8.8/", "generic"),  # 公网 IP 字面量放行
    ("http://1.2.3.4/", "generic"),
    ("http://11.0.0.1/", "generic"),  # 边界外一格
    ("http://126.0.0.1/", "generic"),
    ("http://172.15.0.1/", "generic"),
    ("https://172.32.0.1/", "generic"),  # 172.32 不在 172.16/12
    ("http://169.255.0.1/", "generic"),
    ("https://192.169.0.1/", "generic"),  # 不在 192.168/16
    ("http://100.63.255.255/", "generic"),  # CGNAT 边界外一格
    ("http://100.128.0.1/", "generic"),  # CGNAT 上界外
    ("http://198.17.255.1/", "generic"),  # benchmark 下界外
    ("http://198.20.0.1/", "generic"),  # benchmark 上界外
    ("http://223.255.255.1/", "generic"),  # 多播下界外
    ("http://127.0.0.1.evil.com/", "generic"),  # 主机名，DNS 层事
    ("http://localhost.evil.com/", "generic"),  # 非 *.localhost
    ("http://user@example.com/", "generic"),  # userinfo + 公网 host
    ("http://127.0.0.1:8080@evil.com/", "generic"),  # userinfo 藏 IP，真 host 公网
    ("http://[2606:4700::1]/", "generic"),  # 公网 v6
    ("http://[::ffff:8.8.8.8]/", "generic"),  # 公网 v4-mapped 放行
    ("http://[2001:db8::5efe:808:808]/", "generic"),  # ISATAP 公网
    ("https://www.zhihu.com/p/1", "zhihu"),
    ("https://zhuanlan.zhihu.com/c_1", "zhihu"),
    ("https://b23.tv/abc", "bilibili"),
    ("zhihu.com/p/1", "zhihu"),  # 裸串无 scheme：gate 放行给路由
]


@pytest.mark.parametrize("bad", REJECT)
def test_gate_rejects(rig, bad):
    r = run(rig, bad)
    assert r.returncode == 2, (bad, r.stdout, r.stderr)
    assert called(rig) is None


@pytest.mark.parametrize(("url", "pack"), ALLOW)
def test_gate_allows(rig, url, pack):
    # pack 列是 engine 侧预期路由的文档锚；壳 argv 已无 -p（Phase-6d）
    r = run(rig, url)
    assert r.returncode == 0, (url, r.stderr)
    assert called(rig) == ["fetch-engine", "run", url]


def test_gate_before_substring_route(rig):
    """闸在子串路由之前：内网 host + URL 内嵌平台子串也必须拒，connector 不得被调"""
    r = run(rig, "http://127.0.0.1/?u=zhihu.com")
    assert r.returncode == 2
    assert called(rig) is None


def test_gate_media(rig):
    """--media 同受闸：内网目标拒且 media-get 不被调"""
    r = run(rig, "--media", "http://127.0.0.1/v")
    assert r.returncode == 2
    assert called(rig) is None


def test_mc_tail_url_also_gated(rig):
    """--mc 尾部夹带的内网 URL 同样过闸（verify2 实锤绕过面）"""
    r = run(rig, ZURL, "--mc", "detail", "http://127.0.0.1/x")
    assert r.returncode == 2
    assert called(rig) is None


# --- C) engine 分发（唯一路径）：旗标 → --param 翻译 + 旁路；pack 选择归 engine


def test_eng_generic(rig):
    r = run(rig, "https://example.com/x")
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["fetch-engine", "run", "https://example.com/x"]


def test_eng_outdir_and_params(rig):
    r = run(
        rig, "https://example.com/x", "-o", "/tmp/o", "--refresh", "--cache-ttl", "60"
    )
    assert r.returncode == 0, r.stderr
    assert called(rig) == [
        "fetch-engine",
        "run",
        "https://example.com/x",
        "-o",
        "/tmp/o",
        "--param",
        "refresh",
        "--param",
        "cache_ttl=60",
    ]


def test_eng_media_forced(rig):
    u = "https://www.zhihu.com/p/1"
    r = run(rig, "--media", u)
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["fetch-engine", "run", u, "-p", "media"]


def test_eng_youtube_fast_kind(rig):
    u = "https://youtu.be/abc123XYZ_9"
    r = run(rig, u, "--fast")
    assert r.returncode == 0, r.stderr
    assert called(rig) == [
        "fetch-engine",
        "run",
        u,
        "--param",
        "fast",
        "--param",
        "kind=fast",
    ]


def test_eng_zhihu_variants(rig):
    """变体键按 connector zkey() 分支规则：answer +c/+f，p|question 仅 +f，其余无变体"""
    for url, flags, want in [
        (
            "https://www.zhihu.com/question/1/answer/2",
            ["--comments"],
            ["comments", "variant=+c"],
        ),
        (
            "https://www.zhihu.com/question/1/answer/2",
            ["--fast"],
            ["fast", "variant=+f"],
        ),
        (
            "https://www.zhihu.com/question/1/answer/2",
            ["--comments", "--fast"],
            ["comments", "fast", "variant=+c"],
        ),
        ("https://www.zhihu.com/p/9", ["--comments"], ["comments"]),
        ("https://www.zhihu.com/p/9", ["--fast"], ["fast", "variant=+f"]),
        ("https://www.zhihu.com/question/7", ["--fast"], ["fast", "variant=+f"]),
        ("https://www.zhihu.com/column/c_9", ["--fast"], ["fast"]),
        (
            "https://www.zhihu.com/column/c_9",
            ["--comments"],
            ["comments", "variant=+c"],
        ),
        # zhuanlan.zhihu.com/p/N 命中 p 臂（*/p/* 先于 *zhuanlan*）——comments
        # 按 art 语义忽略；zhuanlan 非 /p/ 路径仍走 col 臂（仅 +c）
        ("https://zhuanlan.zhihu.com/p/9", ["--comments"], ["comments"]),
        ("https://zhuanlan.zhihu.com/p/9", ["--fast"], ["fast", "variant=+f"]),
        (
            "https://zhuanlan.zhihu.com/c_9",
            ["--comments"],
            ["comments", "variant=+c"],
        ),
        ("https://zhuanlan.zhihu.com/c_9", ["--fast"], ["fast"]),
        ("https://www.zhihu.com/people/sb-1", ["--fast"], ["fast"]),
    ]:
        # fresh output file per case
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, url, *flags)
        assert r.returncode == 0, (url, r.stderr)
        c = called(rig)
        assert c[0] == "fetch-engine"
        assert c[1:3] == ["run", url]
        assert "-p" not in c  # 壳不选 pack——variant 注入仍是壳契约（key_params）
        params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
        assert params == want, (url, params)


def test_eng_canvas_enumerate_routes(rig):
    """canvas 枚举类 → engine kind=enum 臂（data lane）；--download 例外直连"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    for flags, want in [
        (["--list-courses"], ["list_courses", "kind=enum", "enum=courses"]),
        (["--files"], ["files", "kind=enum", "enum=files"]),
        (
            ["--announcements"],
            ["announcements", "kind=enum", "enum=announcements"],
        ),
        (
            ["--assignments"],
            ["assignments", "kind=enum", "enum=assignments"],
        ),
        (["--mint"], ["mint", "kind=enum", "enum=mint"]),
    ]:
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, u, *flags)
        assert r.returncode == 0, r.stderr
        c = called(rig)
        assert c[0] == "fetch-engine", (flags, c)
        assert c[1:3] == ["run", u]
        assert "-p" not in c  # enum=<x> 注入是壳契约；pack 选择归 engine [match]
        params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
        assert params == want, (flags, params)


def test_eng_bilibili_mint_kind(rig):
    """bilibili --mint → 壳注 kind=mint（锁 bili_mint meta-lane，永不落抓取臂）"""
    u = "https://www.bilibili.com/video/BV1xx411c7mD"
    r = run(rig, u, "--mint")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert c[1:3] == ["run", u]
    params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
    assert params == ["mint", "kind=mint"], params


def test_eng_canvas_download_bypass(rig):
    """--download（--files 配参、签名链须新鲜）恒直连 canvas-get，不经 engine"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    for flags in (["--download", "/tmp/d"], ["--files", "--download", "/tmp/d"]):
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, u, *flags)
        assert r.returncode == 0, r.stderr
        c = called(rig)
        assert c[0] == "canvas-get", (flags, c)


def test_canvas_download_canvas_get_env(rig):
    """CANVAS_GET env 覆盖旁路解析序（ARCH-FINAL §6：env > $CONN > PATH）"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    custom = os.path.join(rig["home"], "my-canvas-get")
    with open(custom, "w") as f:
        f.write(MOCK)
    os.chmod(custom, 0o755)
    env = dict(rig["env"])
    env["CANVAS_GET"] = custom
    r = subprocess.run(
        [rig["lg"], u, "--download", "/tmp/d"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "my-canvas-get", c


def test_eng_canvas_list_courses_no_target(rig):
    """裸 --list-courses 无课程目标 → 补 sjtu 占位 TARGET 进枚举臂（删了会回归）"""
    r = run(rig, "--list-courses")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert c[1:3] == ["run", "https://oc.sjtu.edu.cn/"]
    assert "-p" not in c
    params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
    assert params == ["list_courses", "kind=enum", "enum=courses"], params


def test_eng_canvas_enum_backfill_extended(rig):
    """Phase-6d：占位 backfill 扩到全部枚举旗标（ARCH-FINAL §6 enum/placeholder
    段列明 --list-courses/--files/--announcements/--assignments）——裸 --files
    也补 sjtu 占位 TARGET + kind=enum enum=files；课程缺席由 canvas-rest lane
    notcovered 报错（rc 面在 engine/lane，壳不再 usage rc2）"""
    r = run(rig, "--files")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert c[1:3] == ["run", "https://oc.sjtu.edu.cn/"]
    params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
    assert params == ["files", "kind=enum", "enum=files"], params


def test_bare_tokens_passthrough(rig):
    """Phase-6d 刻意变更：裸 token 不再壳层「不是 URL」rc2——直通 engine，
    bare_resolve（canvas \\d{4,6}→课程 URL、arxiv:→abs URL）→ canon → guard_url
    在 engine 内裁决。裸 IP 同路：实测 engine「no pack covers 127.0.0.1」rc3
    （canon 的 host 形补 https 规则要求字母 TLD，数字尾不落 URL——SSRF 不回归）"""
    for tok in ("97882", "arxiv:1234.5678", "zhihu.com/p/1", "127.0.0.1"):
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, tok)
        assert r.returncode == 0, (tok, r.stderr)
        assert called(rig) == ["fetch-engine", "run", tok], tok


def test_bare_canvas_id_flags_passthrough(rig):
    """裸课程号 + 枚举旗标：壳域名臂不认 97882（非 sjtu host）→ 只透传布尔
    回波，不注 kind=enum——enum 派生归 routes/canvas-rest lane（6d 修复前
    裸 ID+--files 静默打讲次表）。"""
    for flags, want in [
        (["--files"], ["files"]),
        (["--mint"], ["mint"]),
        (["--list-courses"], ["list_courses"]),
    ]:
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, "97882", *flags)
        assert r.returncode == 0, r.stderr
        c = called(rig)
        assert c[0] == "fetch-engine", (flags, c)
        assert c[1:3] == ["run", "97882"]
        params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
        assert params == want, (flags, params)


def test_bare_canvas_id_download_goes_engine(rig):
    """裸课程号 + --download：旁路 case 只认 sjtu host——97882 直通 engine，
    bare_resolve 落 canvas pack → routes 漏过 download="" 闸 → monolith
    真下载（与旁路平价）。"""
    r = run(rig, "97882", "--download", "/tmp/d")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine", c
    assert c[1:3] == ["run", "97882"]
    params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
    assert params == ["download=/tmp/d"], params


def test_media_token_export_before_exec(rig):
    """--media --token X：CANVAS_TOKEN 导出在 media exec 之前（6d 修复前
    导出排在 eng_run media 之后，此形态丢凭证）。"""
    with open(rig["eng"], "w") as f:
        f.write(
            '#!/bin/bash\n{ echo "fetch-engine"; echo "CT=$CANVAS_TOKEN";'
            ' printf \'%s\\n\' "$@"; } >> "$MOCK_OUT"\n'
        )
    r = run(rig, "https://oc.sjtu.edu.cn/courses/42", "--media", "--token", "sekrit-m")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine", c
    assert "CT=sekrit-m" in c, c


def test_eng_canvas_token_env(rig):
    """--token 不进 --param，走 CANVAS_TOKEN env（凭证不进 argv/journal）"""
    if os.path.exists(rig["out"]):
        os.unlink(rig["out"])
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--token", "sekrit-pat")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert not any("sekrit" in x for x in c), c
    assert rig["env"].get("CANVAS_TOKEN") is None or "CANVAS_TOKEN" not in " ".join(c)


def test_eng_mc_bypass(rig):
    """--mc 永远走旧路径（枚举/搜索非 fetch 管线）"""
    r = run(rig, ZURL, "--mc", "detail")
    assert r.returncode == 0, r.stderr
    assert called(rig) == ["zhihu-get", "--mc", "detail", ZURL]


def test_eng_missing_hard_error(rig):
    """fetch-engine 不可执行（Phase-5d 无回退路径）→ rc2 + stderr 提示"""
    os.chmod(rig["eng"], 0o644)
    r = run(rig, "https://example.com/x")
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "不可执行" in r.stderr
    assert called(rig) is None


# --- D) 对抗验证补丁回归（Phase-5 verify）


def test_token_equals_form_no_leak(rig):
    """--token=PAT 等号形：PAT 走 CANVAS_TOKEN env 不进 ENG_P——
    掉进 -* 臂就成 journal 里的明文凭证（verify 实锤泄漏面）"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--token=sekrit-eq")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert not any("sekrit" in x for x in c), c


def test_token_equals_form_canvas_download_verbatim(rig):
    """--download 旁路：--token 剥出 argv（CANVAS_TOKEN env 已导出——
    PAT 晾 /proc cmdline 世界可读，评审实锤泄漏面）"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--download", "/tmp/d", "--token=sekrit-eq")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "canvas-get", c
    assert not any("sekrit" in x for x in c), c
    assert "--token" not in c


def test_download_bypass_token_via_env(rig):
    """旁路 argv 无 token 时 auth 由 CANVAS_TOKEN env 保——canvas-get
    优先级 --token>env>file，env 链必须真通"""
    cget = os.path.join(rig["env"]["PATH"].split(os.pathsep)[0], "canvas-get")
    with open(cget, "w") as f:
        f.write(
            '#!/bin/bash\n{ basename "$0"; echo "CT=$CANVAS_TOKEN";'
            ' printf \'%s\\n\' "$@"; } >> "$MOCK_OUT"\n'
        )
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--download", "/tmp/d", "--token", "sekrit-env")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert "CT=sekrit-env" in c, c
    assert not any("sekrit-env" in x for x in c if x != "CT=sekrit-env"), c


def test_canvas_download_bypass_needs_no_engine(rig):
    """engine 缺席不连坐旁路：--download 是签名链新鲜性契约，恒直连 canvas-get"""
    os.chmod(rig["eng"], 0o644)
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--files", "--download", "/tmp/d")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "canvas-get", c


def test_unknown_flag_passthrough(rig):
    """Phase-6d 刻意变更：壳白名单退役——未知 -* 旗标一律 --param 透传，rc2 由
    engine [params] 声明表执行（未知 param 报合法集拒）。此断言核对透传形态；
    mock engine 不校验 param，rc2 覆盖见 engine 侧 params 闸测试"""
    r = run(rig, "https://example.com/x", "--bogus-flag")
    assert r.returncode == 0, r.stderr
    assert called(rig) == [
        "fetch-engine",
        "run",
        "https://example.com/x",
        "--param",
        "bogus_flag",
    ]


def test_valued_flag_equals_form(rig):
    """--flag=v 形带值旗标同样进 ENG_P（与两参形同语义）"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--lecture=3")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert "lecture=3" in c, c


# --- E) 评审修复面回归（等号形/host 边界/互斥/凭证剥离）


def test_mc_host_boundary_rejects_evil_suffix(rig):
    """--mc host 边界：zhihu.com.evil.com 子串命中不再放行进旁路"""
    r = run(rig, "https://zhihu.com.evil.com/x", "--mc", "detail")
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert called(rig) is None


def test_mc_host_boundary_subdomains_ok(rig):
    """合法知乎 host 全谱系仍放：www/zhuanlan/裸 zhihu.com"""
    for u in (
        "https://www.zhihu.com/question/1",
        "https://zhuanlan.zhihu.com/p/1",
        "https://zhihu.com/p/1",
    ):
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, u, "--mc", "detail")
        assert r.returncode == 0, (u, r.stderr)
        assert called(rig)[0] == "zhihu-get", u


def test_sjtu_bypass_host_boundary(rig):
    """oc.sjtu.edu.cn.evil.com 不进 --download 旁路——落 engine 真路由"""
    u = "https://oc.sjtu.edu.cn.evil.com/courses/42"
    r = run(rig, u, "--download", "/tmp/d")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine", c  # 旁路只吃真 sjtu host


def test_sjtu_bare_host_download_bypass(rig):
    """无 scheme 的 sjtu host/path 仍命中旁路（剥 scheme 后比对）"""
    r = run(rig, "oc.sjtu.edu.cn/courses/42", "--download", "/tmp/d")
    assert r.returncode == 0, r.stderr
    assert called(rig)[0] == "canvas-get"


def test_canvas_get_not_executable_rc2(rig):
    """CANVAS_GET 指到不可执行文件 → rc2 而非 exec 空跑"""
    dead = os.path.join(rig["home"], "dead-canvas-get")
    with open(dead, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(dead, 0o644)
    env = dict(rig["env"])
    env["CANVAS_GET"] = dead
    r = subprocess.run(
        [rig["lg"], "https://oc.sjtu.edu.cn/courses/42", "--download", "/tmp/d"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "不可执行" in r.stderr


def test_enum_flags_mutex(rig):
    """枚举/铸凭证旗标互斥：混用 rc2 拒（注入胜负靠数组序是掷骰）"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    for flags in (["--files", "--mint"], ["--files", "--announcements"]):
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, u, *flags)
        assert r.returncode == 2, (flags, r.returncode)
        assert "互斥" in r.stderr
        assert called(rig) is None


def test_download_plus_enum_flag_not_mutex(rig):
    """--files --download 是配参组合不是互斥——仍进旁路"""
    r = run(rig, "https://oc.sjtu.edu.cn/courses/42", "--files", "--download", "/tmp/d")
    assert r.returncode == 0, r.stderr
    assert called(rig)[0] == "canvas-get"


def test_output_equals_forms(rig):
    """-o=dir / --output=dir 等号形归一——不落 --param o= 静默失效"""
    for flag in ("-o=/tmp/eq1", "--output=/tmp/eq2"):
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, "https://example.com/x", flag)
        assert r.returncode == 0, (flag, r.stderr)
        c = called(rig)
        assert c[0] == "fetch-engine"
        want = flag.split("=", 1)[1]
        i = c.index("-o")
        assert c[i + 1] == want, c
        assert not any(v.startswith("o=") or v.startswith("output=") for v in c), c


def test_comments_fast_equals_forms(rig):
    """等号形布尔：真值同裸旗语义（注 variant），假值透传不注"""
    for flag, want in [
        ("--comments=0", ["comments=0"]),
        ("--comments=yes", ["comments=yes", "variant=+c"]),
        ("--fast=0", ["fast=0"]),
        ("--fast=1", ["fast=1", "variant=+f"]),
    ]:
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, ZURL, flag)
        assert r.returncode == 0, (flag, r.stderr)
        c = called(rig)
        params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
        assert params == want, (flag, params)


def test_media_equals_forms(rig):
    """--media=v：真值强注 -p media，假值走普通分发"""
    u = "https://www.youtube.com/watch?v=x"
    r = run(rig, u, "--media=0")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    assert c[0] == "fetch-engine"
    assert "-p" not in c, c
    if os.path.exists(rig["out"]):
        os.unlink(rig["out"])
    r = run(rig, u, "--media=yes")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    i = c.index("-p")
    assert c[i + 1] == "media", c


def test_budget_ms_flag_not_param(rig):
    """--budget-ms 是 engine 旗标——落 -* 臂变 --param budget_ms 就静默失效"""
    for form in (["--budget-ms", "5000"], ["--budget-ms=5000"]):
        if os.path.exists(rig["out"]):
            os.unlink(rig["out"])
        r = run(rig, "https://example.com/x", *form)
        assert r.returncode == 0, (form, r.stderr)
        c = called(rig)
        i = c.index("--budget-ms")
        assert c[i + 1] == "5000", c
        assert not any(v.startswith("budget_ms") for v in c), c


def test_dash_value_equals_form_preserves_value(rig):
    """-* 臂等号形：dash→underscore 只作用键名——值里的 - 不吃"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--cover-at=1:30")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
    assert params == ["cover_at=1:30"], params


def test_valued_flag_space_form(rig):
    """--lecture 3 空格形与 --lecture=3 等价（带值兼容表：进 ENG_P + ARGS）"""
    u = "https://oc.sjtu.edu.cn/courses/42"
    r = run(rig, u, "--lecture", "3")
    assert r.returncode == 0, r.stderr
    c = called(rig)
    params = [c[i + 1] for i, v in enumerate(c) if v == "--param"]
    assert params == ["lecture=3"], params
