#!/usr/bin/env python3
r"""check_readback_tex.py — 把渲染出的词回读对照已审计 box。

  check_readback_tex.py FIG.pdf [FIG.audit] [--depth BP] [--quiet]

'pdftotext -bbox' 报告渲染页上每个词的真实包围盒（poppler 坐标：
左上原点、y 向下、单位 bp = 1/72in）。.audit 文件报告 pgf 坐标的
已审计 box（TeX pt = 1/72.27in）。两套坐标由 vizaudit.tex 在每个
tikzpicture 末尾写出的 'origin' 行桥接：

  origin <picid> <picminx> <picminy> <picmaxx> <picmaxy> <paperw> <paperh>

（无 '|'——check_audit.py 的解析器会忽略它）。该行作用于回溯到上
一条 origin 行之间的审计行。标准 standalone 裁剪下页面 = 图形 bbox
加均匀边框，所以
  border = (page - pic)/2          （由 PDF 自身页尺寸推出）
  x_pop   = (x_pgf - picminx)*s + bx
  y_pop   = pageH - ((y_pgf - picminy)*s + by)      s = 72/72.27 bp per pt

规则（全部 warn 级，退出 0）：

  - 词盒在两轴上都侵入已审计 box 内部超过 --depth bp 且未完全落在
    其中——box 边界切穿了词
      warn readback: word "X" crosses audited box "N"
    ——这是文字压框边或未审计对象撞框边的特征。旧测试要求词的中心
    在 box 外，但 Rect.contains 把边界算内部，所以骑在边上的标签
    （最常见的骑跨）会漏网。完全落在已审计 box 内的词保持静默——
    内部隐藏文本归 coverage 管，不归 readback。
  - 声明的 \vzwire 折线段穿入词盒超过 --depth bp
      warn readback: wire "W" crosses word "X" (N.Nbp)
    ——connector 压文字的碰撞是已审计 box 看不到的（wire 的
    endpoint=/via= 豁免只管 box，不管词）。折线端点落在距词盒
    WIRE_ENDPOINT_BP 以内算正常连接，不算穿越。与 box 检查同受
    origin 校准门控。
  - 同页两个保留词盒相交深度超过 --depth bp
      warn readback: word "X" overlaps word "Y" (N.Nbp)
    ——字压字的碰撞没有已审计 box 能看到（标签叠在另一标签上、文本
    完全藏进 box 自己的标签里）。与 box 检查同受校准门控：origin
    行缺失或不可映射时 pair 检查同样跳过。
  - 词盒完全落在页面裁剪之外
      warn readback: word "X" outside page

可见字符（字母/数字/CJK）少于 2 个或纯标点的词跳过——它们是常见
的数学字形噪声。

校准限制：box 映射要求恰好一条 origin 行与恰好一页；多 picture
文档、多页 PDF 或页面在图之外还有内容都会让边框推导变得近似——
检查器此时告警并跳过 box 检查，而不是产出自信垃圾。.audit 缺失或
没有 origin 行时退化为只做 outside-page 检查——常见原因是
vizaudit 在正文里加载（此时文件自我告警并跳过；它必须在 preamble
里 \input）。
"""

import argparse
import html
import re
import shutil
import subprocess
import sys
import unicodedata
from itertools import pairwise
from pathlib import Path

from auditgeom import Rect, audit_rows, seg_rect_depth

PT_TO_BP = 72.0 / 72.27
# 页面远大于 pic+border 说明图旁边还有内容——居中边框映射可能
# 不准；告警而非静默信任
MAX_SANE_BORDER_BP = 40.0
# 包含测试的浮点余量——真实 inner-sep 间隙约 3bp
CONTAIN_EPS_BP = 0.1
# wire 端点距词盒这么近算正常连接
WIRE_ENDPOINT_BP = 2.0

PAGE_RE = re.compile(r"<page[^>]*width=\"([\d.]+)\"[^>]*height=\"([\d.]+)\"")
WORD_RE = re.compile(
    r"<word[^>]*xMin=\"(-?[\d.]+)\"[^>]*yMin=\"(-?[\d.]+)\""
    r"[^>]*xMax=\"(-?[\d.]+)\"[^>]*yMax=\"(-?[\d.]+)\"[^>]*>(.*?)</word>",
    re.DOTALL,
)


class Word(Rect):
    __slots__ = ("page", "text")

    def __init__(self, x0, y0, x1, y1, text, page):
        super().__init__(x0, y0, x1, y1)
        self.text, self.page = text, page


def pdftotext_words(pdf, log):
    """[(Word)] + [每页 (w,h)]；pdftotext 无法运行时返回 None。"""
    if shutil.which("pdftotext") is None:
        log.append("readback: pdftotext not found; skipped")
        return None
    proc = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        log.append(f"readback: pdftotext failed: {proc.stderr.strip()[:120]}")
        return None
    words, pages, cur = [], [], 0
    for ln in proc.stdout.splitlines():
        pm = PAGE_RE.search(ln)
        if pm:
            pages.append((float(pm.group(1)), float(pm.group(2))))
            continue
        if ln.strip().startswith("</page"):
            cur += 1
            continue
        wm = WORD_RE.search(ln)
        if wm:
            words.append(
                Word(
                    *(float(wm.group(i)) for i in range(1, 5)),
                    html.unescape(wm.group(5)),
                    cur,
                )
            )
    return words, pages


