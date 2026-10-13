#!/usr/bin/env python3
"""fetch_engine.py — fetch substrate: bare_resolve → canon → route → admit → exec → collect → envelope.

Lane ABI v1 + pack.toml + journal contract: skills/link-get/references/lane-abi.md.
Derived state (cache/neg/breaker/inflight) is delegated to the `lgc` CLI — the
engine never opens lgc's sqlite itself, so old connectors and the engine share
one store safely (WAL + flock on lgc's side).

Subcommands:
  run <target> [-o DIR] [-p PACK] [--json] [--plan] [--param k=v ...] [--flags…]
  packs [--json]                    已加载 pack 的机读面列表
  lane-run <lane> [req.json|-]      bypass: run one lane standalone
  conformance <lane>                assert lane-abi.md §11 invariants
  selftest [-p PACK]                fixture lanes + lgc caps + pack 部署体检
"""

import sys

try:
    import tomllib
except ImportError:  # pragma: no cover - the launcher version-gates first
    sys.stderr.write("fetch-engine: requires python>=3.11 (tomllib)\n")
    sys.exit(127)

import argparse
import fnmatch
import hashlib
import importlib.machinery
import importlib.util
import ipaddress
import json
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import time
import uuid
from pathlib import Path

VERSION = "0.1.0"
ABI = 1
GRACE_MS = 400
STDERR_CAP = 64 * 1024
LGC_TIMEOUT = 30

CLASSES = {
    "noresults",
    "notcovered",
    "permanent",
    "auth_expired",
    "challenge_needed",
    "rate_limited",
    "transient",
    "budget_exceeded",
    "dep_absent",
    "lane_crash",
    "protocol_violation",
}
# engine-edge rc compression (lane-abi §7)
RC_FOR_CLASS = {
    "noresults": 3,
    "notcovered": 3,
    "permanent": 4,
    "transient": 5,
    "rate_limited": 5,
    "lane_crash": 5,
    "protocol_violation": 5,
    "dep_absent": 5,
    "auth_expired": 6,
    "challenge_needed": 6,
    "budget_exceeded": 7,
}
# classes where trying the next lane is pointless（connector lanes_run 只对
# rc4 短路：cred 死/超预算的车道让位后续车道——匿名车道能救 cred 死，是级联本意）
STOP_CLASSES = {"permanent"}

# 机读 hint：envelope.class → 给消费者的下一步动作提示（class 缺席不带此键）
CLASS_HINTS = {
    "dep_absent": "依赖缺失——跑 fetch-engine selftest --deploy 定位缺席组件",
    "auth_expired": "凭证失效——用对应 pack 的 --mint 臂重铸凭证后重试",
    "challenge_needed": "需人工过验证——完成人机挑战后重试",
    "rate_limited": "触发限流——稍候重试",
    "permanent": "内容已删除——已落删除墓碑，勿重试",
    "notcovered": "此形态无覆盖车道——确认 URL/kind 或补 pack",
    "budget_exceeded": "车道超时——加 --budget-ms 重试",
    "transient": "暂性失败——稍后重试或 --refresh 绕过缓存",
    "noresults": "车道无产物——目标可能无可用内容",
    "lane_crash": "车道崩溃——查 journal 指向的 stderr.log",
    "protocol_violation": "lane 违反 ABI——查 journal 指向的 stderr.log",
}

# [params] 闸的 engine 保留豁免集——这些键永不因未声明被拒（内部分发/全局旗标）。
# 另豁免：[[routes]].params 键、lane params_gate 键、identity.satisfies 键及其
# param 名、identity.key_params——不豁免会把内部分发 param 全拒。
RESERVED_PARAMS = {
    "kind",
    "variant",
    "enum",
    "refresh",
    "no_cache",
    "cache_ttl",
    "o",
    "json",
    "plan",
    "budget_ms",
}

DELSIGN = (
    "该内容已被发布者删除",
    "此内容因违规无法查看",
    "该内容已被删除",
    "该回答已被删除",
    "没有知识存在的荒原",
)

LGC_BIN = os.environ.get("LGC_BIN", "lgc")
JOBS_ROOT = Path(
    os.environ.get("FETCH_ENGINE_JOBS")
    or Path(os.environ.get("LGC_HOME") or Path.home() / ".cache") / "link-get" / "jobs"
)
PACKS_DIR = Path(
    os.environ.get("FETCH_ENGINE_PACKS")
    or Path(__file__).resolve().parent.parent / "packs"
)
SELF_DIR = Path(__file__).resolve().parent
MONOLITH_SHIM = SELF_DIR / "monolith_shim.py"


# ---------------------------------------------------------------- journal


class Journal:
    def __init__(self, job_id, jdir):
        self.job_id = job_id
        self.jdir = Path(jdir)
        self.jdir.mkdir(parents=True, exist_ok=True)
        # long-lived append handle — closed via Journal.close() at command end
        self.f = open(  # noqa: SIM115
            self.jdir / "journal.jsonl", "a", encoding="utf-8"
        )

    def rec(self, stage, evtype, **kw):
        obj = {
            "ts": round(time.time(), 3),
            "job_id": self.job_id,
            "stage": stage,
            evtype: True,
            **kw,
        }
        obj["type"] = evtype
        self.f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.f.flush()

    def event(self, stage, **kw):
        self.rec(stage, "event", **kw)

    def decision(self, stage, **kw):
        self.rec(stage, "decision", **kw)

    def close(self):
        self.f.close()


# ---------------------------------------------------------------- lgc bridge


class Lgc:
    """Thin CLI bridge. Absent lgc => degraded mode (cache off, gates open)."""

    def __init__(self, journal=None, ns="link-get"):
        self.j = journal
        self.ns = ns
        self._caps = None
        self._avail = None
        # inflight markers owned by this process (get --claim → rc6)
        self.claimed_keys = set()

    def _run(self, args, timeout=LGC_TIMEOUT, stdin=None):
        try:
            p = subprocess.run(
                [LGC_BIN, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=stdin,
            )
            return p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.TimeoutExpired) as e:
            return 127, "", str(e)

    def available(self):
        if self._avail is None:
            rc, out, _ = self._run(["--version"])
            self._avail = rc == 0 and out.strip().startswith("lgc")
        return self._avail

    def caps(self):
        if self._caps is None:
            rc, out, _ = self._run(["has"])
            self._caps = set(out.split()) if rc == 0 else set()
        return self._caps

    def has(self, cap):
        return cap in self.caps()

    def key(self, raw):
        rc, out, _ = self._run(["key", self.ns, raw])
        return out.strip() if rc == 0 else None

    def get(self, key, into, claim_pid=None, wait=None, satisfies=None):
        """Returns (verdict, paths, reason). verdict: hit|miss|neg|off."""
        args = ["get", self.ns, key, "--into", str(into)]
        if satisfies and self.has("satisfies"):
            args += ["--satisfies", json.dumps(satisfies, ensure_ascii=False)]
        if self.has("claim"):
            if claim_pid:
                args += ["--claim", "--owner-pid", str(claim_pid)]
            if wait is not None:  # 无 claim 也可压 --wait 0（--plan 只读探针不陪等）
                args += ["--wait", str(wait)]
        if self.has("json"):
            args += ["--json"]
        rc, out, err = self._run(args)
        for ln in (out + err).splitlines():
            if ln.startswith(("cache:", "lgc:")) and self.j:
                self.j.event("cache", detail=ln)
        if rc == 0:
            paths = []
            if self.has("json"):
                try:
                    payload = json.loads(out)
                    paths = list(payload.get("paths", []))
                except json.JSONDecodeError:
                    paths = []
            if not paths:
                paths = [
                    line
                    for line in out.splitlines()
                    if line and not line.startswith(("cache:", "lgc:", "{"))
                ]
            return "hit", paths, None
        if rc == 6:
            self.claimed_keys.add(key)  # miss + 我方认领 inflight 槽位
        reason = {3: "notrack", 4: "deleted", 5: "unavailable"}.get(rc)
        return ("neg" if reason else "miss"), [], reason

    def put(
        self,
        key,
        files=None,
        from_dir=None,
        value=None,
        lane=None,
        ttl=None,
        params=None,
        cred=None,
        owner_pid=None,
        keep=False,
        atomic=False,
    ):
        args = ["put", self.ns, key]
        if files:
            args += ["--files", *map(str, files)]
        if from_dir:
            args += ["--from", str(from_dir)]
        if value is not None:
            args += ["--value", value]
        if lane:
            args += ["--lane", lane]
        if ttl:
            args += ["--ttl", str(ttl)]
        if params:
            args += ["--params", json.dumps(params, ensure_ascii=False)]
        if cred:
            args += ["--cred", cred]
        if owner_pid:
            args += ["--owner-pid", str(owner_pid)]
        if keep and self.has("keep-flag"):
            args += ["--keep"]
        if atomic and self.has("atomic"):
            args += ["--atomic"]
        rc, _, _ = self._run(args)
        self.claimed_keys.discard(key)  # put 的 finally 无条件释放本键 marker
        return rc  # 4 = delguard refused

    def neg(self, key, reason, ttl=None, cred=None):
        args = ["neg", self.ns, key, "--reason", reason]
        if ttl:
            args += ["--ttl", str(ttl)]
        if cred:
            args += ["--cred", cred]
        self._run(args)
        self.claimed_keys.discard(key)  # neg 同样释放本键 inflight marker

    def lane_probe(self, lane, key=None):
        args = ["lane", self.ns, "probe", lane] + ([key] if key else [])
        rc, _, _ = self._run(args)
        return rc != 1  # True = run, False = cooling/neg -> skip

    def lane_fail(self, lane, key=None, reason=None):
        if self.has("breaker"):
            args = ["lane", self.ns, "fail", lane]
            if key:
                args.append(key)
            if reason:
                args += ["--reason", reason]
            self._run(args)

    def lane_hit(self, lane):
        self._run(["lane", self.ns, "hit", lane])

    def lane_note(self, lane, key, reason, ttl=None):
        args = ["lane", self.ns, "note", lane, key, "--reason", reason]
        if ttl:
            args += ["--ttl", str(ttl)]
        self._run(args)

    def release(self, key, owner_pid):
        self._run(["release", self.ns, key, "--owner-pid", str(owner_pid)])
        self.claimed_keys.discard(key)

    def cat(self, key):
        rc, out, _ = self._run(["cat", self.ns, key])
        return out if rc == 0 else None

    def cred_fp(self, domain):
        """`lgc cred-fp <domain>` → 域凭证指纹（cred8）。
        lgc 缺席/子命令不存在/域未知或无可读 cred 文件（rc3）→ None。"""
        if not self.available():
            return None
        rc, out, _ = self._run(["cred-fp", domain])
        fp = (out or "").strip()
        return fp if rc == 0 and fp else None


