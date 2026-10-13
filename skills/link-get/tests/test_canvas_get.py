# test_canvas_get.py — canvas-get 错误分层契约（全离线：本地 http.server 桩 +
# 进程内 stub，零外网、不读真实凭证文件）。Run:
#   uv run --with pytest pytest skills/link-get/tests -x -q
#
# 分层契约（Phase0 缺陷 #3 + fetch-arch/evidence/errtax.txt）：
#   401/403 → stderr 'PAT 失效或权限不足' + exit 5，绝不渲染 '共 0 门'
#   其他非 200（404/5xx）→ None：files/ann/assign 容忍"未开放"，
#     list-courses/donor 改为显性 die5（不再是成功假象/空 errs 报错）
#   200 + [] 真空列表 → 原 '共 0 门' 输出保留
#   URLError/超时/连接重置等网络层异常 → 干净 stderr 一行 + exit 5，
#     无 Traceback（原为 exit 1 + 裸栈）

import importlib.machinery
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "connectors", "canvas-get"
)

# 代理环境变量会让 urllib 把 127.0.0.1 桩请求也交给代理——全剥保证离线确定性
_PROXY_VARS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "no_proxy",
    "NO_PROXY",
)


class _StubHandler(BaseHTTPRequestHandler):
    """单端点桩：全部请求回同一 status/body，逐用例经 set_resp 调整。
    last_path 记录最近请求路径（含 query），供 '//api/v1' 类断言用。"""

    status = 200
    body = b"[]"
    last_path = None

    def _serve(self):
        _StubHandler.last_path = self.path
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        if self.body:
            self.wfile.write(self.body)

    do_GET = _serve  # noqa: N815  # BaseHTTPRequestHandler 钩子名固定
    do_POST = _serve  # noqa: N815  # BaseHTTPRequestHandler 钩子名固定

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_api():
    """本地 REST 桩 → (base_url, set_resp)；set_resp(status, body) 逐用例调。"""
    _StubHandler.status = 200
    _StubHandler.body = b"[]"
    _StubHandler.last_path = None
    srv = HTTPServer(("127.0.0.1", 0), _StubHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    def set_resp(status, body=b"[]"):
        _StubHandler.status = status
        _StubHandler.body = body

    yield f"http://127.0.0.1:{srv.server_port}", set_resp
    srv.shutdown()
    srv.server_close()
    t.join(timeout=5)


def _run(args, base=None):
    env = dict(os.environ)
    env["CANVAS_TOKEN"] = "test-token"  # 不碰 ~/.config/canvas-skill/token
    env["LGC_OFF"] = "1"  # 缓存全绕 = 裸行为，与 lgc 是否安装无关
    for v in _PROXY_VARS:
        env.pop(v, None)
    if base:
        env["CANVAS_OC_BASE"] = base
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _closed_port_base():
    """绑定即放的端口几乎必然拒绝连接 → URLError 确定性触发。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def _load():
    """canvas-get 无 .py 后缀，走 SourceFileLoader 进程内加载。"""
    loader = importlib.machinery.SourceFileLoader("canvas_get", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# --- 端到端：真实 urllib 栈打到本地桩 ------------------------------------------


def test_401_list_courses_auth_expired(stub_api):
    """PAT 过期：exit 5 + 'PAT 失效或权限不足'，绝不渲染 '共 0 门'。"""
    base, set_resp = stub_api
    set_resp(401, b'{"status":"unauthorized"}')
    r = _run(["--list-courses"], base)
    assert r.returncode == 5
    assert "共 0 门" not in r.stdout + r.stderr
    assert "PAT 失效或权限不足" in r.stderr
    assert "Traceback" not in r.stderr


def test_403_list_courses_auth_expired(stub_api):
    base, set_resp = stub_api
    set_resp(403, b'{"status":"forbidden"}')
    r = _run(["--list-courses"], base)
    assert r.returncode == 5
    assert "共 0 门" not in r.stdout + r.stderr
    assert "PAT 失效或权限不足" in r.stderr


def test_200_empty_courses_keeps_output(stub_api):
    """真空列表（200 + []）保留原 '共 0 门' 输出、exit 0。"""
    base, set_resp = stub_api
    set_resp(200, b"[]")
    r = _run(["--list-courses"], base)
    assert r.returncode == 0
    assert "共 0 门" in r.stderr


def test_500_list_courses_not_fake_empty(stub_api):
    """5xx 也是 None ≠ 真空：显性 die5，不出 '共 0 门'。"""
    base, set_resp = stub_api
    set_resp(500, b"oops")
    r = _run(["--list-courses"], base)
    assert r.returncode == 5
    assert "共 0 门" not in r.stdout + r.stderr
    assert "课程列表拉取失败" in r.stderr


def test_404_files_tolerated_as_unopened(stub_api):
    """404 = 文件区未开放/课程不存在：容忍空结果语义保留、exit 0。"""
    base, set_resp = stub_api
    set_resp(404, b"")
    r = _run(["97882", "--files"], base)
    assert r.returncode == 0
    assert "该课程未开放文件区或无文件" in r.stderr
    assert "PAT 失效" not in r.stderr


def test_401_files_auth_expired(stub_api):
    """files 子命令同样走 auth_expired 分层。"""
    base, set_resp = stub_api
    set_resp(401)
    r = _run(["97882", "--files"], base)
    assert r.returncode == 5
    assert "PAT 失效或权限不足" in r.stderr
    assert "该课程未开放文件区或无文件" not in r.stderr


def test_urlerror_clean_exit5_no_traceback():
    """连不上的端口 → URLError：干净 stderr + exit 5，无 traceback（原 exit1）。"""
    r = _run(["--list-courses"], _closed_port_base())
    assert r.returncode == 5
    assert "Traceback" not in r.stderr
    assert "共 0 门" not in r.stdout + r.stderr
    assert "网络错误" in r.stderr


# --- 单元：canvas_api / donor_token 的 None 分层 --------------------------------


def test_canvas_api_status_layering(monkeypatch):
    mod = _load()
    monkeypatch.setenv("LGC_OFF", "1")
    sess = mod.Session("tok")
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (200, {}, b"[]"))
    assert mod.canvas_api(sess, "/courses") == []
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (404, {}, b""))
    assert mod.canvas_api(sess, "/courses/1/files") is None
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (200, {}, b"<html>"))
    assert mod.canvas_api(sess, "/courses") is None  # 解码失败同层 None
    for code in (401, 403):
        monkeypatch.setattr(mod, "http", lambda *_a, code=code, **_k: (code, {}, b"{}"))
        with pytest.raises(SystemExit) as ei:
            mod.canvas_api(sess, "/courses")
        assert ei.value.code == 5


def test_donor_list_source_dead_dies_clean(monkeypatch):
    """donor 扫描的 /courses 源挂了：显性 die5，不是 '所有课程 launch 均失败'。"""
    mod = _load()
    monkeypatch.setenv("LGC_OFF", "1")
    sess = mod.Session("tok")
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (500, {}, b""))
    with pytest.raises(SystemExit) as ei:
        mod.donor_token(sess)
    assert ei.value.code == 5


def test_main_wraps_urlerror(monkeypatch, capsys):
    """main() 兜底：URLError → die5 干净一行，无 traceback。"""
    mod = _load()
    monkeypatch.setenv("LGC_OFF", "1")
    monkeypatch.setenv("CANVAS_TOKEN", "t")
    monkeypatch.setattr(sys, "argv", ["canvas-get", "--list-courses"])

    def boom(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod, "http", boom)
    with pytest.raises(SystemExit) as ei:
        mod.main()
    assert ei.value.code == 5
    err = capsys.readouterr().err
    assert "网络错误" in err
    assert "Traceback" not in err


# --- Phase0 二轮：200+错形 JSON 穿透分层 + CANVAS_OC_BASE 尾斜杠 ----------------


@pytest.mark.parametrize(
    "body",
    [
        b'{"courses": []}',  # dict 包裹：顶层非 list → shape 归一 None → die5
        b'"oops"',  # JSON 字符串 → 同上
        b"42",  # JSON 数字 → 同上
        b"null",  # JSON null（合法 JSON 非法 shape）→ 同上
        b"[1, 2, 3]",  # 顶层是 list 但元素非 dict → 穿透 → main() 兜底 die5
    ],
    ids=["dict-wrap", "string", "number", "null", "non-dict-elems"],
)
def test_200_malformed_body_list_courses(stub_api, body):
    """五种错形 body：rc5 + 无 Traceback + 无 '共 0 门' 成功假象。
    前四种走 canvas_api shape→None→显性 die；末种穿透顶层 shape，
    靠 main() except Exception 最后保险收口——两路殊途同归。"""
    base, set_resp = stub_api
    set_resp(200, body)
    r = _run(["--list-courses"], base)
    assert r.returncode == 5
    assert "Traceback" not in r.stderr
    assert "共 0 门" not in r.stdout + r.stderr
    assert "课程列表拉取失败" in r.stderr or "内部错误" in r.stderr


def test_200_malformed_files_tolerated_as_unopened(stub_api):
    """files 的 200 错形同 None 层：容忍'未开放'语义、rc0 无 traceback。"""
    base, set_resp = stub_api
    set_resp(200, b'{"files": []}')
    r = _run(["97882", "--files"], base)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr
    assert "该课程未开放文件区或无文件" in r.stderr


def test_oc_base_trailing_slash_normalized(stub_api):
    """CANVAS_OC_BASE 带尾斜杠 → 请求路径不得出现 '//api/v1'（rstrip('/')）。"""
    base, set_resp = stub_api
    set_resp(200, b"[]")
    r = _run(["--list-courses"], base + "/")
    assert r.returncode == 0
    assert _StubHandler.last_path is not None
    assert _StubHandler.last_path.startswith("/api/v1/courses")
    assert not _StubHandler.last_path.startswith("//")


def test_canvas_api_shape_layering(monkeypatch):
    """expect=list/dict 顶层 shape：类型不符 → None（同解码失败层）；符 → 原样。"""
    mod = _load()
    monkeypatch.setenv("LGC_OFF", "1")
    sess = mod.Session("tok")
    for body in (b'{"courses":[]}', b'"s"', b"42", b"null"):
        monkeypatch.setattr(mod, "http", lambda *_a, body=body, **_k: (200, {}, body))
        assert mod.canvas_api(sess, "/courses", expect=list) is None
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (200, {}, b'[{"id":1}]'))
    assert mod.canvas_api(sess, "/courses", expect=list) == [{"id": 1}]
    # sessionless_launch 期望 dict：list body → None（→ LtiError 干净报错）
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (200, {}, b"[1]"))
    assert mod.canvas_api(sess, "/x/sessionless_launch", expect=dict) is None
    monkeypatch.setattr(mod, "http", lambda *_a, **_k: (200, {}, b'{"url":"u"}'))
    assert mod.canvas_api(sess, "/x/sessionless_launch", expect=dict) == {"url": "u"}


def test_main_wraps_unexpected_exception(monkeypatch, capsys):
    """main() 最后保险：穿透分层的非网络异常（错形元素的 AttributeError 等）
    → 干净 stderr + exit5，无 traceback；die() 的 SystemExit 不被吞。"""
    mod = _load()
    monkeypatch.setenv("LGC_OFF", "1")
    monkeypatch.setenv("CANVAS_TOKEN", "t")
    monkeypatch.setattr(sys, "argv", ["canvas-get", "--list-courses"])
    # 顶层 shape 合法（list）但元素非 dict：穿透 canvas_api 归一，靠 main 兜底
    monkeypatch.setattr(mod, "canvas_api", lambda *_a, **_k: [1, 2, 3])
    with pytest.raises(SystemExit) as ei:
        mod.main()
    assert ei.value.code == 5
    err = capsys.readouterr().err
    assert "内部错误" in err
    assert "Traceback" not in err
