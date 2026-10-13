#!/usr/bin/env python3
r"""check_audit.py — 校验 vizaudit.tex 导出的几何不变量。

读取 FIG.audit 行：
  node NAME   | swx swy nex ney | tags        （盒，逗号分隔 tags）
  region NAME | swx swy nex ney | tags        （检查同 node；\vzbbox [tags]）
  wire NAME   | x1 y1 x2 y2 ... | endpoint=A,B via=C   （连线折线）

同名 box 行合并（`\path \vaudit{N}{tags}` 的重打 tag 就靠它）：
每个键的 tag 取并集；标量键被重新声明成不同值是 ERR；合并行间坐标
差超过 --tol 是 WARN。

box tags：
  class=<id>      同 class 的所有 box 须有相同 w,h
  square          w == h
  twin=<n>        转置对：w==n.h, h==n.w
  eqww/eqhh/eqwh/eqhw=<n>   我的维 == 对方的维
  tiles=<n>       同 parent 的碎片不许重叠且必须覆盖 parent
  inside=<n>      声明的包含——已校验：目标已审计且确实包含
  adjacent=<n>    声明的有意相邻——抑制 CROWD；
                  class:<id> 展开为所有带 class=<id> 的 box
  overlap=<n>     声明的有意部分重叠——豁免 COLLIDE，
                  已校验：声明对不再重叠则 warn；
                  class:<id> 豁免每个 class 成员（自身除外，
                  空 class 像未审计目标一样 warn）
  alignx/aligny=<n>  center-x / center-y 相等

inside=, tiles=, adjacent=, overlap=, alignx=, aligny=, twin= 与
eqww/eqhh/eqwh/eqhw= 维度键都是多值的：`k=a,k=b` 或重复的 `\vaudit`
行会累积，每个值独立校验。重复的关系键是链式断言——
`alignx=a,alignx=b` 让本 box 分别对 a、b 校验，a、b 与本 box 三者
共轴。

已审计 box 的两两检查：部分重叠 = COLLIDE error（同一对已报过
inside= 逃逸 ERR 时抑制）；未声明的包含 = NEST warning；未声明且
间距小于 --gap = CROWD warning。wire 段进入不在其 endpoint=/via=
名单中的 box 且深度超过 --edge = WIRE-CROSS error。

输出行为 `ERR <rule>: <msg>` / `warn <rule>: <msg>`。
存在 error 级条目时退出码 1；warn 永不失败。
选项：--tol PT（默认 1.0）、--edge PT（默认 2.0）、--gap PT（默认
10.0）、--quiet。
"""

import argparse
import itertools
import sys
from pathlib import Path

from auditgeom import Rect, audit_rows, seg_rect_depth

DIMS = {"eqww": ("w", "w"), "eqhh": ("h", "h"), "eqwh": ("w", "h"), "eqhw": ("h", "w")}
# 可重复 tag 键：值累积而非冲突
MULTI = {
    "inside",
    "tiles",
    "adjacent",
    "overlap",
    "alignx",
    "aligny",
    "twin",
    "eqww",
    "eqhh",
    "eqwh",
    "eqhw",
}


class Box(Rect):
    def __init__(self, name, swx, swy, nex, ney, tags):
        super().__init__(swx, swy, nex, ney)
        self.name, self.tags = name, tags

    def dim(self, d):
        return self.w if d == "w" else self.h


class Wire:
    def __init__(self, name, pts, tags):
        self.name, self.pts, self.tags = name, pts, tags

    def refs(self):
        """wire 可合法触碰的已审计 box 名。"""
        out = set()
        for key in ("endpoint", "via"):
            out.update(self.tags.get(key, []))
        return out


def parse(path):
    """原始行 -> (kind, name, [coords], tagstring) 元组。"""
    return [row[1:] for row in audit_rows(path) if row[0] == "row"]


def wire_tagmap(raw):
    """'endpoint=A,B via=C' -> {'endpoint': ['A','B'], 'via': ['C']}"""
    out = {}
    for clause in raw.split():
        k, _, v = clause.partition("=")
        names = [n.strip() for n in v.split(",") if n.strip()]
        out.setdefault(k.strip(), []).extend(names)
    return out