# ---------------------------------------------------------------- packs


class Pack:
    def __init__(self, path, doc):
        self.dir = Path(path).parent
        self.doc = doc
        p = doc.get("pack", {})
        self.name = p.get("name") or self.dir.name
        self.desc = p.get("desc", "")
        self.abi = int(p.get("abi", 1))
        self.ns = p.get("ns", "link-get")
        self.kinds = p.get("kinds") or ["article"]
        # kind_required：URL/params 判不出 kind 即拒（zhihu 平价——无兜底 kind）
        self.kind_required = bool(p.get("kind_required", False))
        self.kind_hint = p.get("kind_hint", "")
        m = doc.get("match", {})
        self.hosts = m.get("hosts") or ["*"]
        self.schemes = m.get("schemes") or ["http", "https"]
        self.raw_patterns = m.get("raw_patterns") or []
        # [[match.bare]]：canon 之前作用于 raw token 的有序重写表
        # （{pattern, rewrite}；re.match + {0}/{N} 捕获组模板）
        self.bare = m.get("bare") or []
        # [params] 声明式参数面：name → {type,desc,internal,secret,values}
        self.params_spec = doc.get("params") or {}
        if not isinstance(self.params_spec, dict):
            self.params_spec = {}
        # cred_domain（顶层或 [pack] 段）：cred_handle 委托 lgc cred-fp
        self.cred_domain = doc.get("cred_domain") or p.get("cred_domain")
        # writes_cred（顶层或 [pack] 段）：pack 铸 cred 的目标 ns/domain 声明
        self.writes_cred = doc.get("writes_cred") or p.get("writes_cred")
        ident = doc.get("identity", {})
        self.keyexpr = ident.get("keyexpr", "{kind}:{url}")
        self.key_params = ident.get("key_params") or []
        # variant_params：注入 keyexpr 的 param 名——清空即得 base_key（变体剥离面）
        self.variant_params = ident.get("key_params") or []
        # probe_base_variants：内容键以这些变体后缀结尾时，探测链先探 base_key
        # （zhihu +f：全量基键命中即可供快览，probe ZBASE→ZK 序）
        self.probe_base_variants = ident.get("probe_base_variants") or []
        self.capture = ident.get("capture") or {}
        self.capture_defaults = ident.get("capture_defaults") or {}
        # kind_by_url 内部统一存 {kind: regex}；两种声明面并存：
        #   [identity].kind_by_url = { kind = 'regex' }   （存量，kind→regex）
        #   [kind_by_url] 'regex' = 'kind'                （新 schema，regex→kind）
        # 同 kind 冲突时顶层新表赢（其条目按 TOML 序排到尾部）
        kbu = dict(ident.get("kind_by_url") or {})
        for pat, k in (doc.get("kind_by_url") or {}).items():
            kbu.pop(k, None)
            kbu[k] = pat
        self.kind_by_url = kbu
        # match_scope="path"：kind_by_url/capture 只在 netloc+path 上匹配——
        # query/fragment 剥除（?utm=/p/999 这类注入不造 kind/键）
        self.match_scope = ident.get("match_scope", "url")
        # capture_query：path 面下仍需 query 的捕获名白名单（bilibili ?p=N 分 P
        # 是真键料——剥了会多 P 视频坍成 p1）
        self.capture_query = set(ident.get("capture_query") or [])
        # [[identity.derive]] 有序派生：目标 param 缺席且 when_* 满足时填 value
        # （分发层注入在引擎层的平价——裸 --param comments/fast 不撞基键/错 kind）
        self.derive = ident.get("derive") or []
        # satisfies：{探测键名: {param, default?, type?}} → get --satisfies JSON
        # （media-get 平价：entry params 不满足请求约束即判 miss 重抓）
        self.satisfies = ident.get("satisfies") or {}
        # [[routes]] kind×params → 有序 lane 子集；缺席 → 全量 pack.lanes
        self.routes = doc.get("routes") or []
        self.lanes = doc.get("lanes") or []
        self.monolith = doc.get("monolith") or {}
        # lgc_off=false 的 monolith wrap：connector 自管全部缓存/记账（自己的
        # probe/satisfies/claim/put/neg/lane-note 机器）——engine 再探再写只会
        # 双写错 params 的垃圾 entry + 与 connector claim 互等，全线跳过
        self.self_managed = self.monolith.get("lgc_off", True) is False

    def matches(self, url, scheme, host):
        if scheme and self.schemes and scheme not in self.schemes:
            return False
        if host:
            return any(fnmatch.fnmatch(host, g.lower()) for g in self.hosts)
        return any(fnmatch.fnmatch(url, g) for g in self.raw_patterns)


def load_packs(errors=None):
    """errors 传入 list 时收集解析失败详情（deploy 体检据此计 fail）。"""
    packs = []
    if not PACKS_DIR.is_dir():
        return packs
    for ptoml in sorted(PACKS_DIR.glob("*/pack.toml")):
        try:
            doc = tomllib.loads(ptoml.read_text(encoding="utf-8"))
            packs.append(Pack(ptoml, doc))
        except Exception as e:
            if errors is not None:
                errors.append(f"{ptoml}: {e}")
            sys.stderr.write(f"pack {ptoml}: {e}\n")
    # specific host globs before catch-all——hosts 含 "*" 即兜底（不止精确 ["*"]）
    packs.sort(key=lambda p: ("*" in p.hosts, p.name))
    return packs


# ---------------------------------------------------------------- canon / identity / route

PRIVATE_HOSTNAMES = {"localhost", "localhost.", "ip6-localhost", "ip6-loopback"}
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home")


def guard_url(url, allow_private=False):
    """Literal-host SSRF gate. Returns reason string or None."""
    from urllib.parse import urlsplit

    try:
        u = urlsplit(url)
    except ValueError as e:
        return f"unparseable url: {e}"
    if u.scheme not in ("http", "https"):
        return f"scheme '{u.scheme}' not allowed"
    host = (u.hostname or "").lower()
    if not host:
        return "empty host"
    if allow_private:
        return None
    if host in PRIVATE_HOSTNAMES or host.endswith(PRIVATE_SUFFIXES):
        return f"private hostname '{host}'"
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        # inet_aton 字面量形（dword/short/hex/octal——2130706433、127.1、
        # 0x7f000001、0177.0.0.1）：ipaddress 全拒，若按 DNS 放行即 SSRF 逃逸
        try:
            packed = socket.inet_aton(host)
        except (OSError, ValueError):
            return None  # DNS name — literal check only; resolve-lane rechecks
        ip = ipaddress.ip_address(packed)
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return f"private address '{host}'"
    return None


# 裸文件名扩展名表——"report.pdf" 撞上 dot-TLD 规则会被补 https 当 host 抓，
# 本地文件径名进而被送上云解析车道（隐私边界）；命中即不补 scheme，落到 rc3。
_BARE_FILE_EXTS = (
    r"pdf|docx?|pptx?|xlsx?|epub|mobi|zip|tgz?|gz|bz2|xz|7z|rar|"
    r"mp[34]|m4a|mov|avi|mkv|webm|wav|flac|ogg|"
    r"png|jpe?g|gif|webp|svgz?|ico|bmp|tiff?|"
    r"csv|tsv|jsonl?|xml|ya?ml|toml|ini|txt|log|"
    r"py|js|ts|jsx|tsx|css|html?|c|h|cpp|hpp|java|go|rs|rb|php|pl|lua|sql|"
    r"exe|dll|so|dylib|dmg|iso|apk|ipa|deb|rpm|msi|ttf|otf|woff2?|bin|dat"
)


