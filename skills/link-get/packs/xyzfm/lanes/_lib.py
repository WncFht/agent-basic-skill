#!/usr/bin/env python3
"""_lib.py — xyzfm pack 原生 lane 共享助手（Lane ABI v1，references/lane-abi.md）。

- stdin：恰好一行 JSON {job_id, identity:{raw,key,kind,params}, ctx:{artifact_dir,
  journal_dir,budget_ms,cred_handle,key}}。
- stdout：JSONL —— progress / artifact / 终态 result|data|error 恰好一条。
- rc10 + 无终态行 = 静默跳过；产物只写 ctx.artifact_dir 内（mint lane 例外，
  writes_cred 授权写 cred store）。
- 凭证纪律：token.json 只读/写文件本体，值永不进 argv/stdout/journal（stat/指
  纹层语义照 canvas_mint 平价）。

私有 API 面（2026-09 实测）：
- app 头套缺一不可：os/os-version/manufacturer/model/applicationid/
  app-version/app-buildno/UA/x-jike-device-id/local-time——缺 device-id →
  {"code":1,"rpc_error"} HTTP400；缺 token → openresty 401。
- POST api.xiaoyuzhoufm.com/v1/episode-transcript/get {eid,mediaId}
  → {data:{key,transcriptUrl,highlightUrl,vendorDeclaration}}
- GET transcriptUrl（transcript.xyzcdn.net 签名链，UA 必须 Xiaoyuzhou/* 安卓形，
  否则 CDN ACL 拒）→ gzip JSON [{text,startMs}]
- POST api.xiaoyuzhoufm.com/app_auth_tokens.refresh（x-jike-refresh-token 头）
  → 新 token 在响应头 x-jike-access-token/x-jike-refresh-token
- QR 铸凭证：POST web-api.xiaoyuzhoufm.com/v1/auth/qrcode/create
  {clientId:"xyz-web"} + x-midway-app-id → 轮询 /v1/auth/qrcode/login {id}
  → USED 时 token 在响应头。
"""

import gzip
import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

API = "https://api.xiaoyuzhoufm.com"
WEB_API = "https://web-api.xiaoyuzhoufm.com"
MIDWAY_APP_ID = "v6worU4NnWyL"  # accounts.xiaoyuzhoufm.com 登录 JS 内嵌常量
CDN_UA = "Xiaoyuzhou/2.99.1(android 28)"
PAGE_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
TOKEN_PATH = Path("~/.config/xyzfm/token.json").expanduser()

EID_RE = re.compile(r"/episode/([0-9a-fA-F]{24})")
PID_RE = re.compile(r"/podcast/([0-9a-fA-F]{24})")
CDN_HOSTS = (".xyzcdn.net", ".xiaoyuzhoufm.com")
NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


# ---------------------------------------------------------------- ABI 面


def read_req():
    """读 stdin 单行 JSON 请求（engine 写完一行即关 stdin）。"""
    return json.loads(sys.stdin.readline())


def emit(ev):
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def eprint(msg):
    """stderr 自由文本副通道（runner 收进 <lane>.stderr.log）。"""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def progress(msg, **kw):
    emit({"type": "progress", "msg": msg, **kw})


def artifact(path, name):
    emit({"type": "artifact", "path": str(path), "name": name})


def result(items, params=None):
    ev = {"type": "result", "items": items}
    if params:
        ev["params"] = params
    emit(ev)


def data(payload):
    emit({"type": "data", "payload": payload})


def error(cls, evidence, retryable=False, retry_after=None, **kw):
    ev = {
        "type": "error",
        "class": cls,
        "evidence": evidence,
        "retryable": bool(retryable),
    }
    if retry_after is not None:
        ev["retry_after"] = retry_after
    ev.update(kw)
    emit(ev)


def die(cls, evidence, retryable=False, **kw):
    """终态 error + rc0 —— 终态行优先于 rc，runner 不再合成 lane_crash。"""
    eprint(evidence)
    error(cls, evidence, retryable=retryable, **kw)
    sys.exit(0)


def skip(msg=""):
    """dep 缺席/形状不覆盖静默跳过：无终态行 + rc10。"""
    if msg:
        eprint(msg)
    sys.exit(10)


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def budget_s(ctx, reserve_ms=2000):
    """预算秒数（留 reserve 给收尾输出）。"""
    try:
        return max(5.0, (int(ctx.get("budget_ms") or 60000) - reserve_ms) / 1000)
    except (TypeError, ValueError):
        return 58.0


# ---------------------------------------------------------------- 凭证面


def load_token(path=TOKEN_PATH):
    """token.json → dict 或 None（缺文件/坏 JSON/缺字段一律按无凭证处理）。"""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict) or not d.get("access_token"):
        return None
    return d


def device_id(tok=None):
    """device_id 持久化在 token.json；全新铸造时生成 uuid 落盘。"""
    if tok and tok.get("device_id"):
        return tok["device_id"]
    return str(uuid.uuid4())


