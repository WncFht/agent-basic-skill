#!/usr/bin/env python3
"""xyzfm_tr.py — 官方文字稿车道（kind=tr）。

链：episode 页 __NEXT_DATA__ → transcriptMediaId → POST episode-transcript/get
（token+device-id 安卓头套）→ transcriptUrl 签名链（CDN UA ACL）→ gzip JSON
[{text,startMs}] → transcript.txt；shownotes.md + meta.json 是页面白送副产。

错误映射：
- token.json 缺席/无 access_token / API 401|403 → auth_expired（cred 域账，
  engine 级联让位 xyzfm-sn——级联本意）
- 无 transcriptMediaId 或转写键空 → notcovered（lane×key 30d，重试跳过本
  lane 直接供 shownotes；绝不能报 noresults——内容键 24h neg 会连兜底一起锁）
- episode 页 404/410 → permanent（内容墓碑，级联唯一短路的类）
- 其余 HTTP/网络/解析 → transient
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def classify_http(e, stage):
    """stage ∈ page|api|cdn——同一状态码按面映射不同类。"""
    s = e.status
    if s in (401, 403):
        if stage == "api":
            return "auth_expired", f"api HTTP {s}——token 失效，link-get --mint 重铸"
        # www 页 WAF / CDN 签名过期与凭证无关——挂 auth 账会谎报 mint 需求
        return "transient", f"{stage} HTTP {s}：{e.body[:120]!r}"
    if s in (404, 410):
        if stage == "page":
            return "permanent", f"episode 页 HTTP {s}——内容已删除"
        return "notcovered", f"{stage} HTTP {s}——该集无官方转写"
    if s == 429:
        return "rate_limited", f"{stage} HTTP 429"
    if s == 0:
        return "transient", f"{stage} 响应解析失败：{e.body[:120]!r}"
    return "transient", f"{stage} HTTP {s}：{e.body[:120]!r}"


def main():
    req = _lib.read_req()
    ident = req["identity"]
    ctx = req["ctx"]
    adir = Path(ctx["artifact_dir"])
    adir.mkdir(parents=True, exist_ok=True)
    timeout = min(30.0, _lib.budget_s(ctx) / 3)

    # 形状闸：tr 臂只接 /episode/——kind_miss 兜底页（首页等）让给 sn lane
    eid = _lib.eid_of(ident.get("raw") or "")
    if not eid:
        _lib.skip("xyzfm-tr: 非 /episode/ 形")

    tok = _lib.load_token()
    if not tok:
        _lib.die(
            "auth_expired",
            "~/.config/xyzfm/token.json 缺席或无 access_token——"
            "link-get --mint <episode-url> 扫码铸凭证",
            retryable=True,
        )

    _lib.progress(f"episode {eid}：拉页面元数据")
    try:
        ep = _lib.fetch_episode(eid, timeout)
    except _lib.HttpFail as e:
        cls, ev = classify_http(e, "page")
        _lib.die(cls, ev, retryable=(cls in ("transient", "rate_limited")))
    if not ep:
        _lib.die(
            "transient", "episode 页无 episode JSON（页面结构变更？）", retryable=True
        )

    media_id = _lib.media_id_of(ep)
    if not media_id:
        _lib.die("notcovered", "episode 无 transcriptMediaId——该集无官方转写")

    _lib.progress("换转写签名链")
    try:
        td = _lib.transcript_get(eid, media_id, tok, timeout)
    except _lib.HttpFail as e:
        cls, ev = classify_http(e, "api")
        _lib.die(cls, ev, retryable=(cls in ("transient", "rate_limited")))
    turl = td.get("transcriptUrl") or ""
    if not turl:
        _lib.die("notcovered", "transcript/get 无 transcriptUrl——该集无官方转写")

    _lib.progress("拉转写体")
    try:
        segs = _lib.transcript_fetch(turl, timeout)
    except _lib.HttpFail as e:
        cls, ev = classify_http(e, "cdn")
        _lib.die(cls, ev, retryable=(cls in ("transient", "rate_limited")))
    if not segs:
        _lib.die("notcovered", "转写体为空——该集无官方转写")

    tr_path = adir / "transcript.txt"
    _lib.write_text(tr_path, _lib.render_transcript(segs))
    sn_path = adir / "shownotes.md"
    _lib.write_text(
        sn_path,
        f"# {ep.get('title') or eid}\n\n" + _lib.html2md(ep.get("shownotes") or ""),
    )
    meta_path = adir / "meta.json"
    _lib.write_json(
        meta_path,
        _lib.meta_of(
            ep,
            "transcript",
            {
                "transcript_vendor": td.get("vendorDeclaration"),
                "transcript_key": td.get("key"),
                "transcript_segments": len(segs),
            },
        ),
    )

    items = []
    for p, name in (
        (tr_path, "transcript.txt"),
        (sn_path, "shownotes.md"),
        (meta_path, "meta.json"),
    ):
        _lib.artifact(p, name)
        items.append({"path": str(p), "name": name, "bytes": p.stat().st_size})
    _lib.result(items, params={"form": "transcript"})


if __name__ == "__main__":
    main()