def canon(raw):
    """Light cleanup; heavy normalization lives inside lgc's key derivation."""
    raw = raw.strip()
    if not raw:
        return None, "empty target"
    # 裸 host/path（zhihu.com/p/1）：connector 时代 curl 自补 scheme；
    # engine 须在 route/admit 前归一，否则 scheme 闸误拒。
    # denylist 只管无 / 的裸文件名——x.com/a.pdf 是远端文档不是本地文件，
    # 拦了会把 doc 车道饿死
    if (
        "://" not in raw
        and re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}([/:?#]|$)", raw)
        and (
            "/" in raw
            or not re.search(
                r"\.(?:" + _BARE_FILE_EXTS + r")([?#].*)?$",
                raw,
                re.IGNORECASE,
            )
        )
    ):
        raw = "https://" + raw
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        from urllib.parse import urlsplit, urlunsplit

        try:
            u = urlsplit(raw)
        except ValueError as e:
            return None, f"unparseable url: {e}"
        try:
            uport = u.port
        except ValueError:
            return None, f"unparseable url (bad port): {raw}"
        host = (u.hostname or "").lower()
        if ":" in host:
            host = f"[{host}]"  # v6 字面量 brackets 必须保住——裸写下游按 host:port 误切
        # 端口剥离按 scheme 默认表——http:443/https:80 是跨源另一站，盲剥会撞键
        default_port = {"http": 80, "https": 443}.get(u.scheme.lower())
        port = f":{uport}" if uport and uport != default_port else ""
        # userinfo 剥除：user:pass@ 进 journal/缓存键/lgc argv 全是泄露面
        netloc = host + port
        raw = urlunsplit((u.scheme.lower(), netloc, u.path or "/", u.query, ""))
    return raw, None


def bare_resolve(target, packs, journal=None):
    """[[match.bare]] 有序重写表——canon 之前作用于 raw token：
    首条 re.match 命中的 pattern 触发 rewrite 模板展开（{0}=整组、{N}=捕获组 N），
    重写结果进 canon 继续管线；未中原样返回。命中即停——绝不重扫重写产物。
    packs 由调用方按确定性序（pack.name）排好；-p 强制时只含该 pack 的表。"""
    for pack in packs:
        for rule in pack.bare:
            pat = rule.get("pattern")
            tpl = rule.get("rewrite")
            if not pat or tpl is None:
                continue
            try:
                m = re.match(pat, target)
            except re.error as e:
                if journal:
                    journal.event(
                        "bare_resolve",
                        pack=pack.name,
                        detail=f"bad pattern {pat!r}: {e}",
                    )
                continue
            if m is None:
                continue
            # {0}=整组 {N}=捕获组 N——str.format(*groups) 位置参展开；
            # format_map 不支持数字域（ValueError: positional fields）。
            # 未参与的捕获组（None）展开为空串。
            groups = tuple(
                g if g is not None else "" for g in (m.group(0), *m.groups())
            )
            try:
                out = tpl.format(*groups)
            except (KeyError, IndexError, ValueError) as e:
                if journal:
                    journal.event(
                        "bare_resolve",
                        pack=pack.name,
                        detail=f"bad rewrite {tpl!r}: {e}",
                    )
                continue
            if journal:
                journal.decision(
                    "bare_resolve",
                    pack=pack.name,
                    pattern=pat,
                    rewrite=tpl,
                    target=out,
                )
            return out
    return target


def param_valid_keys(pack):
    """[params] 闸的合法键集：pack.params_spec ∪ engine 保留名 ∪
    routes.params 键 ∪ lane params_gate 键 ∪ satisfies 键/param 名 ∪ key_params。"""
    valid = set(RESERVED_PARAMS) | set(pack.params_spec)
    for route in pack.routes:
        valid.update((route.get("params") or {}).keys())
    for lane in pack.lanes:
        valid.update((lane.get("params_gate") or {}).keys())
    for skey, decl in (pack.satisfies or {}).items():
        valid.add(skey)
        if isinstance(decl, dict) and decl.get("param"):
            valid.add(decl["param"])
    valid.update(pack.key_params)
    return valid


def secret_params(pack):
    """[params] 里声明 secret=true 的键——journal 只记键名，值一律 '***'。"""
    return {
        k
        for k, d in pack.params_spec.items()
        if isinstance(d, dict) and d.get("secret")
    }


_SECRET_QP = re.compile(
    r"([?&](?:sig|signature|token|access_token|auth_token|expires|"
    r"key-pair-pk|credential|x-amz-[a-z0-9-]*|password|passwd|secret|"
    r"api_?key|sessionid)=)[^\s&#]*",
    re.IGNORECASE,
)


def mask_url_secrets(s):
    """journal/plan 落盘面的 query 秘参掩码——值换 ***（key/lgc argv 需真值
    保功能，journal 是持久面不该存秘参）。"""
    return _SECRET_QP.sub(r"\1***", str(s))


def match_target(pack, raw):
    """kind_by_url/capture 的匹配面：match_scope="path" → netloc+path
    （query/fragment 剥除——?utm=/p/999、?next=/opus/1 类注入不造 kind/键）。"""
    if pack.match_scope != "path":
        return raw
    from urllib.parse import urlsplit

    try:
        u = urlsplit(raw)
    except ValueError:
        return raw
    return (u.netloc or "") + (u.path or "")


def _key_fmt(pack, kind, raw, params):
    fmt = {"url": raw, "kind": kind}
    for k in pack.key_params:
        fmt[k] = str(params.get(k, ""))
    mraw = match_target(pack, raw)
    for name, pat in pack.capture.items():
        if isinstance(pat, dict):
            pat = pat.get(kind) or pat.get("default") or ""
        # capture_query 白名单：该捕获匹配全 raw（query 是真键料）
        hay = raw if name in pack.capture_query else mraw
        m = re.search(pat, hay) if pat else None
        fmt[name] = (
            (m.group(1) if m and m.groups() else m.group(0))
            if m
            else str(pack.capture_defaults.get(name, ""))
        )
    return fmt


def render_key(pack, expr, kind, raw, params):
    if isinstance(expr, dict):
        expr = expr.get(kind) or expr.get("default") or "{kind}:{url}"
    fmt = _key_fmt(pack, kind, raw, params)
    # a capture referenced by the expr but empty (e.g. no BV in a b23.tv link)
    # would collapse all such URLs onto one key — fall back to per-URL key.
    capture_miss = any(
        "{" + name + "}" in expr and not fmt.get(name) for name in pack.capture
    )
    try:
        return f"{kind}:{raw}" if capture_miss else expr.format_map(_SafeFmt(fmt))
    except Exception:
        return f"{kind}:{raw}"


def build_satisfies(pack, params):
    """[identity].satisfies {探测键: {param,default?,type?}} → lgc --satisfies
    JSON。param 缺席取 default，两者皆无 → 该键略去；全空 → None（不探约束）。"""
    spec = pack.satisfies
    if not spec:
        return None
    out = {}
    for key, decl in spec.items():
        if not isinstance(decl, dict):
            continue
        v = params.get(decl.get("param") or key, decl.get("default"))
        if v is None:
            continue
        t = decl.get("type", "str")
        try:
            if t == "int":
                v = int(v)
            elif t == "csv":
                v = [s for s in str(v).split(",") if s]
            elif t == "bool":
                v = _truthy(v)
            elif t == "str":
                v = str(v)
            # 其它 type 原样透传（list/dict/数值字面量）
        except (TypeError, ValueError):
            continue
        out[key] = v
    return out or None


def apply_derive(pack, kind, params):
    """[[identity.derive]] 有序规则：目标 param 缺席（falsy）且 when_kind /
    when_truthy 满足时填 value。target="kind" 的规则在 make_identity 早段
    先决——kind 定后才轮到普通派生（variant 等）。"""
    params = dict(params)
    for rule in pack.derive:
        if not isinstance(rule, dict):
            continue
        target = rule.get("target")
        if not target or target == "kind" or params.get(target):
            continue
        wk = rule.get("when_kind")
        if wk and kind not in (wk if isinstance(wk, list) else [wk]):
            continue
        wt = rule.get("when_truthy")
        if wt and not _truthy(params.get(wt)):
            continue
        params[target] = rule.get("value", True)
    return params


def make_identity(pack, raw, params, lgc):
    kind = params.get("kind") if params.get("kind") in pack.kinds else None
    kind_miss = False
    if kind is None:
        mraw = match_target(pack, raw)
        kind = next(
            (k for k, pat in pack.kind_by_url.items() if re.search(pat, mraw)),
            None,
        )
        if kind is None:
            # kind-derive：param 触发的 kind 填充（youtube 裸 --param fast →
            # kind=fast → yt:fast: 键 + kind_flags，不再错存 tr 键）
            kind = next(
                (
                    r.get("value")
                    for r in pack.derive
                    if isinstance(r, dict)
                    and r.get("target") == "kind"
                    and r.get("value") in pack.kinds
                    and r.get("when_truthy")
                    and _truthy(params.get(r["when_truthy"]))
                ),
                None,
            )
        if kind is None:
            kind = pack.kinds[0]
            kind_miss = True  # params 与 kind_by_url 均未判出——兜底了 kinds[0]
    params = apply_derive(pack, kind, params)
    key = render_key(pack, pack.keyexpr, kind, raw, params)
    # base_key：同一 keyexpr、variant_params 全部清空——车道账/基键探测/
    # store='base' 入库共用这把无变体键（connector 平价：lane 键从不带变体）
    base_params = dict(params)
    for kp in pack.variant_params:
        base_params[kp] = ""
    base_key = render_key(pack, pack.keyexpr, kind, raw, base_params)
    kh = lgc.key(key) if lgc.available() else None
    return {
        "raw": raw,
        "key": key,
        "base_key": base_key,
        "kind": kind,
        "kind_miss": kind_miss,
        "params": params,
        "keyhash": kh,
    }


def select_lanes(pack, ident):
    """[[routes]]：首条 kind∈kinds 且 params 全匹配的 arm → 按 route.lanes 序
    取 lane cfg。无 routes → 全量 pack.lanes；有 routes 无匹配 → None。"""
    if not pack.routes:
        return pack.lanes
    params = ident.get("params") or {}
    for route in pack.routes:
        kinds = route.get("kinds")
        if kinds is None:
            kinds = []
        elif not isinstance(kinds, list):
            kinds = [kinds]
        # 无 kinds 限制（缺席/空表）或含 "*" → 兜底臂覆盖全部 kind
        # （与 selftest 覆盖自检同口径，兜底臂无 params 约束即兜）
        if kinds and "*" not in kinds and ident["kind"] not in kinds:
            continue
        ok = True
        for k, v in (route.get("params") or {}).items():
            actual = params.get(k)
            if v is True:
                match = _truthy(actual)
            elif v is False:
                match = not _truthy(actual)
            else:
                match = str(actual if actual is not None else "") == str(v)
            if not match:
                ok = False
                break
        if not ok:
            continue
        return [
            lc
            for name in (route.get("lanes") or [])
            for lc in pack.lanes
            if lc.get("name") == name
        ]
    return None


def params_gate_ok(gate, params):
    """lane params_gate：每个声明的 param 必须落在允许值表内（值按 str 比较）。"""
    for pname, allowed in (gate or {}).items():
        allowed = allowed if isinstance(allowed, list) else [allowed]
        if str(params.get(pname, "")) not in [str(a) for a in allowed]:
            return False
    return True


class _SafeFmt(dict):
    def __missing__(self, k):
        return ""


# ---------------------------------------------------------------- exec: lane runner

LANE_ENV_BASE = [
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "LGC_HOME",
    "LGC_BIN",
    "FETCH_ENGINE_JOBS",
    "FETCH_ENGINE_ALLOW_PRIVATE",
    "FETCH_ENGINE_PACKS",
    "FETCH_ENGINE_PYTHON",
]


def lane_env(lane_cfg, cred_env):
    env = {k: v for k, v in os.environ.items() if k in LANE_ENV_BASE}
    needs = lane_cfg.get("needs") or {}
    for name in (needs.get("env") or []) + (needs.get("env_optional") or []):
        if name in os.environ:
            env[name] = os.environ[name]
    egress = lane_cfg.get("egress") or {}
    if egress.get("proxy") in ("required", "optional"):
        for v in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
            "NO_PROXY",
            "no_proxy",
        ):
            if v in os.environ:
                env[v] = os.environ[v]
    env.update(cred_env)
    return env


def lane_argv(pack, lane_cfg):
    exec_ = lane_cfg.get("exec", "")
    if exec_ == "monolith":
        shim = MONOLITH_SHIM
        return [sys.executable, str(shim)]
    path = Path(exec_)
    if not path.is_absolute():
        cand = pack.dir / exec_
        path = cand if cand.exists() else Path(exec_)
    if path.suffix == ".py":
        return [sys.executable, str(path)]
    return [str(path)]


def check_needs(lane_cfg):
    needs = lane_cfg.get("needs") or {}
    missing = []
    for t in needs.get("tools") or []:
        if not shutil.which(t):
            missing.append(f"tool:{t}")
    # tools_any：任一在场即满足（zhihu 二进制 或 uvx 兜底类 OR 依赖）
    any_tools = needs.get("tools_any") or []
    if any_tools and not any(shutil.which(t) for t in any_tools):
        missing.append(f"tool_any:{'|'.join(any_tools)}")
    for e in needs.get("env") or []:
        if not os.environ.get(e):
            missing.append(f"env:{e}")
    # needs.creds 不闸：声明的凭证文件只喂 cred_handle 指纹——connector 自行
    # 降级/报 auth_expired（zhihu 无 cookie 走 jina、media 有 BBDown.data 兜底）
    return missing


