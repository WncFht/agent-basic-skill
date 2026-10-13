#!/usr/bin/env python3
"""xyzfm_sn.py — shownotes/简介匿名车道（kind=art + tr 臂内兜底）。

无凭证面：只打 www.xiaoyuzhoufm.com 页面 __NEXT_DATA__。
- /episode/<eid> → shownotes.md（HTML→md）+ meta.json
- /podcast/<pid> → article.md（节目简介+集表）+ meta.json
- 其余页 → title/description 尽力提取 → article.md，提不出 → noresults

在 tr 臂内当兜底时产物按请求键入 tr:<eid>——result.params form=shownotes
与 satisfies 断言互锁，不污染后续转写探测（pack.toml [identity].satisfies）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def emit_items(adir, files, form="shownotes", meta=None):
    items = []
    for p, name in files:
        _lib.artifact(p, name)
        items.append({"path": str(p), "name": name, "bytes": p.stat().st_size})
    _lib.result(items, params={"form": form})


def main():
    req = _lib.read_req()
    ident = req["identity"]
    ctx = req["ctx"]
    adir = Path(ctx["artifact_dir"])
    adir.mkdir(parents=True, exist_ok=True)
    timeout = min(25.0, _lib.budget_s(ctx) / 2)
    raw = ident.get("raw") or ""

    eid = _lib.eid_of(raw)
    pid = _lib.pid_of(raw)

    if eid:
        _lib.progress(f"episode {eid}：拉 shownotes")
        try:
            ep = _lib.fetch_episode(eid, timeout)
        except _lib.HttpFail as e:
            if e.status in (404, 410):
                _lib.die("permanent", f"episode 页 HTTP {e.status}——内容已删除")
            _lib.die("transient", f"episode 页拉取失败 HTTP {e.status}", retryable=True)
        if not ep:
            _lib.die("transient", "episode 页无 episode JSON", retryable=True)
        sn = adir / "shownotes.md"
        _lib.write_text(
            sn,
            f"# {ep.get('title') or eid}\n\n" + _lib.html2md(ep.get("shownotes") or ""),
        )
        mp = adir / "meta.json"
        _lib.write_json(mp, _lib.meta_of(ep, "shownotes"))
        emit_items(adir, [(sn, "shownotes.md"), (mp, "meta.json")])
        return

    if pid:
        _lib.progress(f"podcast {pid}：拉节目页")
        try:
            pod, eps = _lib.fetch_podcast(pid, timeout)
        except _lib.HttpFail as e:
            if e.status in (404, 410):
                _lib.die("permanent", f"podcast 页 HTTP {e.status}——内容已删除")
            _lib.die("transient", f"podcast 页拉取失败 HTTP {e.status}", retryable=True)
        if not pod:
            # 页面 200 但 pageProps.podcast 缺席——与 episode 分支同判暂性抖动；
            # noresults 会给内容键落 24h 墓碑（pack.toml 头注同禁）
            _lib.die(
                "transient",
                "podcast 页无 podcast JSON（页面结构变更？）",
                retryable=True,
            )
        lines = [f"# {pod.get('title') or pid}", ""]
        if pod.get("author"):
            lines.append(f"主播：{pod['author']}\n")
        brief = pod.get("brief") or pod.get("description") or ""
        if brief:
            lines.append(brief.strip() + "\n")
        if pod.get("episodeCount"):
            lines.append(f"共 {pod['episodeCount']} 集\n")
        if eps:
            lines.append("## 集表\n")
            for e in eps[:50]:
                if isinstance(e, dict) and e.get("eid"):
                    t = e.get("title") or e["eid"]
                    lines.append(
                        f"- [{t}](https://www.xiaoyuzhoufm.com/episode/{e['eid']})"
                    )
        art = adir / "article.md"
        _lib.write_text(art, "\n".join(lines) + "\n")
        mp = adir / "meta.json"
        _lib.write_json(
            mp,
            {
                "platform": "xyzfm",
                "form": "shownotes",
                "pid": pod.get("pid") or pid,
                "title": pod.get("title"),
                "url": f"https://www.xiaoyuzhoufm.com/podcast/{pid}",
                "episode_count": pod.get("episodeCount"),
            },
        )
        emit_items(adir, [(art, "article.md"), (mp, "meta.json")])
        return

    # 其他 xiaoyuzhoufm 页面：尽力提取 NEXT_DATA 标题/描述
    try:
        raw_page = _lib.http_get(raw, timeout=timeout)
    except _lib.HttpFail as e:
        if e.status in (404, 410):
            _lib.die("permanent", f"HTTP {e.status}——页面不存在")
        _lib.die("transient", f"页面拉取失败 HTTP {e.status}", retryable=True)
    html = raw_page.decode("utf-8", errors="replace")
    import re as _re

    title = ""
    m = _re.search(r"<title[^>]*>([^<]+)</title>", html)
    if m:
        title = m.group(1).strip()
    desc = ""
    m = _re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html
    )
    if m:
        desc = m.group(1).strip()
    if not (title or desc):
        # SPA 壳页/结构漂移同判暂性——noresults 会落内容键 24h 墓碑错杀活页
        _lib.die("transient", "页面无可提取文本（JS 壳或结构变更）", retryable=True)
    art = adir / "article.md"
    _lib.write_text(art, f"# {title}\n\n{desc}\n")
    emit_items(adir, [(art, "article.md")])


if __name__ == "__main__":
    main()