def merge_rows(rows, tol):
    """合并同名 box 行；返回 (nodes, wires, errors, warns)。"""
    nodes, wires, errors, warns = {}, [], [], []
    for kind, name, vals, tags in rows:
        if (
            vals is None
            or (kind == "wire" and len(vals) % 2)
            or (kind != "wire" and len(vals) != 4)
        ):
            warns.append(("row", f"{name or '?'}: malformed audit line skipped"))
            continue
        if kind == "wire":
            if name in {w.name for w in wires}:
                warns.append(("merge", f"wire {name} re-registered; first wins"))
                continue
            pts = list(zip(vals[::2], vals[1::2], strict=True))
            wires.append(Wire(name, pts, wire_tagmap(tags)))
            continue
        if name in nodes:
            b = nodes[name]
            drift = max(
                abs(a - c) for a, c in zip((b.x0, b.y0, b.x1, b.y1), vals, strict=True)
            )
            if drift > tol:
                warns.append(
                    (
                        "merge",
                        f"{name} re-registered {drift:.1f}pt away; "
                        "first registration wins (stale \\tikzlastnode?)",
                    )
                )
            if tags:
                b.tags = f"{b.tags},{tags}" if b.tags else tags
            continue
        nodes[name] = Box(name, *vals, tags)
    return nodes, wires, errors, warns


def tagmap(box):
    """'k=v,flag,k=v2' -> {'k': ['v','v2'], 'flag': [True]}——保留重复。"""
    out = {}
    for t in box.tags.split(","):
        t = t.strip()
        if not t:
            continue
        k, _, v = t.partition("=")
        out.setdefault(k.strip(), []).append(v.strip() or True)
    return out


def ref_targets(ref, nodes, classes, self_name):
    """adjacent=/overlap= 目标 -> 它断言针对的已审计 box 名。

    'class:<id>' 展开为所有带 class=<id> 的 box（自身除外）；其余一律
    是普通的节点名目标——未审计时返回 []。只有 adjacent=/overlap= 走
    这里；inside=/tiles=/align*= 保持按名直指。
    """
    s = str(ref)
    if s.startswith("class:"):
        return [
            m.name for m in classes.get(s[len("class:") :], []) if m.name != self_name
        ]
    return [s] if s in nodes else []


def check_scalar_conflicts(nodes, errors):
    for n, b in nodes.items():
        for k, vals in tagmap(b).items():
            if k in MULTI:
                continue
            distinct = {str(v) for v in vals}
            if len(distinct) > 1:
                errors.append(
                    ("tag", f"{n}: conflicting {k}= values {sorted(distinct)}")
                )


def check_tiles(parent, shards, nodes, tol, edge, errors):
    p = nodes.get(parent)
    if p is None:
        errors.append(("tiles", f"parent {parent} not audited"))
        return
    for i, s in enumerate(shards):
        for s2 in shards[i + 1 :]:
            dx, dy = s.overlap_depth(s2)
            if min(dx, dy) > edge:
                errors.append(("tiles", f"{parent}: {s.name} overlaps {s2.name}"))
    # 出檐 / 并集 bbox 与 parent 不符
    x0 = min(s.x0 for s in shards)
    y0 = min(s.y0 for s in shards)
    x1 = max(s.x1 for s in shards)
    y1 = max(s.y1 for s in shards)
    cover = max(abs(x0 - p.x0), abs(y0 - p.y0), abs(x1 - p.x1), abs(y1 - p.y1))
    if cover > tol:
        errors.append(
            (
                "tiles",
                f"{parent}: union ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f}) "
                f"does not cover parent ({p.x0:.1f},{p.y0:.1f})-({p.x1:.1f},{p.y1:.1f})",
            )
        )
    # 真实面积覆盖：扫基本 x 区间；跨该区间的碎片须在 y 向覆盖
    # parent——能逮到并集 bbox 掩盖的洞
    xs = {p.x0, p.x1}
    for s in shards:
        xs.update(c for c in (s.x0, s.x1) if p.x0 - tol < c < p.x1 + tol)
    xs = sorted(xs)
    holes = 0
    for xa, xb in itertools.pairwise(xs):
        if xb - xa < 1e-6:
            continue
        xm = (xa + xb) / 2
        spans = sorted((s.y0, s.y1) for s in shards if s.x0 - tol <= xm <= s.x1 + tol)
        cur = p.y0
        hole = None
        for a, bnd in spans:
            if a > cur + tol:
                hole = (cur, a)
                break
            cur = max(cur, bnd)
        if hole is None and p.y1 - cur > tol:
            hole = (cur, p.y1)
        if hole is not None:
            errors.append(
                (
                    "tiles",
                    f"{parent}: uncovered hole x~{xm:.1f} "
                    f"y=({hole[0]:.1f},{hole[1]:.1f})",
                )
            )
            holes += 1
            if holes >= 3:
                break  # 每个 parent 的洞告警封顶