def run_lane(job, pack, lane_cfg, ident, cred_env, stdin_extra=None):
    """Spawn one lane, stream JSONL, enforce budget, classify terminal.
    Returns dict {outcome: result|data|error|skipped, ...}."""
    j = job.journal
    lane_name = lane_cfg.get("name", "lane")
    lane_fname = re.sub(r"[^A-Za-z0-9_.-]", "_", lane_name)
    adir = job.artifact_dir
    adir.mkdir(parents=True, exist_ok=True)
    errlog_path = job.dir / f"{lane_fname}.stderr.log"
    budget_ms = int(lane_cfg.get("budget_ms") or job.budget_ms)

    stdin_obj = {
        "job_id": job.job_id,
        "identity": ident,
        "ctx": {
            "artifact_dir": str(adir),
            "journal_dir": str(job.dir),
            "budget_ms": budget_ms,
            "cred_handle": job.cred_handle or "",
            "key": ident["key"],
        },
    }
    if stdin_extra:
        stdin_obj.update(stdin_extra)

    env = lane_env(lane_cfg, cred_env)
    if lane_cfg.get("exec") == "monolith":
        conf = dict(pack.monolith)
        conf.update(lane_cfg.get("monolith") or {})  # lane 级 [lanes.monolith] 覆盖
        conf["connector"] = lane_cfg.get("connector", "")
        # lane 级 kinds 窄于 pack 级时以 lane 为准（双保险，engine admit 已先行闸）
        conf["kinds"] = lane_cfg.get("kinds") or getattr(pack, "kinds", [])
        if lane_cfg.get("rc_map"):
            conf["rc_map"] = lane_cfg["rc_map"]
        conf["pack_dir"] = str(pack.dir)
        env["MONOLITH_CONF"] = json.dumps(conf, ensure_ascii=False)

    argv = lane_argv(pack, lane_cfg)
    j.decision(
        "exec", lane=lane_name, argv=argv[1:] if argv else argv, budget_ms=budget_ms
    )
    # closed after proc.wait() below — a `with` cannot span the stream loop
    errlog = open(errlog_path, "ab")  # noqa: SIM115
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errlog,
            env=env,
            bufsize=0,
            start_new_session=True,
            cwd=str(pack.dir),
        )
    except OSError as e:
        errlog.close()
        j.event("exec", lane=lane_name, detail=f"spawn failed: {e}")
        return {
            "outcome": "error",
            "class": "lane_crash",
            "evidence": f"spawn: {e}",
            "retryable": True,
            "lane": lane_name,
        }
    try:
        proc.stdin.write(json.dumps(stdin_obj, ensure_ascii=False).encode())
        proc.stdin.write(b"\n")
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        # lane 秒退没读 stdin——写 BrokenPipe 不是 engine 错，继续走读环，
        # lane 的 rc/stdout 照常分类（lane_crash/notcovered 由终态面裁决）
        try:
            proc.stdin.close()
        except OSError:
            pass

    fd = proc.stdout.fileno()
    deadline = time.monotonic() + (budget_ms + GRACE_MS) / 1000
    buf, terminal, killed = b"", None, False
    artifacts, protocol_bad = [], []

    def handle_line(line):
        nonlocal terminal
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            ev = None
        if not isinstance(ev, dict):
            text = line.decode(errors="replace")[:200]
            protocol_bad.append(text)
            j.event("lane", lane=lane_name, protocol_violation=True, detail=text)
            return
        t = ev.get("type")
        j.event("lane", lane=lane_name, lane_event=ev)
        if t == "artifact":
            artifacts.append(ev)
        elif t in ("result", "data", "error"):
            if terminal is None:
                terminal = ev
            else:
                # 首条终态胜（ABI：exactly one terminal）——后发丢弃但记违例，
                # last-wins 会把已收的 result 换成 error 连产物一起丢
                j.event(
                    "lane",
                    lane=lane_name,
                    protocol_violation=True,
                    detail=f"second terminal '{t}' ignored",
                )

    def pump(final=False):
        nonlocal buf
        while b"\n" in buf or (final and buf.strip()):
            if b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
            else:
                line, buf = buf, b""
            if line.strip():
                handle_line(line.strip())

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            killed = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            j.decision(
                "exec",
                lane=lane_name,
                killed=True,
                detail=f"budget {budget_ms}ms + grace {GRACE_MS}ms",
            )
            while select.select([fd], [], [], 1.0)[0]:
                data = os.read(fd, 65536)
                if not data:
                    break
                buf += data
            break
        if not select.select([fd], [], [], min(remaining, 0.25))[0]:
            continue
        data = os.read(fd, 65536)
        if not data:
            break
        buf += data
        pump()
    pump(final=True)
    rc = proc.wait()
    errlog.close()
    if errlog_path.stat().st_size > STDERR_CAP:
        # ABI 约定 stderr.log 保留尾部——truncate(0..CAP) 留头丢尾，crash 段恰在尾
        errlog_path.write_bytes(errlog_path.read_bytes()[-STDERR_CAP:])
    j.decision("exec", lane=lane_name, rc=rc, killed=killed, artifacts=len(artifacts))

    if rc == 10 and terminal is not None:
        j.event("exec", lane=lane_name, detail="rc10_after_terminal")
    elif rc == 10:
        return {"outcome": "skipped", "class": "notcovered", "lane": lane_name}
    if terminal is None:
        if killed:
            terminal = {
                "type": "error",
                "class": "budget_exceeded",
                "evidence": f"killed at budget {budget_ms}ms",
                "retryable": True,
            }
        elif rc == 0:
            terminal = {
                "type": "error",
                "class": "noresults",
                "evidence": "rc=0, no terminal event",
                "retryable": False,
            }
        else:
            tail = _stderr_tail(errlog_path)
            terminal = {
                "type": "error",
                "class": "lane_crash",
                "evidence": f"rc={rc} {tail}",
                "retryable": True,
            }
        j.decision(
            "exec",
            lane=lane_name,
            synthesized_terminal=terminal["type"],
            detail=terminal.get("evidence"),
        )
    if terminal["type"] == "result":
        items = terminal.get("items") or artifacts
        res = {"outcome": "result", "items": items, "lane": lane_name}
        # lane 可随 result 上报入库 params（束的实测语义：height/req_cap/
        # langs_obtained/files_meta…）——collect 时并入 entry params，
        # 否则 satisfies 探针永远拿不到产物侧字段
        rp = terminal.get("params")
        if isinstance(rp, dict):
            res["params"] = rp
        return res
    if terminal["type"] == "data":
        return {
            "outcome": "data",
            "payload": terminal.get("payload"),
            "lane": lane_name,
        }
    cls = terminal.get("class") or "transient"
    if cls not in CLASSES:
        cls = "transient"
    return {
        "outcome": "error",
        "class": cls,
        "evidence": terminal.get("evidence") or terminal.get("msg") or "",
        "retryable": bool(terminal.get("retryable")),
        "retry_after": terminal.get("retry_after"),
        "needs_human": bool(terminal.get("needs_human")),
        "scope_hint": terminal.get("scope_hint"),
        "lane": lane_name,
    }


def _stderr_tail(path, n=400):
    try:
        data = path.read_bytes()[-2048:]
        return data.decode(errors="replace").strip()[-n:]
    except OSError:
        return ""


# ---------------------------------------------------------------- admit/collect policies


def record_error(lgc, ident, lane, res, lane_cfg=None):
    """Write derived state per lane-abi §6 scope table."""
    if not lgc.available():
        return
    lane_cfg = lane_cfg or {}
    key, cls = ident["key"], res["class"]
    # 车道账走 base_key（变体剥离基键，zhihu lk=ZBASE 平价）；内容墓碑走内容键
    lk = ident.get("base_key") or key
    if cls == "auth_expired":
        # cred 死是车道事不是内容事：内容键 neg 会毒死共享 store——connector
        # 对同键探测 exit5/24h，匿名车道陪葬。auth 理由让 lgc 自动把
        # note/breaker 绑进 cred 域（cred8 轮换即自愈），对齐 z_lfail 形状。
        lgc.lane_note(lane, lk, "auth-expired", ttl=3600)
        lgc.lane_fail(lane, lk, "auth-expired")
    elif cls == "permanent":
        # 变体内容 gone ⇒ 基键同碑（+f/+c 是同一内容的视图，不是独立条目）
        lgc.neg(key, "deleted")
        if lk != key:
            lgc.neg(lk, "deleted")
    elif cls == "noresults":
        lgc.neg(key, "unavailable", ttl=86400)
    elif cls == "notcovered":
        # scope_hint=params：拒绝针对请求形（参数校验/参数级不覆盖），不是内容
        # 覆盖判词——基键墓碑无 params 维度，上账会把同键其余参数组合陪葬 30d
        if res.get("scope_hint") != "params":
            lgc.lane_note(lane, lk, "notcovered", ttl=2592000)
    elif cls == "rate_limited":
        ttl = res.get("retry_after") or 3600
        lgc.lane_note(lane, lk, "ratelimited", ttl=ttl)
    elif cls == "challenge_needed":
        # 车道可报 retry_after 覆盖默认 12h——站点风控墙（zhcli/bili 平价）要
        # 长冷却，自家 QR 过期这类"再扫一次就好"的 challenge 不该锁死 remint
        lgc.lane_note(lane, lk, "challenge", ttl=res.get("retry_after") or 43200)
    elif cls in ("transient", "lane_crash", "protocol_violation") and lane_cfg.get(
        "fail_note", True
    ):
        # fail_note=false（tardis 平价）：镜像面错误只分类不上账——
        # 内容类 neg（permanent/noresults 等）照常写
        lgc.lane_fail(lane)
        lgc.lane_note(lane, lk, "lane-fail", ttl=600)
    # dep_absent / budget_exceeded: record nothing


def delguard_scan(paths):
    for p in paths:
        if Path(p).suffix in (".md", ".txt") or Path(p).name == "__value__":
            try:
                head = Path(p).read_text(encoding="utf-8", errors="replace")[:65536]
            except OSError:
                continue
            for sig in DELSIGN:
                if sig in head:
                    return sig
    return None


def _safe_relpath(name):
    """Item name doubles as dest/store relpath — reject absolute/parent escapes."""
    if not name or Path(str(name)).is_absolute():
        return False
    n = os.path.normpath(str(name))
    return n != ".." and not n.startswith(".." + os.sep)