def _local_time():
    """local-time 头：ISO 毫秒 +0800（app 抓包形）。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}+0800"


def app_headers(did, access=None, refresh=None):
    """小宇宙 app 头套——缺一即 401/rpc_error，勿裁。"""
    h = {
        "os": "android",
        "os-version": "28",
        "manufacturer": "Xiaomi",
        "model": "MI 6",
        "applicationid": "app.podcast.cosmos",
        "app-version": "2.99.1",
        "app-buildno": "1362",
        "User-Agent": CDN_UA,
        "x-jike-device-id": did,
        "local-time": _local_time(),
        "content-type": "application/json",
    }
    if access:
        h["x-jike-access-token"] = access
    if refresh:
        h["x-jike-refresh-token"] = refresh
    return h


# ---------------------------------------------------------------- HTTP 面


class HttpFail(Exception):
    """status/理由成对带出，调用方映射 class。"""

    def __init__(self, status, body=b""):
        self.status = status
        self.body = body[:300] if isinstance(body, bytes) else str(body)[:300]
        super().__init__(f"HTTP {status}")


def http_get(url, headers=None, timeout=20.0, gunzip=False):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": PAGE_UA})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
    except urllib.error.HTTPError as e:
        raise HttpFail(e.code, e.read() if e.fp else b"")
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        http.client.HTTPException,
        ValueError,
        EOFError,
    ) as e:
        # IncompleteRead/gzip 截断/坏 URL 全是暂性面——归一进 HttpFail 分类
        raise HttpFail(-1, str(e).encode())
    if gunzip:
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError):
            pass  # 服务端可能已解压/未压缩——按原样解析
    return raw


def http_post(url, obj, headers, timeout=20.0):
    """POST JSON → (status, resp_headers, body)。resp_headers 是 HTTPMessage
    （大小写不敏感 .get）——x-jike-* 在头不在体，dict() 化会丢大小写语义。"""
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read() if e.fp else b""
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        http.client.HTTPException,
        ValueError,
        EOFError,
    ) as e:
        return -1, {}, str(e).encode()


# ---------------------------------------------------------------- 页面/转写面


def eid_of(raw):
    """engine match_scope=path 平价：query/fragment 不参与匹配——
    ?next=/episode/<eid> 类注入不得劫持分支。"""
    s = re.split(r"[?#]", raw or "", maxsplit=1)[0]
    m = EID_RE.search(s)
    return m.group(1).lower() if m else ""


def pid_of(raw):
    s = re.split(r"[?#]", raw or "", maxsplit=1)[0]
    m = PID_RE.search(s)
    return m.group(1).lower() if m else ""


def next_data(url, timeout=20.0):
    """页面 → __NEXT_DATA__ JSON。HttpFail 直通给调用方分类。"""
    raw = http_get(url, timeout=timeout)
    html = raw.decode("utf-8", errors="replace")
    m = NEXT_RE.search(html)
    if not m:
        raise HttpFail(0, b"no __NEXT_DATA__")
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise HttpFail(0, f"bad __NEXT_DATA__: {e}".encode())


def fetch_episode(eid, timeout=20.0):
    """episode 页 → props.pageProps.episode dict；缺席返回 None 由调用方判。"""
    nd = next_data(f"https://www.xiaoyuzhoufm.com/episode/{eid}", timeout)
    if not isinstance(nd, dict):
        raise HttpFail(0, b"__NEXT_DATA__ not a JSON object")
    ep = ((nd.get("props") or {}).get("pageProps") or {}).get("episode")
    return ep if isinstance(ep, dict) else None


def fetch_podcast(pid, timeout=20.0):
    nd = next_data(f"https://www.xiaoyuzhoufm.com/podcast/{pid}", timeout)
    if not isinstance(nd, dict):
        raise HttpFail(0, b"__NEXT_DATA__ not a JSON object")
    pp = (nd.get("props") or {}).get("pageProps") or {}
    pod = pp.get("podcast")
    if isinstance(pod, dict):
        return pod, pod.get("episodes") or []
    return None, []


def media_id_of(ep):
    """transcriptMediaId 优先（官方转写键）；media.id/mediaKey 兜底。"""
    mid = ep.get("transcriptMediaId") or ""
    if not mid:
        mid = (ep.get("media") or {}).get("id") or ep.get("mediaKey") or ""
    return mid


def transcript_get(eid, media_id, tok, timeout=20.0):
    """POST episode-transcript/get → data dict。HttpFail 直通分类。"""
    status, _hdrs, body = http_post(
        f"{API}/v1/episode-transcript/get",
        {"eid": eid, "mediaId": media_id},
        app_headers(device_id(tok), access=tok["access_token"]),
        timeout,
    )
    if status != 200:
        raise HttpFail(status, body)
    try:
        d = json.loads(body)
    except json.JSONDecodeError:
        raise HttpFail(0, body[:200])
    if not isinstance(d, dict):
        raise HttpFail(0, body[:200])
    if d.get("code"):
        raise HttpFail(0, json.dumps(d, ensure_ascii=False)[:200].encode())
    data = d.get("data")
    return data if isinstance(data, dict) else {}


def transcript_fetch(url, timeout=30.0):
    """签名链 → [{text,startMs}]。CDN UA ACL：UA 必须安卓 app 形。
    URL 来自 API 响应——出去前校验 https+白名单 host：响应被篡改给
    file:// 时 urllib 会读本地文件并把字节带进 error evidence。"""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError as e:
        raise HttpFail(0, f"transcriptUrl 解析失败：{e}".encode())
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(
        host == h.lstrip(".") or host.endswith(h) for h in CDN_HOSTS
    ):
        raise HttpFail(0, f"transcriptUrl 出白名单域：{u.scheme}://{host}".encode())
    raw = http_get(url, headers={"User-Agent": CDN_UA}, timeout=timeout, gunzip=True)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        raise HttpFail(0, raw[:200])
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        data = d.get("data")
        return data if isinstance(data, list) else []
    raise HttpFail(0, b"transcript body not a JSON array/object")


