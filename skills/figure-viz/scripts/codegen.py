#!/usr/bin/env python3
r"""codegen.py — 语义/几何台账 JSON → 带 vaudit 埋点的 standalone .tex 骨架。

用法：
    codegen.py LEDGER.json [-o OUT.tex] [--assets DIR]

LEDGER.json（坐标一律 cm，tikzpicture 直角坐标 x 右 y 上；canvas 是名义
正文区矩形 [0,w]x[0,h]，mean 含义框与标识行由 codegen 自动落在底边之下）:

    {"canvas": {"w": 12.0, "h": 8.0},
     "boxes":  [{"id": "a1", "class": "blk",
                "style": "model, draw=vteal, fill=vteal!14",
                "x": 2.0, "y": 5.5, "text": "{\\small $A$}",
                "inside": "bandA", "alignx": "b1", "aligny": "..",
                "eqwh": "..", "adjacent": "..", "overlap": ".."}],
     "bands":  [{"id": "bandA", "sw": [0.0, 4.4], "ne": [12.0, 6.6],
                "style": "band=vteal", "tags": "class=band"}],
     "wires":  [{"id": "w1", "pts": ["a1.east", "5.0,5.5", "a2.west"],
                "endpoint": "a1,a2", "via": "bandA", "style": "varr"}],
     "mean":   {"text": "\\textbf{对象}\\quad ..."},
     "caption":{"text": "..."}}

字段细则：
  - box 的审计键（class/square/twin/eqww/eqhh/eqwh/eqhw/inside/alignx/
    aligny/adjacent/overlap/tiles）可写字符串或字符串列表，逐个展开成
    vaudit={k=v,...}；未给任何审计键也照发 vaudit={}（注册盒参与
    WIRE-CROSS/COLLIDE/CROWD）。
  - band.sw/ne 接受 [x,y] 或 "x,y"；style 缺省 "band"；tags 原样进
    \vzbbox 第四参数（可写 class=band,inside=outer 等）。
  - wire.pts 元素接受 "a.east" 节点锚、"x,y" 裸坐标或 "(...)" 原样段；
    endpoint/via 接受 "a,b" 或列表；style 缺省 "varr"。
  - mean/caption 可省；缺 caption 时留注释占位不造空节点。

产出骨架：\documentclass{standalone} + \input{vizstyle.tex} +
\input{vizaudit.tex}（--assets DIR 时写成 \input{DIR/vizstyle.tex}，
供脱离 render_tex TEXINPUTS 注入的 tex 工程用）。box → 带 vaudit 全
标签 \node；band → bg 层 \fill[band] + \vzbbox（角点自动排序）；wire →
\draw[varr] + 镜像 \vzwire。自洽台账产出的骨架编译即审计全绿。

自洽检查（不阻断，一律 'warn codegen:'）：重复 id、引用不存在的对象、
box 中心/band 角点越出 canvas、band 角点颠倒（自动交换）、inside 目标
带不覆盖 box 中心、wire 途经点少于 2、box 缺 text（mdot/msq/circle/
coordinate 类标记节点豁免）、canvas 缺失（mean/标识行按内容底沿下推）。

输出：-o 写文件并 stdout 打 'ok: <file>'；无 -o 时 tex 上 stdout、
'ok:' 与 warn 走 stderr。用法/输入非法 exit 2。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

AUDIT_KEYS = (
    "class",
    "square",
    "twin",
    "eqww",
    "eqhh",
    "eqwh",
    "eqhw",
    "inside",
    "alignx",
    "aligny",
    "adjacent",
    "overlap",
    "tiles",
)
REF_KEYS = (
    "inside",
    "alignx",
    "aligny",
    "adjacent",
    "overlap",
    "twin",
    "tiles",
    "eqww",
    "eqhh",
    "eqwh",
    "eqhw",
)
NODE_NAME_RE = re.compile(r"^[A-Za-z][\w.:-]*$")
TAG_REF_RE = re.compile(
    r"(?:inside|adjacent|overlap|tiles|alignx|aligny|twin|"
    r"eqww|eqhh|eqwh|eqhw)\s*=\s*([^,\]]+)"
)


class UsageError(Exception):
    """输入/用法非法 -> exit 2"""


def as_list(v):
    """'a' -> ['a']; ['a','b'] -> 原样；None/缺省 -> []。"""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def wire_pts(w):
    """pts 归一为途经点列表：数组原样（元素可为 [x,y]）；';' 分隔串按
    \\vzwire 途经点惯例拆分——agent 写台账很容易照搬该写法，静默按
    字符迭代会产出 t--o--k 式废线，必须挡住。"""
    v = w.get("pts")
    if isinstance(v, str):
        return [s.strip() for s in v.split(";") if s.strip()]
    if isinstance(v, (list, tuple)):
        return list(v)
    return []


def num(v) -> str:
    """3.0 -> '3'; 3.25 -> '3.25'（cm 文本，最多 4 位小数）。"""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return s or "0"


def pt_token(p):
    """wire 途经点统一成 '(...)'：'a.east'->'(a.east)'，'1.5,2'->'(1.5,2)'，
    已带括号或 calc '($..$)' 原样。\\vzwire 的 paren-led 通道原样进 pgf
    扫描器，\\draw 同样需要括号形式——一份 token 两处用。"""
    if isinstance(p, (list, tuple)):
        return f"({num(p[0])},{num(p[1])})"
    s = str(p).strip()
    if s.startswith("("):
        return s
    return f"({s})"


def load_ledger(path: Path):
    try:
        led = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise UsageError(f"{path}: {e}") from e
    if not isinstance(led, dict):
        raise UsageError("top level must be a JSON object")
    for key in ("boxes", "bands", "wires"):
        v = led.get(key) or []
        if not isinstance(v, list):
            raise UsageError(f'"{key}" must be a list')
        for i, e in enumerate(v):
            if not isinstance(e, dict):
                raise UsageError(f"{key}[{i}] must be an object")
    return led


def check(led, canvas):
    """台账自洽检查 -> warns 列表（不抛错；生成物照样落盘）。"""
    warns = []
    boxes = led.get("boxes") or []
    bands = led.get("bands") or []
    wires = led.get("wires") or []
    ids = {}
    for b in boxes + bands:
        bid = b.get("id") if isinstance(b, dict) else None
        if bid is None:
            warns.append("entry without 'id' skipped")
            continue
        bid = str(bid)
        if bid in ids:
            warns.append(f"duplicate id {bid!r}")
        ids[bid] = b
        if not NODE_NAME_RE.match(bid):
            warns.append(f"id {bid!r} 不是稳妥的 tikz 节点名（字母起头、仅 \\w.:-）")
    band_ids = {str(b.get("id")) for b in bands if isinstance(b, dict)}

    def check_ref(owner, key, ref):
        if ref not in ids:
            warns.append(f"{owner}: {key}= refers to unknown {ref!r}")

    for b in boxes:
        if "id" not in b:
            continue  # 上面已警告 "entry without 'id' skipped"
        bid = str(b.get("id", "?"))
        try:
            bx, by = float(b["x"]), float(b["y"])
        except (KeyError, TypeError, ValueError):
            raise UsageError(f"box {bid!r}: need numeric x,y")
        if canvas and not (0 <= bx <= canvas[0] and 0 <= by <= canvas[1]):
            warns.append(
                f"box {bid}: center ({num(bx)},{num(by)}) outside "
                f"canvas {num(canvas[0])}x{num(canvas[1])}"
            )
        if not b.get("text") and not any(
            m in str(b.get("style", ""))
            for m in ("mdot", "msq", "circle", "coordinate")
        ):
            warns.append(f"box {bid}: empty text")
        for key in AUDIT_KEYS:
            for ref in as_list(b.get(key)):
                if key in REF_KEYS:
                    check_ref(bid, key, ref)
                if ref == bid:
                    warns.append(f"box {bid}: self-reference {key}={ref}")
        # inside 目标若是 band，box 中心应落在带内
        for ref in as_list(b.get("inside")):
            tgt = ids.get(ref)
            if tgt is None:
                continue
            if ref in band_ids:
                sw, ne = band_rect(tgt)
                if sw[0] is not None and not (
                    sw[0] <= bx <= ne[0] and sw[1] <= by <= ne[1]
                ):
                    warns.append(f"box {bid}: inside={ref} 但中心不在带内")
            else:
                pass  # inside 另一个 box 的包含关系由编译期审计验证

    for b in bands:
        bid = str(b.get("id", "?"))
        rect = band_rect(b)
        if rect[0][0] is None:
            warns.append(f"band {bid}: missing/invalid sw/ne")
            continue
        try:  # sw 应 <= ne；band_rect 已自动交换，这里补警告
            raw_sw = b["sw"]
            raw_ne = b["ne"]
            if isinstance(raw_sw, str):
                raw_sw = [float(t) for t in raw_sw.split(",")]
            if isinstance(raw_ne, str):
                raw_ne = [float(t) for t in raw_ne.split(",")]
            if raw_sw[0] > raw_ne[0] or raw_sw[1] > raw_ne[1]:
                warns.append(f"band {bid}: sw/ne 角点颠倒，已自动交换")
        except (KeyError, TypeError, ValueError, IndexError):
            pass  # missing/invalid 警告上面已覆盖
        (x0, y0), (x1, y1) = rect
        if canvas and (x0 < 0 or y0 < 0 or x1 > canvas[0] or y1 > canvas[1]):
            warns.append(f"band {bid}: rect outside canvas")
        for ref in TAG_REF_RE.findall(str(b.get("tags", ""))):
            check_ref(bid, "tags", ref)

    for w in wires:
        if "id" not in w:
            warns.append("wire entry without 'id' skipped")
            continue
        wid = str(w.get("id", "?"))
        pts = wire_pts(w)
        if len(pts) < 2:
            warns.append(f"wire {wid}: needs >= 2 pts")
        for key in ("endpoint", "via"):
            for clause in as_list(w.get(key)):
                for ref in str(clause).split(","):
                    ref = ref.strip()
                    if ref:
                        check_ref(wid, key, ref)
    return warns


def band_rect(b):
    """(sw, ne) 归一化后的角点；sw/ne 缺失或非法返回 (None, None)。"""
    try:
        sw, ne = b["sw"], b["ne"]
        if isinstance(sw, str):
            sw = [float(t) for t in sw.split(",")]
        if isinstance(ne, str):
            ne = [float(t) for t in ne.split(",")]
        x0, y0, x1, y1 = float(sw[0]), float(sw[1]), float(ne[0]), float(ne[1])
        return (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))
    except (KeyError, TypeError, ValueError, IndexError):
        return (None, None), (None, None)


def vaudit_tags(box):
    tags = []
    for key in AUDIT_KEYS:
        v = box.get(key)
        if v is None:
            continue
        if key == "square" and isinstance(v, bool):
            if v:
                tags.append("square")
            continue
        for ref in as_list(v):
            tags.append(f"{key}={ref}")
    return ",".join(tags)


def gen_tex(led, canvas, assets):
    # check() 已警告过的残缺条目在此跳过（id/x/y 缺一时无法落笔）
    boxes = [
        b
        for b in (led.get("boxes") or [])
        if isinstance(b, dict) and {"id", "x", "y"} <= set(b)
    ]
    bands = [b for b in (led.get("bands") or []) if isinstance(b, dict) and "id" in b]
    wires = [w for w in (led.get("wires") or []) if isinstance(w, dict) and "id" in w]
    mean = led.get("mean") or {}
    caption = led.get("caption") or {}

    # 内容底沿：box 中心与 band 角的最小 y；mean 再往下让 1.6cm
    ys = [float(b["y"]) for b in boxes if "y" in b]
    ys += [band_rect(b)[0][1] for b in bands if band_rect(b)[0][0] is not None]
    content_min = min(ys) if ys else 0.0
    cw = canvas[0] if canvas else 10.0
    cx_mid = cw / 2
    mean_y = min(-1.8, content_min - 1.6)
    cap_y = mean_y - 1.6

    prefix = f"{assets.rstrip('/')}/" if assets else ""
    head = [
        "% generated by codegen.py — 语义台账骨架：几何与埋点已就位，",
        "% 语义文字/样式精修仍是人工活（codegen 管几何正确性）",
        "% ------------------------------------------------------------------",
        "% 几何台账（输入摘要，cm）：",
        (
            f"%   canvas {num(cw)} x {num(canvas[1]) if canvas else '?'}（正文区 "
            "[0,w]x[0,h]；mean/标识行自动落底边之下）"
            if canvas
            else "%   canvas 未给——按内容包围盒推 mean 位置"
        ),
    ]
    for b in boxes:
        head.append(
            f"%   box {b.get('id')} @ ({num(b['x'])},{num(b['y'])})"
            + (f" {vaudit_tags(b)}" if vaudit_tags(b) else "")
        )
    for b in bands:
        sw, ne = band_rect(b)
        if sw[0] is not None:
            head.append(
                f"%   band {b.get('id')} ({num(sw[0])},{num(sw[1])})-"
                f"({num(ne[0])},{num(ne[1])})"
            )
    for w in wires:
        head.append(
            f"%   wire {w.get('id')}: endpoint={w.get('endpoint', '-')}"
            f" via={w.get('via', '-')}"
        )
    head.append("% " + "-" * 66)

    tex = [
        *head,
        r"\documentclass[border=8pt]{standalone}",
        r"\usepackage[UTF8,fontset=fandol]{ctex}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{positioning,calc,fit}",
        f"\\input{{{prefix}vizstyle.tex}}",
        f"\\input{{{prefix}vizaudit.tex}}",
        "",
        r"\begin{document}",
        r"\begin{tikzpicture}[x=1cm,y=1cm]",
        "",
        "% ===== boxes =====",
    ]
    for b in boxes:
        style = str(b.get("style") or "model")
        tags = vaudit_tags(b)
        tex.append(
            f"\\node[{style}, vaudit={{{tags}}}] ({b['id']}) at "
            f"({num(b['x'])},{num(b['y'])}) {{{b.get('text', '')}}};"
        )
    tex += ["", "% ===== bands + wires（bg 层） =====", r"\begin{pgfonlayer}{bg}"]
    for b in bands:
        sw, ne = band_rect(b)
        if sw[0] is None:
            continue
        style = str(b.get("style") or "band")
        tags = str(b.get("tags") or "")
        tex.append(
            f"  \\fill[{style}] ({num(sw[0])},{num(sw[1])}) rectangle "
            f"({num(ne[0])},{num(ne[1])});"
        )
        # 第四参数恒写（可空）：\@ifnextchar[ 会把下一行的 '[' 误吃成 tags
        tex.append(
            f"  \\vzbbox{{{b['id']}}}{{({num(sw[0])},{num(sw[1])})}}"
            f"{{({num(ne[0])},{num(ne[1])})}}[{tags}]"
        )
    for w in wires:
        pts = [pt_token(p) for p in wire_pts(w)]
        if len(pts) < 2:
            continue
        style = str(w.get("style") or "varr")
        ep = ",".join(
            r.strip()
            for c in as_list(w.get("endpoint"))
            for r in str(c).split(",")
            if r.strip()
        )
        via = ",".join(
            r.strip()
            for c in as_list(w.get("via"))
            for r in str(c).split(",")
            if r.strip()
        )
        clauses = []
        if ep:
            clauses.append(f"endpoint={ep}")
        if via:
            clauses.append(f"via={via}")
        tags = " ".join(clauses)
        tex.append(f"  \\draw[{style}] " + " -- ".join(pts) + ";")
        tex.append(f"  \\vzwire{{{w['id']}}}{{{';'.join(pts)}}}{{{tags}}}")
    tex += [r"\end{pgfonlayer}", "", "% ===== 含义框 / 标识行 ====="]
    if mean.get("text"):
        tex.append(
            f"\\node[mean, text width={num(max(cw - 1.0, 2.0))}cm, "
            f"vaudit={{}}] (meanbox) at ({num(cx_mid)},{num(mean_y)}) "
            f"{{{mean['text']}}};"
        )
    else:
        tex.append(
            "% TODO: \\node[mean, text width=..cm, vaudit={}] (meanbox) at (..,..) {对象/机制/...};"
        )
    if caption.get("text"):
        tex.append(
            f"\\node[font=\\scriptsize, text=black!55] at "
            f"({num(cx_mid)},{num(cap_y)}) {{{caption['text']}}}; % fv:noaudit"
        )
    else:
        tex.append(
            "% TODO: 标识行 \\node[font=\\scriptsize, text=black!55] at (..,..) {...};"
        )
    tex += ["", r"\end{tikzpicture}", r"\end{document}", ""]
    return "\n".join(tex)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="codegen.py",
        description="语义台账 JSON → 带 vaudit 埋点的 standalone .tex 骨架",
    )
    ap.add_argument("ledger", type=Path, help="LEDGER.json")
    ap.add_argument("-o", "--out", type=Path, help="输出 .tex（缺省写 stdout）")
    ap.add_argument(
        "--assets",
        help="vizstyle/vizaudit 的相对路径前缀（如 ../assets/tikz）；"
        "缺省按 render_tex 的 TEXINPUTS 注入写裸 \\input{vizstyle.tex}",
    )
    args = ap.parse_args(argv)

    try:
        led = load_ledger(args.ledger)
        canvas = None
        cv = led.get("canvas")
        if (
            isinstance(cv, dict)
            and float(cv.get("w", 0)) > 0
            and float(cv.get("h", 0)) > 0
        ):
            canvas = (float(cv["w"]), float(cv["h"]))
        warns = check(led, canvas)
        if canvas is None:
            warns.append("canvas missing/invalid — mean 位置按内容包围盒推")
    except UsageError as e:
        print(f"ERR codegen: {e}", file=sys.stderr)
        return 2
    except (TypeError, ValueError) as e:
        print(f"ERR codegen: bad numeric field: {e}", file=sys.stderr)
        return 2

    tex = gen_tex(led, canvas, args.assets)
    for w in warns:
        print(f"warn codegen: {w}", file=sys.stderr)
    if args.out:
        args.out.write_text(tex)
        print(f"ok: {args.out}")
    else:
        sys.stdout.write(tex)
        print("ok: (stdout)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