def _relpath_or_name(path, root):
    """lgc get --into 按入库 relpath 还原子目录树——hit 交付沿用同一 relpath。"""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return Path(path).name


def validate_artifacts(items, adir):
    """Every artifact path must live inside artifact_dir; names must be non-empty."""
    root = Path(adir).resolve()
    ok, bad = [], []
    for it in items:
        p = Path(it.get("path", ""))
        try:
            rp = p.resolve()
        except OSError:
            bad.append((it, "unresolvable path"))
            continue
        if root not in rp.parents and rp != root:
            bad.append((it, "outside artifact_dir"))
        elif not _safe_relpath(it.get("name")):
            bad.append((it, "unsafe name"))
        elif not rp.is_file():
            bad.append((it, "not a file"))
        else:
            it["path"] = str(rp)
            it.setdefault("bytes", rp.stat().st_size)
            ok.append(it)
    # 同名产物改名去重——name 同时是交付/staging/lgc 的 relpath，撞名会被
    # copy2 静默覆盖丢件，envelope 却谎报两件
    seen = {}
    for it in ok:
        name = it.get("name") or Path(it["path"]).name
        n = seen.get(name, 0)
        if n:
            stem, ext = os.path.splitext(name)
            cand = f"{stem}-{n}{ext}"
            while cand in seen:
                n += 1
                cand = f"{stem}-{n}{ext}"
            it["name"] = cand
            name = cand
        seen[name] = n + 1
    return ok, bad


# ---------------------------------------------------------------- job

JOBS_KEEP_S = 14 * 86400  # jobs/ 无界增长——过期任务目录（journal+artifacts）整体回收


def _gc_jobs(jobs_root):
    try:
        cutoff = time.time() - JOBS_KEEP_S
        for d in Path(jobs_root).iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


class Job:
    def __init__(self, jobs_root=None, budget_ms=120000):
        self.job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.dir = Path(jobs_root or JOBS_ROOT) / self.job_id
        self.artifact_dir = self.dir / "artifacts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(exist_ok=True)
        self.journal = Journal(self.job_id, self.dir)
        self.budget_ms = budget_ms
        self.cred_handle = ""


def resolve_cred_env(pack, job, lgc=None):
    """cred_handle：pack 声明 cred_domain → 委托 `lgc cred-fp`（域口径与
    lgc 凭证记账同源，修指纹分歧）；缺席/空 → ""。未声明 → needs.creds
    原文哈希旧口径。env passthrough 仍是空表。"""
    if pack.cred_domain:
        job.cred_handle = (lgc.cred_fp(pack.cred_domain) if lgc else None) or ""
        return {}
    creds = []
    for lane in pack.lanes:
        creds += (lane.get("needs") or {}).get("creds") or []
    fp = ""
    if creds:
        h = hashlib.sha256()
        for c in sorted(set(creds)):
            p = Path(c).expanduser()
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"missing")
        fp = h.hexdigest()[:8]
    job.cred_handle = fp
    return {}


# ---------------------------------------------------------------- run pipeline