def render_transcript(segments):
    """[{text,startMs}] → [MM:SS] text 行（[Music]/[Lyric] 标签原样保留）。"""
    out = []
    for s in segments:
        if not isinstance(s, dict):
            continue
        try:
            ms = int(float(s.get("startMs") or 0))
        except (TypeError, ValueError):
            continue  # 畸形 startMs 段宁可丢也不崩整条车道
        text = re.sub(r"\s+", " ", str(s.get("text") or "")).strip()
        if not text:
            continue
        out.append(f"[{ms // 60000:02d}:{(ms // 1000) % 60:02d}] {text}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- HTML→md

_SKIP_TAGS = {"script", "style", "noscript", "iframe"}
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "li",
    "blockquote",
    "pre",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


class _Html2Md(HTMLParser):
    """小宇宙 shownotes HTML → 轻量 md：段落/列表/链接/图片，弃样式标签。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.href = None
        self.skip = 0

    def _w(self, s):
        if not self.skip:
            self.out.append(s)

    def _nl(self, n=1):
        if self.skip:
            return
        cur = "".join(self.out)
        need = n - (len(cur) - len(cur.rstrip("\n")))
        if need > 0:
            self.out.append("\n" * need)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _SKIP_TAGS:
            self.skip += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._nl(2)
            self._w("#" * int(tag[1]) + " ")
        elif tag == "li":
            self._nl()
            self._w("- ")
        elif tag == "br":
            self._w("\n")
        elif tag in _BLOCK_TAGS:
            self._nl(2 if tag != "li" else 1)
        elif tag == "a":
            if self.href is not None:
                # 嵌套 <a>（富文本编辑器产物）：先闭合外层再开新的
                self._w(f"]({self.href})")
            self.href = a.get("href") or ""
            self._w("[")
        elif tag == "img":
            src = a.get("src") or ""
            if src:
                self._w(f"![]({src})")
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag in (
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "pre",
            "blockquote",
            "tr",
        ):
            self._nl()
        elif tag in ("p", "div", "section", "article", "ul", "ol"):
            self._nl(2)
        elif tag == "a":
            if self.href is not None:  # 游离 </a> 无开不产 "]"残渣
                self._w(f"]({self.href})")
                self.href = None
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")

    def handle_data(self, d):
        self._w(d)

    def md(self):
        s = "".join(self.out)
        s = re.sub(r"[ \t]+\n", "\n", s)
        # li 内嵌块级标签会在 "- " 后补 \n\n 造成孤行破折号——收拢回 "- text"
        s = re.sub(r"(?m)^-[^\S\n]*\n\n+", "- ", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip() + "\n"


def html2md(html):
    p = _Html2Md()
    try:
        p.feed(html or "")
    except Exception:
        # 坏 HTML 不该杀整条车道——先剥 script/style 块再剥标签成纯文本
        s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", "", html or "")
        return re.sub(r"<[^>]+>", "", s)
    return p.md()


# ---------------------------------------------------------------- 产物面


def meta_of(ep, form, extra=None):
    """meta.json schema（consumer-contract.md xyzfm 节）。"""
    media = ep.get("media") or {}
    enc = ep.get("enclosure") or {}
    pod = ep.get("podcast") or {}
    d = {
        "platform": "xyzfm",
        "form": form,
        "eid": ep.get("eid"),
        "pid": ep.get("pid") or pod.get("pid"),
        "title": ep.get("title"),
        "podcast_title": pod.get("title"),
        "duration_s": ep.get("duration"),
        "pub_date": ep.get("pubDate"),
        "url": f"https://www.xiaoyuzhoufm.com/episode/{ep.get('eid')}",
        "audio_url": enc.get("url") or (media.get("source") or {}).get("url"),
        "transcript_media_id": media_id_of(ep) or None,
    }
    if extra:
        d.update(extra)
    return d


def write_json(path, obj):
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def write_text(path, text):
    Path(path).write_text(text, encoding="utf-8")
