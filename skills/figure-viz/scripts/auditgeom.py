"""auditgeom.py — .audit 行格式与盒/线几何原语（check_audit / check_readback_tex 共用）。

vizaudit.tex 落盘的 .audit 行形如 ``kind name | coords | tags``，并在每个
tikzpicture 结尾追加 ``origin <picid> <6 nums>`` 行（无竖线），把此前的行
归到该 picture 的坐标系。``audit_rows`` 是两侧唯一的解析入口。

几何原语作用在任何带 ``x0/x1/y0/y1`` 属性的矩形上（Rect、check_audit.Box、
check_readback_tex.Word 皆可），单位随调用方坐标系——check_audit 用 pgf pt，
readback 已映射成 poppler bp。
"""

import math
import re

ORIGIN_RE = re.compile(r"^origin\s+(\S+)\s+(.*)$")


class Rect:
    """轴对齐矩形：x0<x1、y0<y1 由构造时排序保证。"""

    __slots__ = ("x0", "x1", "y0", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.x1 = sorted((x0, x1))
        self.y0, self.y1 = sorted((y0, y1))

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0

    def overlap_depth(self, o):
        """相交深度 (dx, dy)；某轴 <=0 即两盒在该轴不相交。"""
        return (
            min(self.x1, o.x1) - max(self.x0, o.x0),
            min(self.y1, o.y1) - max(self.y0, o.y0),
        )

    def contains(self, o, eps):
        """o 完全落在 self 内（每侧距边 eps 之内）。"""
        return (
            self.x0 <= o.x0 + eps
            and self.y0 <= o.y0 + eps
            and self.x1 >= o.x1 - eps
            and self.y1 >= o.y1 - eps
        )

    def gap(self, o):
        """两矩形的欧氏距离；相贴/重叠时为 0。"""
        dx, dy = self.overlap_depth(o)
        return math.hypot(max(0.0, -dx), max(0.0, -dy))

    def pt_gap(self, px, py):
        """点到矩形的欧氏距离；点在矩形内时为 0。"""
        return math.hypot(
            max(0.0, self.x0 - px, px - self.x1),
            max(0.0, self.y0 - py, py - self.y1),
        )


def audit_rows(path):
    """逐行解析 .audit，yield 两种事件：

    - ``("origin", pic, vals)`` —— origin 行；vals 是数值列表（pt 后缀剥掉）
    - ``("row", kind, name, vals, tags)`` —— kind/name/tags 为已 strip 字符串；
      vals 是数值列表，解析失败为 None（由调用方决定告警还是跳过）
    """
    for ln in path.read_text().splitlines():
        if "|" not in ln:
            om = ORIGIN_RE.match(ln.strip())
            if om:
                vals = [
                    float(v[:-2]) if v.endswith("pt") else float(v)
                    for v in om.group(2).split()
                ]
                yield ("origin", om.group(1), vals)
            continue
        head, rest = ln.split("|", 1)
        coords, _, tags = rest.partition("|")
        kind, _, name = head.strip().partition(" ")
        try:
            vals = [float(v.replace("pt", "")) for v in coords.split()]
        except ValueError:
            vals = None
        yield ("row", kind.strip(), name.strip(), vals, tags.strip())


def seg_rect_depth(p, q, r):
    """线段 p->q 侵入矩形 r 的最深距离。

    先对矩形做 slab 裁剪，再求弦端点与矩形中位线交点处到边界的距离
    （凹分段线性函数的最大值必落在这些点之一）。沿边行进的线段深度
    保持 ~0——贴边豁免，与 COLLIDE 的贴边豁免一致；落在他人盒内的
    途经点如实上报自身深度。
    """
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for lo, hi, p0, d in (
        (r.x0, r.x1, p[0], dx),
        (r.y0, r.y1, p[1], dy),
    ):
        if abs(d) < 1e-9:
            if p0 < lo or p0 > hi:
                return 0.0
            continue
        ta, tb = sorted(((lo - p0) / d, (hi - p0) / d))
        t0, t1 = max(t0, ta), min(t1, tb)
        if t1 <= t0:
            return 0.0

    def depth_at(t):
        x, y = p[0] + t * dx, p[1] + t * dy
        return min(x - r.x0, r.x1 - x, y - r.y0, r.y1 - y)

    cand = [t0, t1]
    xm, ym = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    for mid, p0, d in ((xm, p[0], dx), (ym, p[1], dy)):
        if abs(d) > 1e-9:
            t = (mid - p0) / d
            if t0 < t < t1:
                cand.append(t)
    return max(0.0, *(depth_at(t) for t in cand))