def cmd_run(args):
    t0 = time.monotonic()
    params = dict(args.param or [])
    for k, v in args.kv or []:
        params[k] = v
    # --json 旗标与 --param json（link-get 透传形）同义——机读面经壳可达
    json_mode = args.json or _truthy(params.get("json"))
    # --plan dry-run（壳 --plan → --param plan 透传同义）：决策面照跑，不 spawn 车道
    plan_mode = bool(args.plan) or _truthy(params.get("plan"))
    no_cache = _truthy(params.get("no_cache"))
    refresh = _truthy(params.get("refresh"))
    try:
        cache_ttl = int(params.get("cache_ttl") or 0) or None
    except (TypeError, ValueError):
        cache_ttl = None
    job = Job(budget_ms=args.budget_ms)
    j = job.journal
    lgc = Lgc(journal=j)
    _gc_jobs(job.dir.parent)

    def envelope(rc, cls=None, items=None, data=None, plan=None):
        env = {
            "job_id": job.job_id,
            "rc": rc,
            "items": items or [],
            "journal": str(job.dir / "journal.jsonl"),
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        }
        if cls:
            env["class"] = cls
            if cls in CLASS_HINTS:
                env["hint"] = CLASS_HINTS[cls]
        if data is not None:
            env["data"] = data
        if plan is not None:
            env["plan"] = plan
        if json_mode:
            print(json.dumps(env, ensure_ascii=False))
        j.event("envelope", rc=rc, **({"class": cls} if cls else {}))
        j.close()
        return rc

    def out_paths(items, dest):
        """Copy items to -o dest (if given) and print ==> 已存 lines."""
        shown = []
        for it in items:
            src = Path(it["path"])
            dst = src
            if dest:
                dest.mkdir(parents=True, exist_ok=True)
                dst = dest / (it.get("name") or src.name)
                dst.parent.mkdir(parents=True, exist_ok=True)  # name 可带子目录
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
            # --json 模式 stdout 是单行 envelope 契约——交付行进 stderr
            if json_mode:
                sys.stderr.write(f"==> 已存 {dst}\n")
            else:
                print(f"==> 已存 {dst}")
            shown.append({**it, "path": str(dst)})
        return shown

    # ---- packs + forced-pack resolution（bare_resolve 扫描面需要：
    #      -p 时只扫该 pack 的 [[match.bare]]，否则按 name 序全表扫描）
    packs = load_packs()
    pack = None
    if args.pack:
        pack = next((p for p in packs if p.name == args.pack), None)
        if not pack:
            sys.stderr.write(f"fetch-engine: unknown pack '{args.pack}'\n")
            return envelope(2)

    # ---- bare_resolve：raw token 有序重写（canon 之前，修裸 ID/旧式 arxiv/
    #      裸课程号这类 canon 会劫持成 dot-TLD URL 的输入形）
    target = bare_resolve(
        args.target.strip(),
        [pack] if pack else sorted(packs, key=lambda p: p.name),
        j,
    )

    # ---- canon
    raw, err = canon(target)
    if err:
        sys.stderr.write(f"fetch-engine: {err}\n")
        return envelope(2)
    j.decision("canon", raw=mask_url_secrets(raw))

    # -o 指向已存在的普通文件 → rc2（dest.mkdir 的 FileExistsError 是 rc1 裸炸）
    if args.outdir and args.outdir.exists() and not args.outdir.is_dir():
        sys.stderr.write(f"fetch-engine: -o {args.outdir} 已存在且非目录\n")
        return envelope(2)

    # ---- route (forced pack short-circuits before host matching)
    if pack:
        j.decision("route", pack=pack.name, forced=True)
    else:
        from urllib.parse import urlsplit

        u = urlsplit(raw) if "://" in raw else None
        for p in packs:
            if p.matches(
                raw,
                u.scheme if u else None,
                u.hostname.lower() if u and u.hostname else None,
            ):
                pack = p
                break
        if not pack:
            j.decision("route", detail="no pack matched")
            sys.stderr.write(f"fetch-engine: no pack covers {raw}\n")
            return envelope(3, "notcovered")
        j.decision("route", pack=pack.name, via="match")

    # pack 持有自己的 lgc 命名空间（zhihu-skill）：不切换则与旧 connector
    # 写出的缓存/车道账分裂成两套——lgc 首次调用在下方 identity，此处换绑安全
    lgc.ns = pack.ns

    # ---- params gate：--param 键必须落在 pack [params] ∪ 豁免集内——
    #      错拼旗标静默失效比直接拒更糟（旧直连由 connector usage 拒的平价）。
    #      secret 声明的参数 journal 只记键名（值 '***'，不落明文）；
    #      未过闸的未知键同样掩码——错拼的秘参旗标不该落 journal 明文。
    valid_params = param_valid_keys(pack)
    bad_params = sorted(k for k in params if k not in valid_params)
    # [params].values 值域执行：枚举形参数越表即 rc2——值域拒绝是 usage 错，
    # 落到 lane params_gate 变成 dep_absent 是误导类
    bad_vals = sorted(
        k
        for k, d in pack.params_spec.items()
        if isinstance(d, dict)
        and d.get("values")
        and params.get(k) is not None
        and str(params.get(k)) not in [str(v) for v in d["values"]]
    )
    # kind 不在 [params] 声明面（RESERVED 豁免）——引擎层核 pack.kinds：
    # kind=bogus 会静默坍到 kinds[0]，把内容写进错域键
    if params.get("kind") is not None and params["kind"] not in pack.kinds:
        bad_vals.append("kind")
    secrets = secret_params(pack)
    rejected = bad_params + bad_vals
    j.decision(
        "admit",
        gate="params",
        provided={
            k: ("***" if (k in secrets or k in bad_params) else v)
            for k, v in params.items()
        },
        **({"rejected": rejected} if rejected else {}),
    )
    if bad_params:
        sys.stderr.write(
            f"fetch-engine: unknown param(s) {', '.join(bad_params)} "
            f"for pack '{pack.name}' — valid: {', '.join(sorted(valid_params))}\n"
        )
        return envelope(2, "refused")
    if bad_vals:
        sys.stderr.write(
            f"fetch-engine: param value out of range: {', '.join(bad_vals)} "
            f"for pack '{pack.name}'\n"
        )
        return envelope(2, "refused")

    # ---- SSRF gate (pre-dispatch; lanes re-resolve at fetch time)
    deny = guard_url(
        raw, allow_private=_truthy(os.environ.get("FETCH_ENGINE_ALLOW_PRIVATE"))
    )
    if deny:
        j.decision("admit", gate="ssrf", deny=deny)
        sys.stderr.write(f"fetch-engine: refused {raw}: {deny}\n")
        return envelope(2, "refused")

    # ---- identity
    ident = make_identity(pack, raw, params, lgc)
    j.decision(
        "identity",
        key=mask_url_secrets(ident["key"]),
        kind=ident["kind"],
        keyhash=ident.get("keyhash"),
        **({"kind_miss": True} if ident["kind_miss"] else {}),
    )
    if pack.kind_required and ident["kind_miss"]:
        hint = f"——{pack.kind_hint}" if pack.kind_hint else ""
        sys.stderr.write(f"fetch-engine: no kind for {raw}{hint}\n")
        return envelope(2, "refused")

    # ---- lane arm：[[routes]] kind×params → 有序 lane 子集（无 routes → 全量）
    lanes = select_lanes(pack, ident)
    if lanes is None:
        j.decision("route_miss", kind=ident["kind"])
        sys.stderr.write(f"fetch-engine: no route for kind={ident['kind']} ({raw})\n")
        return envelope(2, "refused")
    if pack.routes:
        j.decision("route", lanes=[lc.get("name", "lane") for lc in lanes])

    cred_env = resolve_cred_env(pack, job, lgc)
    adir = job.artifact_dir

    # ---- admit gate 1: content cache（探测链：列名变体后缀 → 先探 base_key）
    owner_pid = os.getpid()

    def fail_release():
        for k in list(lgc.claimed_keys):
            lgc.release(k, owner_pid)

    probe_keys = (
        [ident["base_key"]]
        if ident["base_key"] != ident["key"]
        and any(ident["key"].endswith(v) for v in pack.probe_base_variants)
        else []
    ) + [ident["key"]]
    cache_verdict = "off"
    # 纯铸凭证 meta-lane（writes_cred）探内容键只会吞 mint——hit 返回旧内容
    # 不铸 cred；meta 臂既非内容产物也无冷却语义，gate1/gate2 全跳
    meta_only = bool(lanes) and all(lc.get("writes_cred") for lc in lanes)
    if pack.self_managed:
        # connector 自管缓存（lgc_off=false）：探测/认领/入库/记账全归它——
        # engine 探测只会 hit 到自己写的无 params 垃圾版本或抢走 inflight 槽
        cache_verdict = "self-managed"
        j.decision("admit", gate="cache", verdict=cache_verdict)
    elif meta_only:
        cache_verdict = "meta-lane"
        j.decision("admit", gate="cache", verdict=cache_verdict)
    elif lgc.available() and not (no_cache or refresh):
        try:
            wait_s = int(os.environ.get("LGC_WAIT") or "300")
        except ValueError:
            wait_s = 300
        # satisfies 断言读 derive 后的有效 params（xyzfm art 臂 derive
        # form=shownotes）——用原始 params 时断言落 default，与 derive 注入
        # 的束记 params 互斥 → 该键域缓存恒 miss 变 write-only
        sat = build_satisfies(pack, ident["params"])
        for k in probe_keys:
            # plan 模式探针不建 inflight 槽位、不陪等（lgc 侧命中/miss 计数
            # 与过期 GC 与真探测同质——非零写，但不写 entry/neg/cred）
            verdict, paths, reason = lgc.get(
                k,
                adir,
                claim_pid=None if plan_mode else owner_pid,
                wait=0 if plan_mode else wait_s,
                satisfies=sat,
            )
            cache_verdict = verdict
            j.decision(
                "admit",
                gate="cache",
                key=mask_url_secrets(k),
                verdict=verdict,
                reason=reason,
                paths=len(paths),
                **({"satisfies": len(sat)} if sat else {}),
            )
            if verdict == "hit":
                if plan_mode:
                    break  # dry-run 只记 verdict——hit 不交付，继续列车道决策面
                fail_release()  # 前序 miss 的认领归还——本次不生产
                sys.stderr.write(f"cache: hit(engine,{mask_url_secrets(k[:32])})\n")
                items = [{"path": p, "name": _relpath_or_name(p, adir)} for p in paths]
                return envelope(0, items=out_paths(items, args.outdir))
            if verdict == "neg":
                if plan_mode:
                    break  # 同上：plan 不收墓碑短路，车道面照列
                fail_release()
                cls = {
                    "deleted": "permanent",
                    "notrack": "notcovered",
                    "unavailable": "transient",
                }.get(reason, "transient")
                return envelope(RC_FOR_CLASS[cls], cls)
            # miss+claim（rc6）已由 Lgc.get 记入 claimed_keys——探测键都可能入库
    else:
        if lgc.available():
            cache_verdict = "no_cache" if no_cache else "refresh"
        j.decision("admit", gate="cache", verdict=cache_verdict)

    # ---- admit gate 2: per-lane kind/params + needs + cooling
    runnable = []
    lane_status = []  # --plan 机读面：每条 lane 的闸判定
    for lc in lanes:
        name = lc.get("name", "lane")
        st = {"name": name, "ok": True}
        lkinds = lc.get("kinds")
        if lkinds and ident["kind"] not in lkinds:
            j.decision("admit", gate="kinds", lane=name, detail=f"kind={ident['kind']}")
            st.update(ok=False, gate="kinds")
            lane_status.append(st)
            continue
        if not params_gate_ok(lc.get("params_gate"), ident["params"]):
            j.decision("admit", gate="params", lane=name)
            st.update(ok=False, gate="params")
            lane_status.append(st)
            continue
        missing = check_needs(lc)
        if missing:
            j.decision("admit", gate="needs", lane=name, missing=missing)
            st.update(ok=False, gate="needs", missing=missing)
            lane_status.append(st)
            continue
        if lgc.available() and not pack.self_managed and not (no_cache or refresh):
            # writes_cred 车道照样过冷却——auth_expired 车道账须拦 remint
            # hammer（bili_mint 实测回归）；只有 gate1 内容探测对 meta-lane 跳过
            if not lgc.lane_probe(name, ident["base_key"]):
                j.decision("admit", gate="cooling", lane=name, verdict="skip")
                st.update(ok=False, gate="cooling")
                lane_status.append(st)
                continue
        elif lgc.available():
            j.decision(
                "admit",
                gate="cooling",
                lane=name,
                verdict=(
                    "no_cache" if no_cache else "refresh" if refresh else "self-managed"
                ),
            )
        lane_status.append(st)
        runnable.append(lc)

    # ---- --plan dry-run：决策面出完即收——不 spawn 车道、不写 entry/neg、
    #      无 claim（lgc 探针计数/GC 与真跑同质，非零写——语义是"评估"非"冻结"）
    if plan_mode:
        fail_release()  # 防御：只读探针本不该留 claim
        plan = {
            "target_raw": raw,
            "pack": pack.name,
            "kind": ident["kind"],
            "key": mask_url_secrets(ident["key"]),
            "base_key": mask_url_secrets(ident["base_key"]),
            "lanes": lane_status,
            "runnable": len(runnable),
            "cache_verdict": cache_verdict,
        }
        if not json_mode:
            print(f"plan pack={pack.name} kind={ident['kind']} cache={cache_verdict}")
            print(
                f"key={mask_url_secrets(ident['key'])} "
                f"base={mask_url_secrets(ident['base_key'])}"
            )
            for st in lane_status:
                if st["ok"]:
                    print(f"lane {st['name']}: ok")
                else:
                    why = st["gate"]
                    if st.get("missing"):
                        why += " " + ",".join(st["missing"])
                    print(f"lane {st['name']}: 拒({why})")
        return envelope(0, plan=plan)

    if not runnable:
        fail_release()
        j.decision("admit", detail="no runnable lanes")
        return envelope(5, "dep_absent")

    # ---- exec lanes in order
    final = None
    last_error = None
    for lc in runnable:
        res = run_lane(job, pack, lc, ident, cred_env)
        res["lc"] = lc
        if res["outcome"] == "skipped":
            j.decision("exec", lane=res["lane"], detail="lane skipped (rc10)")
            continue
        if res["outcome"] in ("result", "data"):
            final = res
            break
        last_error = res
        if not no_cache and not pack.self_managed:
            record_error(lgc, ident, res["lane"], res, res.get("lc"))
        if res["class"] in STOP_CLASSES:
            j.decision("exec", lane=res["lane"], detail=f"stop class {res['class']}")
            break

    # ---- collect
    if final and final["outcome"] == "result":
        ok, bad = validate_artifacts(final["items"], adir)
        for it, why in bad:
            j.event(
                "collect", protocol_violation=True, detail=f"{why}: {it.get('path')}"
            )
            last_error = {
                "outcome": "error",
                "class": "protocol_violation",
                "evidence": f"artifact {why}",
                "lane": final["lane"],
            }
            final = None
        if final and not ok:
            # result 全件验证不过/空 items = lane 违例，不是内容缺席——
            # 若按 noresults 走会给内容键落 24h 墓碑，错杀活内容
            last_error = {
                "outcome": "error",
                "class": "protocol_violation",
                "evidence": "result with empty items",
                "lane": final["lane"],
            }
            final = None
        if final:
            lk = ident.get("base_key") or ident["key"]
            sig = delguard_scan([i["path"] for i in ok])
            if sig:
                if not no_cache:
                    lgc.neg(ident["key"], "deleted")
                    if lk != ident["key"]:
                        lgc.neg(lk, "deleted")
                fail_release()
                items = out_paths(ok, args.outdir)
                sys.stderr.write(f"内容命中删除签名（产物已保留）：{sig}\n")
                return envelope(4, "permanent", items=items)
            # store='base'：全文产物永远入基键（jina/firecrawl 平价——
            # 一次 +f 快取不得只填满 +f 变体键）
            store_key = (
                ident["base_key"]
                if (final.get("lc") or {}).get("store") == "base"
                else ident["key"]
            )
            if lgc.available() and not no_cache and not pack.self_managed:
                # put --files 拍扁 relpath 成 basename——answers/x.md 与
                # articles/x.md 撞名丢件。按 name 搭 staging 走 --from 保树
                # （connector staged_run 的 z_store --from 平价）
                stage = job.dir / "store"
                shutil.rmtree(stage, ignore_errors=True)
                stage.mkdir(parents=True)
                for it in ok:
                    dst = stage / (it.get("name") or Path(it["path"]).name)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.link(it["path"], dst)
                    except OSError:
                        shutil.copy2(it["path"], dst)
                # lane result.params（产物实测语义）覆盖请求 params——
                # satisfies 探针看的是束的 height/langs_obtained 而非请求值；
                # secret 声明键掩码——lgc put --params 落 manifest，秘参值不盘
                put_params = {
                    k: ("***" if k in secrets else v)
                    for k, v in ident["params"].items()
                }
                put_params.update(final.get("params") or {})
                lc = final.get("lc") or {}
                prc = lgc.put(
                    store_key,
                    from_dir=stage,
                    lane=final["lane"],
                    params=put_params,
                    ttl=cache_ttl,
                    owner_pid=owner_pid if store_key in lgc.claimed_keys else None,
                    keep=bool(lc.get("store_keep")),
                    atomic=bool(lc.get("store_atomic")),
                )
                j.decision(
                    "collect",
                    gate="store",
                    rc=prc,
                    keep=bool(lc.get("store_keep")),
                    atomic=bool(lc.get("store_atomic")),
                )
                # put 自释 store_key marker；归还其余 probe 认领（变体/基键另一把）
                fail_release()
                if prc == 4:
                    lgc.neg(ident["key"], "deleted")
                    if lk != ident["key"]:
                        lgc.neg(lk, "deleted")
                    items = out_paths(ok, args.outdir)
                    return envelope(4, "permanent", items=items)
            lgc.lane_hit(final["lane"]) if (
                lgc.available() and not no_cache and not pack.self_managed
            ) else None
            items = out_paths(ok, args.outdir)
            return envelope(0, items=items)

    if final and final["outcome"] == "data":
        payload = final["payload"]
        if not json_mode:
            if isinstance(payload, str):
                print(payload)
            else:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
        fail_release()
        return envelope(0, data=payload)

    fail_release()
    if last_error:
        cls = last_error["class"]
        msg = last_error.get("evidence", "")
        sys.stderr.write(f"fetch-engine: {cls}: {msg}\n")
        if last_error.get("needs_human"):
            sys.stderr.write("fetch-engine: needs human intervention\n")
        return envelope(RC_FOR_CLASS[cls], cls)
    # 走到这 = 每条 runnable lane 都 rc10 静默跳过（dep 缺席/形状不覆盖）——
    # connector lanes_run 全 skip 收 rc5；dep_absent 不记账同则
    return envelope(5, "dep_absent")