def check_wire(wire, nodes, edge, errors, warns):
    exempt = wire.refs()
    for key in ("endpoint", "via"):
        for ref in wire.tags.get(key, []):
            if ref not in nodes:
                warns.append(("wire", f"{wire.name}: {key} {ref} not audited"))
    # 曲线 connector 是作者声明的折线近似——检查看到的是导出的
    # 途经点，不是画出的 Bézier
    for p, q in zip(wire.pts, wire.pts[1:]):
        for name, b in nodes.items():
            if name in exempt:
                continue
            depth = seg_rect_depth(p, q, b)
            if depth > edge:
                errors.append(
                    (
                        "WIRE-CROSS",
                        f"{wire.name} crosses {name} ({depth:.1f}pt deep)",
                    )
                )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audit", type=Path)
    ap.add_argument("--tol", type=float, default=1.0, help="dimension tolerance in pt")
    ap.add_argument(
        "--edge",
        type=float,
        default=2.0,
        help="intersection depth under this (pt) counts as edge-touching, not collision",
    )
    ap.add_argument(
        "--gap",
        type=float,
        default=10.0,
        help="undeclared box pairs closer than this (pt) trigger CROWD",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    nodes, wires, errors, warns = merge_rows(parse(args.audit), args.tol)
    names = sorted(nodes)
    classes = {}
    for n in names:
        for cls in tagmap(nodes[n]).get("class", []):
            classes.setdefault(str(cls), []).append(nodes[n])
    # 已吃过 inside 逃逸 ERR 的 (child, parent) 对——两两检查不能再
    # 叠一条 COLLIDE
    escaped = set()

    for n in names:
        b = nodes[n]
        tags = tagmap(b)
        if "square" in tags and abs(b.w - b.h) > args.tol:
            errors.append(("square", f"{n} is {b.w:.2f}x{b.h:.2f}"))
        for k, (d1, d2) in DIMS.items():
            for ref in tags.get(k, []):
                other = nodes.get(str(ref))
                if other is None:
                    errors.append(("dims", f"{k}: {n} refers to unaudited {ref}"))
                elif abs(b.dim(d1) - other.dim(d2)) > args.tol:
                    errors.append(
                        (
                            "dims",
                            f"{k}: {n}.{d1}={b.dim(d1):.2f} "
                            f"!= {ref}.{d2}={other.dim(d2):.2f}",
                        )
                    )
        for ref in tags.get("twin", []):
            o = nodes.get(str(ref))
            if o is None:
                errors.append(("twin", f"{n} refers to unaudited {ref}"))
            elif abs(b.w - o.h) > args.tol or abs(b.h - o.w) > args.tol:
                errors.append(
                    (
                        "twin",
                        f"{n} ({b.w:.2f}x{b.h:.2f}) vs {ref} ({o.w:.2f}x{o.h:.2f})",
                    )
                )
        for ax, getter in (
            ("alignx", lambda s: (s.x0 + s.x1) / 2),
            ("aligny", lambda s: (s.y0 + s.y1) / 2),
        ):
            for ref in tags.get(ax, []):
                o = nodes.get(str(ref))
                if o is None:
                    errors.append((ax, f"{n} refers to unaudited {ref}"))
                elif abs(getter(b) - getter(o)) > args.tol:
                    errors.append(
                        (
                            ax,
                            f"{n} center={getter(b):.2f} != {ref} {getter(o):.2f}",
                        )
                    )
        # inside= 现在是已校验断言，不只是 NEST 抑制器
        for ref in tags.get("inside", []):
            o = nodes.get(str(ref))
            if o is None:
                errors.append(("inside", f"{n} refers to unaudited {ref}"))
            elif not o.contains(b, args.tol):
                over = max(o.x0 - b.x0, o.y0 - b.y0, b.x1 - o.x1, b.y1 - o.y1)
                errors.append(
                    (
                        "inside",
                        f"{n} escapes declared parent {ref} by {over:.1f}pt",
                    )
                )
                escaped.add((n, str(ref)))
        for ref in tags.get("adjacent", []):
            if str(ref).startswith("class:"):
                if not ref_targets(ref, nodes, classes, n):
                    warns.append(("adjacent", f"{n} refers to empty {ref}"))
            elif str(ref) not in nodes:
                warns.append(("adjacent", f"{n} refers to unaudited {ref}"))
        # overlap= 与 inside= 同为被验证声明：声明了相交就必须真相交，
        # 漂移成只贴/只离会报 declared-but-not-true；class:<id> 展开为整组，
        # 只要与任一成员真相交即成立
        for ref in tags.get("overlap", []):
            if str(ref).startswith("class:"):
                members = [nodes[t] for t in ref_targets(ref, nodes, classes, n)]
                if not members:
                    warns.append(("overlap", f"{n} refers to empty {ref}"))
                elif all(min(b.overlap_depth(m)) <= args.edge for m in members):
                    warns.append(
                        (
                            "overlap",
                            f"{n} declares overlap={ref} but intersects "
                            "no class member",
                        )
                    )
                continue
            o = nodes.get(str(ref))
            if o is None:
                warns.append(("overlap", f"{n} refers to unaudited {ref}"))
            else:
                dx, dy = b.overlap_depth(o)
                if min(dx, dy) <= args.edge:
                    warns.append(
                        (
                            "overlap",
                            f"{n} declares overlap={ref} but boxes only "
                            f"intersect {min(dx, dy):.1f}pt",
                        )
                    )

    check_scalar_conflicts(nodes, errors)

    for cls, members in classes.items():
        ref = members[0]
        for m in members[1:]:
            if abs(m.w - ref.w) > args.tol or abs(m.h - ref.h) > args.tol:
                errors.append(
                    (
                        "class",
                        f"{cls}: {m.name} ({m.w:.2f}x{m.h:.2f}) "
                        f"!= {ref.name} ({ref.w:.2f}x{ref.h:.2f})",
                    )
                )

    tile_groups = {}
    for n in names:
        for parent in tagmap(nodes[n]).get("tiles", []):
            tile_groups.setdefault(str(parent), []).append(nodes[n])
    for parent, shards in tile_groups.items():
        check_tiles(parent, shards, nodes, args.tol, args.edge, errors)

    for w in wires:
        check_wire(w, nodes, args.edge, errors, warns)

    # 声明的关系：包含（inside/tiles，有向）与相邻（adjacent，
    # 对称）；同一 parent 的碎片互相关联
    declared_in = set()
    related = set()
    overlap_decl = set()
    for n in names:
        t = tagmap(nodes[n])
        for key in ("inside", "tiles"):
            for ref in t.get(key, []):
                declared_in.add((n, str(ref)))
                related.add((n, str(ref)))
                related.add((str(ref), n))
        for ref in t.get("adjacent", []):
            for tgt in ref_targets(ref, nodes, classes, n):
                related.add((n, tgt))
                related.add((tgt, n))
        for ref in t.get("overlap", []):
            for tgt in ref_targets(ref, nodes, classes, n):
                overlap_decl.add((n, tgt))
                overlap_decl.add((tgt, n))
                related.add((n, tgt))
                related.add((tgt, n))
    for parent, shards in tile_groups.items():
        for i, s in enumerate(shards):
            for s2 in shards[i + 1 :]:
                related.add((s.name, s2.name))
                related.add((s2.name, s.name))

    for i, a in enumerate(names):
        for bname in names[i + 1 :]:
            ba, bb = nodes[a], nodes[bname]
            dx, dy = ba.overlap_depth(bb)
            if min(dx, dy) > args.edge:
                if ba.contains(bb, args.tol) or bb.contains(ba, args.tol):
                    child, parent = (bb, ba) if ba.contains(bb, args.tol) else (ba, bb)
                    if (child.name, parent.name) not in declared_in:
                        warns.append(
                            (
                                "NEST",
                                f"{child.name} inside {parent.name} (undeclared)",
                            )
                        )
                elif (a, bname) not in overlap_decl:
                    if (a, bname) not in escaped and (bname, a) not in escaped:
                        errors.append(
                            ("COLLIDE", f"{a} vs {bname}: {dx:.1f}x{dy:.1f}pt")
                        )
                continue
            if (a, bname) in related:
                continue
            gap = ba.gap(bb)
            if gap < args.gap:
                warns.append(
                    (
                        "CROWD",
                        f"{a} ~ {bname}: {gap:.1f}pt gap undeclared "
                        "(inside=/tiles=/adjacent= or widen)",
                    )
                )

    if not args.quiet:
        print(
            f"{args.audit.name}: {len(nodes)} audited boxes, {len(wires)} wires, "
            f"tol={args.tol}pt edge={args.edge}pt gap={args.gap}pt"
        )
    for rule, msg in warns:
        print(f"  warn {rule}: {msg}")
    for rule, msg in errors:
        print(f"  ERR {rule}: {msg}")
    if not errors and not warns:
        print("  all invariants hold")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