def parse_audit(path):
    """归属到各 origin 的 boxes+wires：'origin' 描述其前的行。"""
    boxes, wires, origins, pending = [], [], [], []
    for row in audit_rows(path):
        if row[0] == "origin":
            origins.append({"pic": row[1], "vals": row[2]})
            for b in pending:
                b["origin"] = len(origins) - 1
            pending = []
            continue
        _etype, kind, name, vals, _tags = row
        if kind not in {"node", "region", "wire"} or vals is None:
            continue
        if kind == "wire":
            if len(vals) < 4 or len(vals) % 2:
                continue
            b = {
                "name": name,
                "pts": list(zip(vals[::2], vals[1::2], strict=True)),
                "origin": None,
            }
            wires.append(b)
        else:
            if len(vals) != 4:
                continue
            b = {"name": name, "rect": vals, "origin": None}
            boxes.append(b)
        pending.append(b)
    if origins:  # 末条 origin 之后的行也归它
        for b in pending:
            b["origin"] = len(origins) - 1
    return boxes, wires, origins


def border_of(origin_vals, page_w, page_h):
    """standalone 裁剪边框 (bx, by)（bp）；非裁剪时为负。"""
    minx, miny, maxx, maxy, _pw, _ph = origin_vals
    return (
        (page_w - (maxx - minx) * PT_TO_BP) / 2,
        (page_h - (maxy - miny) * PT_TO_BP) / 2,
    )


def map_box(vals, origin_vals, page_w, page_h):
    """pgf-pt 矩形 -> poppler-bp 矩形；几何非裁剪时返回 None。"""
    minx, miny = origin_vals[0], origin_vals[1]
    bx, by = border_of(origin_vals, page_w, page_h)
    if bx < -1.0 or by < -1.0:
        return None, (bx, by)  # 图比页还宽——不是干净的裁剪
    x0, y0, x1, y1 = vals
    return (
        Rect(
            (x0 - minx) * PT_TO_BP + bx,
            page_h - ((y1 - miny) * PT_TO_BP + by),
            (x1 - minx) * PT_TO_BP + bx,
            page_h - ((y0 - miny) * PT_TO_BP + by),
        ),
        (bx, by),
    )


def map_wire_pts(pts, origin_vals, page_w, page_h):
    """pgf-pt 折线 -> poppler-bp 点列，走同一边框映射。"""
    minx, miny = origin_vals[0], origin_vals[1]
    bx, by = border_of(origin_vals, page_w, page_h)
    return [
        ((x - minx) * PT_TO_BP + bx, page_h - ((y - miny) * PT_TO_BP + by))
        for x, y in pts
    ]


def visible_chars(text):
    return [
        c for c in text if not c.isspace() and unicodedata.category(c)[0] not in "PS"
    ]


def word_overlaps(words, depth):
    """同页词盒对相交深度超过 depth 时的 warn 串。

    与 crosses 规则不同，这里没有中心豁免——两个词盒的任何真实重叠
    都是字印在了字上。只比较同页的词对。
    """
    out = []
    for i, a in enumerate(words):
        for b in words[i + 1 :]:
            if a.page != b.page:
                continue
            dx, dy = a.overlap_depth(b)
            if dx > depth and dy > depth:
                out.append(
                    f'readback: word "{a.text}" overlaps word "{b.text}" '
                    f"({min(dx, dy):.1f}bp)"
                )
    return out


def box_crossings(words, mapped, depth):
    """词盒骑跨已审计 box 边界时的 warn 串。

    词在两轴上侵入 box 内部超过 depth 且未完全落在其中，说明边界切
    穿了词——能逮到旧的「中心在外」测试漏掉的骑边标签。完全在内的
    词保持静默（内部隐藏文本归 coverage 管）；完全在外或擦入不足
    depth 的词同样静默。
    """
    out = []
    for w in words:
        for name, r in mapped:
            dx, dy = r.overlap_depth(w)
            if dx > depth and dy > depth and not r.contains(w, CONTAIN_EPS_BP):
                out.append(
                    f'readback: word "{w.text}" crosses audited box '
                    f'"{name}" ({min(dx, dy):.1f}bp)'
                )
    return out