# ---------------------------------------------------------------- lane-run


def cmd_lane_run(args):
    lane_path = Path(args.lane)
    req = None
    if args.req and args.req != "-":
        req = json.loads(Path(args.req).read_text(encoding="utf-8"))
    elif args.req == "-" or not sys.stdin.isatty():
        try:
            req = json.loads(sys.stdin.read() or "null")
        except json.JSONDecodeError as e:
            sys.stderr.write(f"lane-run: bad req json: {e}\n")
            return 2
    job = Job()
    req = req or {}
    ident = req.get("identity") or {
        "raw": req.get("url", "lane-run://test"),
        "key": "lane-run:test",
        "kind": req.get("kind", "article"),
        "params": req.get("params", {}),
    }
    # identity 缺字段不该裸 KeyError——stdin_obj ctx 装配需要 key/raw/kind
    ident.setdefault("key", f"lane-run:{ident.get('raw', 'test')}")
    ident.setdefault("raw", "lane-run://test")
    ident.setdefault("kind", req.get("kind", "article"))
    ident.setdefault("params", {})
    ident.setdefault("base_key", ident["key"])
    lane_cfg = {
        "name": req.get("lane_name") or lane_path.stem,
        "exec": str(lane_path),
        "budget_ms": req.get("budget_ms", 30000),
    }
    fake_pack = type(
        "P", (), {"dir": lane_path.parent, "monolith": {}, "name": "lane-run"}
    )()
    if str(lane_path) == "monolith" or req.get("monolith"):
        lane_cfg["exec"] = "monolith"
        lane_cfg["connector"] = req.get("connector", "generic-get")
        fake_pack.monolith = req.get("monolith") or {
            "argv": ["{url}", "-o", "{artifact_dir}"],
        }
        lane_cfg["name"] = "monolith:" + lane_cfg["connector"]
    res = run_lane(job, fake_pack, lane_cfg, ident, {})
    job.journal.event("lane-run", outcome=res["outcome"])
    out = {
        "job_id": job.job_id,
        "outcome": res["outcome"],
        "journal": str(job.dir / "journal.jsonl"),
    }
    if res["outcome"] == "result":
        out["items"] = res["items"]
    elif res["outcome"] == "data":
        out["payload"] = res["payload"]
    else:
        out["error"] = {k: res.get(k) for k in ("class", "evidence", "retryable")}
    job.journal.close()
    print(json.dumps(out, ensure_ascii=False))
    return (
        0
        if res["outcome"] in ("result", "data")
        else RC_FOR_CLASS.get(res.get("class", "noresults"), 5)
    )


# ---------------------------------------------------------------- conformance

FIXTURE_DIR = SELF_DIR.parent / "tests" / "fixtures"


def check_lane_stdout(lines):
    """§11.1/2: every line parses as JSON with a legal type; one terminal."""
    types = []
    bad = []
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            bad.append(i)
            continue
        t = ev.get("type")
        if t not in ("progress", "artifact", "data", "error", "call", "result"):
            bad.append(i)
        types.append(t)
    terminals = [t for t in types if t in ("result", "data", "error")]
    return bad, types, terminals


def cmd_conformance(args):
    lane = Path(args.lane)
    if not lane.exists():
        sys.stderr.write(f"conformance: no such lane {lane}\n")
        return 2
    checks = []
    # C1: a normal run — stdout JSONL-clean, one terminal, journal stamped
    job = Job()
    ident = {
        "raw": "conformance://probe",
        "key": "conf:probe",
        "kind": args.kind or "article",
        "params": {},
    }
    lc = {"name": lane.stem, "exec": str(lane), "budget_ms": args.budget_ms}
    fake_pack = type(
        "P", (), {"dir": lane.parent, "monolith": {}, "name": "conformance"}
    )()
    res = run_lane(job, fake_pack, lc, ident, {})
    stderr_log = job.dir / f"{lane.stem}.stderr.log"
    checks.append(("outcome", res["outcome"]))
    # C2: journal has job_id on every line
    jlines = (job.dir / "journal.jsonl").read_text().splitlines()
    stamped = all(json.loads(line).get("job_id") == job.job_id for line in jlines)
    checks.append(("journal_job_id", stamped))
    # C3: artifact confinement (only when lane produced artifacts)
    if res["outcome"] == "result":
        _, bad = validate_artifacts(res["items"], job.artifact_dir)
        checks.append(("artifact_confined", not bad))
        checks.append(("item_names", all(i.get("name") for i in res["items"])))
    checks.append(
        (
            "stderr_captured",
            not stderr_log.exists() or stderr_log.stat().st_size <= STDERR_CAP + 4096,
        )
    )
    job.journal.close()
    ok = True
    for name, val in checks:
        passed = bool(val) and val is not False
        if name == "outcome":
            passed = val in ("result", "data", "error", "skipped")
        if not passed:
            ok = False
        print(f"{'PASS' if passed else 'FAIL'} {name}: {val}")
    return 0 if ok else 1


FIXTURES = {
    "ok_lane.py": "result",
    "data_lane.py": "data",
    "quiet_lane.py": "error:noresults",
    "sleeper_lane.py": "error:budget_exceeded",
    "skip_lane.py": "skipped",
    "err_lane.py": "error:transient",
    "dirty_lane.py": "any",  # unparsed line must not kill the runner
    "badterm_lane.py": "result",  # terminal beats rc10
    "escape_lane.py": "result",  # runner sees it; collect stage rejects
}


def _fixture_selftest():
    total, failed = 0, 0
    for fname, expect in FIXTURES.items():
        lane = FIXTURE_DIR / fname
        if not lane.exists():
            print(f"SKIP {fname}: missing")
            continue
        total += 1
        job = Job()
        ident = {
            "raw": "selftest://x",
            "key": "selftest:x",
            "kind": "article",
            "params": {},
        }
        lc = {
            "name": lane.stem,
            "exec": str(lane),
            "budget_ms": 1500 if fname == "sleeper_lane.py" else 10000,
        }
        fake_pack = type(
            "P", (), {"dir": lane.parent, "monolith": {}, "name": "selftest"}
        )()
        res = run_lane(job, fake_pack, lc, ident, {})
        job.journal.close()
        got = res["outcome"]
        if expect == "any":
            ok = True
        elif expect.startswith("error:"):
            ok = got == "error" and res.get("class") == expect.split(":", 1)[1]
        else:
            ok = got == expect
        if not ok:
            failed += 1
        print(
            f"{'PASS' if ok else 'FAIL'} {fname}: "
            f"want {expect} got {got}" + ("" if ok else f" ({res.get('class')})")
        )
    print(f"fixtures: {total - failed}/{total} passed")
    return failed


# fetch 组件消费的 lgc 能力集（doctor.sh×3 合并版）：缺席即 ✗
REQUIRED_CAPS = [
    "get",
    "put",
    "neg",
    "release",
    "cat",
    "lane",
    "list",
    "key",
    "value",
    "satisfies",
    "cred",
    "producer",
    "delguard",
    "denylist",
    "breaker",
    "into",
    "wait",
    "from",
    "claim",
    "keep-flag",
    "atomic",
    "params",
    "owner-pid",
    "lane-note",
    "ttl",
    "json",
]


def _lgc_health():
    """lgc 部署段（吸收 doctor.sh×3 的重复块）：banner + caps + selftest。"""
    fails = 0
    print("== lgc")
    env_bin = os.environ.get("LGC_BIN")
    lgc_bin = env_bin or shutil.which("lgc") or str(SELF_DIR / "lgc")
    if not (Path(lgc_bin).exists() or shutil.which(str(lgc_bin))):
        print("  · lgc 缺席——缓存层直通 miss 降级（跑 setup.sh 启用）")
        return 0
    try:
        r = subprocess.run(
            [str(lgc_bin), "has"], capture_output=True, text=True, timeout=10
        )
    except Exception as e:
        print(f"  ✗ lgc has 失败: {e}")
        return 1
    lines = r.stdout.splitlines()
    banner = lines[0] if lines else ""
    if re.match(r"^lgc [0-9]+(\.[0-9]+)?$", banner):
        print(f"  ✓ banner: {banner}")
    else:
        fails += 1
        print(f"  ✗ banner 异常: {banner}")
    caps = set(" ".join(lines[1:]).split())
    missing = [c for c in REQUIRED_CAPS if c not in caps]
    if missing:
        fails += 1
        print(f"  ✗ caps 缺席: {' '.join(missing)}")
    else:
        print(f"  ✓ caps {len(REQUIRED_CAPS)} 项齐")
    try:
        r = subprocess.run([str(lgc_bin), "selftest"], capture_output=True, timeout=30)
        if r.returncode == 0:
            print("  ✓ lgc selftest")
        else:
            fails += 1
            print("  ✗ lgc selftest")
    except Exception as e:
        fails += 1
        print(f"  ✗ lgc selftest: {e}")
    return fails


def _lgc_cred_surface():
    """解析中的 lgc 脚本 → (mint 合法域 CRED_DOMAINS, ns→domain map,
    cred_domain 合法域 CRED_FILES 键集)；脚本不可读/非 python → None
    （cred 校验降级跳过，不打红）。优先读 lgc 自带
    CRED_DOMAINS/NS_CRED_DOMAIN，缺席回退 CRED_FILES 键集。"""
    env_bin = os.environ.get("LGC_BIN")
    lgc_bin = env_bin or shutil.which("lgc") or str(SELF_DIR / "lgc")
    path = Path(str(lgc_bin))
    if not path.is_file():
        return None
    try:
        loader = importlib.machinery.SourceFileLoader("_lgc_cred_mod", str(path))
        spec = importlib.util.spec_from_loader("_lgc_cred_mod", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    except Exception:
        return None
    cred_files = set(getattr(mod, "CRED_FILES", {}) or {})
    domains = getattr(mod, "CRED_DOMAINS", None)
    if domains is None:
        domains = cred_files - {"bili-fallback"}
    nsmap = getattr(mod, "NS_CRED_DOMAIN", None)
    if nsmap is None:
        nsmap = {}
    return set(domains or ()), dict(nsmap), cred_files


def _cred_domain_of(decl, domains, nsmap):
    """writes_cred 声明值 → cred domain：声明值可直接是 domain 名；是 ns 名时
    走 NS_CRED_DOMAIN 映射（映射口径=cred domain 名而非 ns 名），老 lgc 无映射
    表再回退 '-skill'/'-get' 后缀剥离。映射不出 → None（体检判 FAIL）。"""
    if decl in domains:
        return decl
    if nsmap.get(decl) in domains:
        return nsmap[decl]
    for sfx in ("-skill", "-get"):
        if decl.endswith(sfx) and decl[: -len(sfx)] in domains:
            return decl[: -len(sfx)]
    return None


def _pack_health(pack):
    """pack 部署体检：lane exec 可解析、needs tools/env、creds 文件、probe.sh。"""
    fails = 0
    print(f"== pack {pack.name} (ns {pack.ns})")

    def bad(m):
        nonlocal fails
        fails += 1
        print(f"  ✗ {m}")

    for lane in pack.lanes:
        lname = lane.get("name", "?")
        exec_ = lane.get("exec", "")
        if exec_ == "monolith":
            # 与 monolith_shim 同序：pack.dir 相对路径优先，PATH 兜底
            conn = lane.get("connector", "")
            cpath = Path(conn)
            if not cpath.is_absolute():
                cpath = pack.dir / conn
            if cpath.exists():
                print(f"  ✓ lane {lname}: connector {conn}")
            elif conn and shutil.which(conn):
                print(f"  ✓ lane {lname}: connector {conn} → {shutil.which(conn)}")
            else:
                bad(f"lane {lname}: connector '{conn}' 缺席（pack.dir/PATH 均未命中）")
        else:
            path = Path(exec_)
            if not path.is_absolute():
                path = pack.dir / exec_
            if path.exists():
                print(f"  ✓ lane {lname}: {exec_}")
            else:
                bad(f"lane {lname}: exec {exec_} 缺席")
        needs = lane.get("needs") or {}
        for t in needs.get("tools") or []:
            if shutil.which(t):
                print(f"    ✓ tool {t}")
            else:
                bad(f"tool {t} 缺席（lane {lname}）")
        any_tools = needs.get("tools_any") or []
        if any_tools:
            hit = [t for t in any_tools if shutil.which(t)]
            if hit:
                print(f"    ✓ tools_any {'|'.join(any_tools)} → {hit[0]}")
            else:
                bad(f"tools_any {'|'.join(any_tools)} 全缺（lane {lname}）")
        for e in needs.get("env") or []:
            if os.environ.get(e):
                print(f"    ✓ env {e}")
            else:
                bad(f"env {e} 未设（lane {lname}）")
        for e in needs.get("env_optional") or []:
            if os.environ.get(e):
                print(f"    ✓ env* {e}")
            else:
                print(f"    · env* {e} 未设（可选）")
        for c in needs.get("creds") or []:
            if Path(c).expanduser().exists():
                print(f"    ✓ cred {c}")
            else:
                print(f"    · cred {c} 缺席")
    # [[routes]].lanes 引名必须落在已声明 lane 集——拼错名会让该臂静默空道
    lane_names = {ln.get("name") for ln in pack.lanes}
    for route in pack.routes:
        for ref in route.get("lanes") or []:
            if ref not in lane_names:
                bad(f"route lanes 引用未声明 lane '{ref}'")
    # routes 覆盖自检：[[routes]] 存在时 pack.kinds 每个 kind 须至少被一条臂
    # 覆盖（无 kinds 限制/含 "*" 的臂=兜底臂，覆盖全部）——漏 kind 意味着
    # 该 kind 运行时永远 route_miss rc2（加臂漏兜底的伴生陷阱）
    if pack.routes:
        covered = set()
        for route in pack.routes:
            rk = route.get("kinds")
            if rk is None:
                rk = []
            elif not isinstance(rk, list):
                rk = [rk]
            if not rk or "*" in rk:
                covered.update(pack.kinds)
            else:
                covered.update(k for k in rk if k in pack.kinds)
        uncovered = [k for k in pack.kinds if k not in covered]
        if uncovered:
            bad(f"routes 无臂覆盖 kinds: {', '.join(uncovered)}")
        else:
            print(f"  ✓ routes 覆盖全部 {len(pack.kinds)} kind")
    # writes_cred 自检：声明的 ns/domain 须映射到 lgc 已知 cred domain
    # （CRED_DOMAINS ∪ NS_CRED_DOMAIN 表；读 lgc 脚本事实源不另抄一份）
    writes = set()
    if pack.writes_cred:
        writes.add(pack.writes_cred)
    for ln in pack.lanes:
        if ln.get("writes_cred"):
            writes.add(ln["writes_cred"])
    need_surf = bool(writes) or bool(pack.cred_domain)
    surf = _lgc_cred_surface() if need_surf else None
    if pack.cred_domain:
        if surf is None:
            print("  · cred_domain 校验跳过（lgc 脚本不可解析）")
        elif pack.cred_domain in surf[2]:
            print(f"  ✓ cred_domain '{pack.cred_domain}'")
        else:
            bad(f"cred_domain '{pack.cred_domain}' 不在 lgc CRED_FILES 域表")
    if writes:
        if surf is None:
            print("  · writes_cred 校验跳过（lgc 脚本不可解析）")
        else:
            domains, nsmap = surf[0], surf[1]
            for w in sorted(writes):
                dom = _cred_domain_of(w, domains, nsmap)
                if dom:
                    print(f"  ✓ writes_cred {w} → cred domain '{dom}'")
                else:
                    bad(f"writes_cred '{w}' 不映射任何已知 lgc cred domain")
    probe = pack.dir / "probe.sh"
    if probe.exists():
        try:
            r = subprocess.run(
                ["bash", str(probe)],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "PACK_DIR": str(pack.dir)},
            )
            for line in r.stdout.rstrip().splitlines():
                print(f"  {line}")
            for line in r.stderr.rstrip().splitlines():
                print(f"  ! {line}")
            if r.returncode == 0:
                print("  ✓ probe.sh")
            else:
                bad(f"probe.sh rc{r.returncode}")
        except subprocess.TimeoutExpired:
            bad("probe.sh 超时(90s)")
    return fails


def cmd_selftest(args):
    if not args.pack and not args.deploy:
        return 0 if _fixture_selftest() == 0 else 1
    fails = _lgc_health()
    load_errors = []
    packs = load_packs(errors=load_errors)
    for e in load_errors:
        fails += 1
        print(f"  ✗ pack 解析失败: {e}")
    if args.pack:
        packs = [p for p in packs if p.name == args.pack]
        if not packs:
            print(f"selftest: pack '{args.pack}' 不在 {PACKS_DIR}")
            return 2
    for p in packs:
        fails += _pack_health(p)
    if fails:
        print(f"selftest: FAIL ({fails} problems)")
        return 1
    print("selftest: PASS")
    return 0


# ---------------------------------------------------------------- packs 列表


def cmd_packs(args):
    """packs [--json]：已加载 pack 的机读面（name/desc/kinds/hosts/schemes/lanes/bare）。
    解析失败的 pack 进 errors 键——机读面静默漏报已部署 pack 比炸更糟。"""
    errs = []
    packs = load_packs(errors=errs)
    rows = []
    for p in packs:
        row = {
            "name": p.name,
            "desc": p.desc,
            "kinds": p.kinds,
            "hosts": p.hosts,
            "schemes": p.schemes,
            "lanes": [lc.get("name", "lane") for lc in p.lanes],
            "bare": bool(p.bare),
        }
        if p.cred_domain:
            row["cred_domain"] = p.cred_domain
        rows.append(row)
    if args.json:
        out = {"packs": rows}
        if errs:
            out["errors"] = errs
        print(json.dumps(out, ensure_ascii=False))
        return 0
    for r in rows:
        print(f"{r['name']}: kinds={','.join(r['kinds'])} lanes={','.join(r['lanes'])}")
        if r["desc"]:
            print(f"  {r['desc']}")
    return 0


# ---------------------------------------------------------------- main


def kv_pair(s):
    if "=" in s:
        k, v = s.split("=", 1)
        return k, v
    return s, True


def _truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fetch-engine", description="fetch substrate engine"
    )
    ap.add_argument("--version", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="fetch a target")
    r.add_argument("target")
    r.add_argument("-o", "--outdir", type=Path)
    r.add_argument("-p", "--pack")
    r.add_argument("--json", action="store_true")
    r.add_argument(
        "--plan",
        action="store_true",
        help="dry-run：决策面输出（plan dict），不跑车道不写缓存",
    )
    r.add_argument("--budget-ms", type=int, default=120000)
    r.add_argument(
        "--param",
        action="append",
        type=kv_pair,
        help="flag-style param (--param refresh → refresh=true)",
    )
    r.add_argument("kv", nargs="*", type=kv_pair, help="k=v params")

    lr = sub.add_parser("lane-run", help="run one lane standalone")
    lr.add_argument("lane")
    lr.add_argument("req", nargs="?", default=None)

    cf = sub.add_parser("conformance", help="check a lane against lane-abi §11")
    cf.add_argument("lane")
    cf.add_argument("--kind", default="article")
    cf.add_argument("--budget-ms", type=int, default=10000)

    st = sub.add_parser(
        "selftest",
        help="fixture conformance；--deploy/-p 加 lgc/pack 部署体检 (doctor.sh 合一)",
    )
    st.add_argument("-p", "--pack", help="只体检单个 pack")
    st.add_argument("--deploy", action="store_true", help="全部 pack 部署体检")

    pk = sub.add_parser("packs", help="列出已加载 pack（--json 机读面）")
    pk.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.version:
        print(f"fetch-engine {VERSION} (abi {ABI})")
        return 0
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "lane-run":
        return cmd_lane_run(args)
    if args.cmd == "conformance":
        return cmd_conformance(args)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    if args.cmd == "packs":
        return cmd_packs(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