def wire_word_crossings(wires, words, depth, endpoint_bp=WIRE_ENDPOINT_BP):
    """声明的 wire 折线切穿词盒时的 warn 串。

    wires: [(name, [(x,y), ...])] 已映射到 poppler bp；words: 映射页
    上保留下来的词。折线端点落在距词盒 endpoint_bp 以内算正常连接
    ——即使线头擦到盒边，该 (wire, word) 对也豁免。
    """
    out = []
    for name, pts in wires:
        if len(pts) < 2:
            continue
        for w in words:
            if min(w.pt_gap(*e) for e in (pts[0], pts[-1])) <= endpoint_bp:
                continue
            deep = max(seg_rect_depth(p, q, w) for p, q in pairwise(pts))
            if deep > depth:
                out.append(
                    f'readback: wire "{name}" crosses word "{w.text}" ({deep:.1f}bp)'
                )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("audit", type=Path, nargs="?")
    ap.add_argument(
        "--depth",
        type=float,
        default=1.0,
        help="bp of interior penetration that counts as a crossing",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.pdf.exists():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2
    audit = args.audit or args.pdf.with_suffix(".audit")

    warns = []
    got = pdftotext_words(args.pdf, warns)
    if got is None:
        for w in warns:
            print(f"  warn {w}")
        return 0
    words, pages = got

    kept = [w for w in words if len(visible_chars(w.text)) >= 2]

    # 出页检查：每个保留词、每页都查。骑跨裁剪边界的词是被部分裁
    # 掉——比完全在外更温和的另一类特征（standalone 裁剪会随内容
    # 增大，所以骑跨意味着内容戳过了边框余量）。
    for w in kept:
        pw, ph = pages[w.page] if w.page < len(pages) else (0, 0)
        if w.x1 < 0 or w.y1 < 0 or w.x0 > pw or w.y0 > ph:
            warns.append(
                f'readback: word "{w.text}" outside page '
                f"({w.x0:.1f},{w.y0:.1f})-({w.x1:.1f},{w.y1:.1f})"
            )
        elif w.x0 < 0 or w.y0 < 0 or w.x1 > pw or w.y1 > ph:
            warns.append(
                f'readback: word "{w.text}" clipped at page edge '
                f"({w.x0:.1f},{w.y0:.1f})-({w.x1:.1f},{w.y1:.1f})"
            )

    boxes, wires, origins = [], [], []
    if audit.exists():
        boxes, wires, origins = parse_audit(audit)
    else:
        warns.append(f"readback: no {audit.name}; box checks skipped")

    mapped = []
    geom_ok = False  # origin 映射已校准——同时门控 box 与词对检查
    if not boxes:
        # 没有可映射的东西，但单页单 origin 仍给词对检查一个可用框架
        geom_ok = len(origins) == 1 and len(pages) == 1
    elif not origins:
        warns.append(
            "readback: .audit has no origin row — vizaudit was not loaded in "
            "the preamble (body/in-picture \\input is skipped by guard) or "
            "an old vizaudit; box checks skipped"
        )
    elif len(origins) > 1 or len(pages) > 1:
        warns.append(
            f"readback: {len(origins)} origin rows / {len(pages)} pages — "
            "border map only calibrated for single-picture standalone; "
            "box checks skipped"
        )
    else:
        pw, ph = pages[0]
        bad_border = False
        for b in boxes:
            r, (bx, by) = map_box(b["rect"], origins[0]["vals"], pw, ph)
            if r is None:
                bad_border = True
                break
            mapped.append((b["name"], r))
        if bad_border:
            warns.append(
                "readback: picture bbox exceeds page crop — not a "
                "standalone crop? box checks skipped"
            )
            mapped = []
        else:
            geom_ok = True
            bx, by = border_of(origins[0]["vals"], pw, ph)
            if bx > MAX_SANE_BORDER_BP or by > MAX_SANE_BORDER_BP:
                warns.append(
                    f"readback: page margin {bx:.0f}/{by:.0f}bp exceeds the "
                    "usual standalone border — page probably holds content "
                    "besides the figure; box map approximate"
                )

    mapped_wires = []
    if geom_ok and wires:
        pw, ph = pages[0]
        bx, by = border_of(origins[0]["vals"], pw, ph)
        if bx >= -1.0 and by >= -1.0:  # 与 box 同款的非干净裁剪守卫
            mapped_wires = [
                (b["name"], map_wire_pts(b["pts"], origins[0]["vals"], pw, ph))
                for b in wires
            ]

    kept0 = [w for w in kept if w.page == 0]
    warns.extend(box_crossings(kept0, mapped, args.depth))

    # 词对词：同页任意两保留词盒相交超过 --depth——字压字碰撞，
    # 同受该校准门控；wire 对词在同一门控之上再叠加边框合理性检查
    if geom_ok:
        warns.extend(word_overlaps(kept, args.depth))
        warns.extend(wire_word_crossings(mapped_wires, kept0, args.depth))

    if not args.quiet:
        print(
            f"{args.pdf.name}: {len(words)} words ({len(kept)} checked), "
            f"{len(mapped)} mapped boxes, {len(mapped_wires)} wires, "
            f"{len(pages)} page(s)"
        )
    for w in warns:
        print(f"  warn {w}")
    if not warns:
        print("  all readback checks clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
