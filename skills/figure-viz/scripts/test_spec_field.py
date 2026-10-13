#!/usr/bin/env python3
"""test_spec_field.py — 场族系列（contour/quiver）的隔离测试。

- contour 长表 {x,y,z} 数值网格透视 / matrix 直给（数值单调坐标）：
  fill/lines/fill+lines 三模式、levels int/数组/log、clabel 子配置
  （'all'/步长/显式子集/fmt 模板）、cbar/cmap/vcenter 复用 heat 机制、
  NaN 缺格、场 zorder 垫在数据系列之下、grid 默认关
- contour SpecError 面：clabel 依赖线层、坏 levels/mode/matrix、长表
  类别坐标、重复格、of/by/color 拒绝、长表禁 xlabels、log 域、clabel
  子集越界、clabel.manual 与 levels 互斥/坏形状、matrix 类别标签重复
- quiver：arrows 逐行向量（任意位置、scale/pivot/alpha/label/系列色）与
  stream 网格流线图（density/linewidth/arrowsize、m→cmap+norm+cbar）；
  m 缺省回退系列色；缺字段行跳过、非数值响亮报错
- quiver SpecError 面：缺 u/v、坏 mode、流派字段跨 mode 互斥、m+color、
  cmap/vcenter/cbar 无 m、坏 scale/pivot/density、stream <2x2
- occluded-by-heat 扩展：contourf（fill/fill+lines）按 _KIND_ZORDER=0.5
  覆盖低 zorder 系列，lines 模式不算覆盖
- clabel 压自身等值面不触发 text-overlaps-data——fvstyle 的栅格场豁免
  已覆盖 QuadContourSet（与 QuadMesh/AxesImage 同口径：遮挡语义由
  色条承担）；审计断言直接走 audit_of，无过滤。

运行：uv run --with matplotlib --with numpy python scripts/test_spec_field.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection, PathCollection
from matplotlib.colors import TwoSlopeNorm
from matplotlib.contour import QuadContourSet
from matplotlib.quiver import Quiver

SKILL_DIR = Path(__file__).resolve().parents[1]


def render(spec):
    return fvspec.render(spec, base_dir=SKILL_DIR / "scripts" / "examples")


def audit_of(fig):
    return fvspec.audit_fig(fig)


def expect_error(name, spec, *substrings):
    try:
        render(spec)
    except fvspec.SpecError as e:
        msg = str(e)
        missing = [s for s in substrings if s not in msg]
        check(f"err:{name}", not missing, f"missing {missing} in: {msg}")
        return
    except Exception as e:
        check(f"err:{name}", False, f"wrong exc {type(e).__name__}: {e}")
        return
    check(f"err:{name}", False, "no SpecError raised")


def expect_lint(name, spec, lint, present=True):
    fig = render(spec)
    hits = [w for w in warnings_of(fig) if w.startswith(lint)]
    check(f"lint:{name}", bool(hits) == present, f"warnings={warnings_of(fig)}")
    plt.close(fig)


META = {"ledger": "l", "caption": "c"}


def _zrows(xs, ys, f):
    return [{"x": float(x), "y": float(y), "z": float(f(x, y))} for y in ys for x in xs]


def _vrows(xs, ys):
    """旋转场 u=-y, v=x，m=hypot(x,y)——stream 可积分、箭头有方向变化。"""
    return [
        {
            "x": float(x),
            "y": float(y),
            "u": float(-y),
            "v": float(x),
            "m": float(np.hypot(x, y)),
        }
        for y in ys
        for x in xs
    ]


def contour_kinds():
    xs, ys = np.linspace(0, 3, 16), np.linspace(0, 2, 12)
    rows = _zrows(xs, ys, lambda x, y: x + 2 * y * y)
    base = {
        "version": 1,
        "data": {"d": rows},
        "xaxis": {"label": "x"},
        "yaxis": {"label": "y"},
        "meta": META,
    }

    # --- fill 默认：contourf 单 artist、cbar 自动出、audit 干净 ---
    spec = dict(
        base,
        series=[{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
    )
    fig = render(spec)
    ax = fig.get_axes()[0]
    css = [c for c in ax.collections if isinstance(c, QuadContourSet)]
    check("ct-fill-one", len(css) == 1, f"{len(css)}")
    check("ct-fill-cbar", len(fig.get_axes()) == 2, f"{len(fig.get_axes())}")
    check("ct-fill-array", css[0].get_array() is not None, "no level array")
    probs = audit_of(fig)
    check("ct-fill-clean", not probs and not warnings_of(fig), f"{probs[:2]}")
    # 场默认垫在数据系列层之下（collection 默认 zorder=1，场=0.5）
    check("ct-fill-zorder", css[0].get_zorder() < 1, f"z={css[0].get_zorder()}")
    plt.close(fig)

    # --- 网格透视：x/y 升序数值坐标、z 矩阵取向一致 ---
    cs = css[0] if css else None
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "levels": [2.0, 4.0, 6.0],
                    "mode": "lines",
                    "cbar": False,
                }
            ],
        )
    )
    ax = fig.get_axes()[0]
    cs = next(c for c in ax.collections if isinstance(c, QuadContourSet))
    check(
        "ct-levels-explicit",
        list(cs.levels) == [2.0, 4.0, 6.0],
        f"{list(cs.levels)}",
    )
    check("ct-lines-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    plt.close(fig)

    # --- int levels：mpl MaxNLocator 取层数 ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "levels": 5,
                    "cbar": False,
                }
            ],
        )
    )
    cs = next(c for c in fig.get_axes()[0].collections if isinstance(c, QuadContourSet))
    check(
        "ct-levels-int",
        len(cs.levels) >= 3 and np.all(np.diff(cs.levels) > 0),
        f"{list(cs.levels)}",
    )
    plt.close(fig)

    # --- fill+lines：色面 + vink 细描线（fv-neutral），clabel 挂在描线上 ---
    spec = dict(
        base,
        series=[
            {
                "kind": "contour",
                "from": "d",
                "x": "x",
                "y": "y",
                "z": "z",
                "mode": "fill+lines",
                "levels": 5,
                "clabel": {"levels": 2},
                "cbar": {"label": "f"},
            }
        ],
    )
    fig = render(spec)
    ax = fig.get_axes()[0]
    css = [c for c in ax.collections if isinstance(c, QuadContourSet)]
    check("ct-fl-two", len(css) == 2, f"{len(css)}")
    if len(css) == 2:
        fill, lines = css[0], css[1]
        check(
            "ct-fl-overlay-neutral",
            lines.get_gid() == "fv-neutral",
            f"gid={lines.get_gid()!r}",
        )
        check(
            "ct-fl-overlay-z",
            lines.get_zorder() > fill.get_zorder(),
            f"{lines.get_zorder()} vs {fill.get_zorder()}",
        )
        check(
            "ct-fl-same-levels",
            np.array_equal(lines.levels, fill.levels),
            f"{list(lines.levels)} vs {list(fill.levels)}",
        )
        ec = np.atleast_2d(np.asarray(lines.get_edgecolor(), dtype=float))
        check(
            "ct-fl-overlay-ink",
            len({tuple(c) for c in ec[:, :3]}) == 1,
            f"{ec[:3]}",
        )
    labels = [t for t in ax.texts if t.get_text().strip()]
    check("ct-fl-clabel", len(labels) >= 1, f"{len(labels)}")
    if labels:
        check(
            "ct-fl-clabel-neutral",
            all(t.get_gid() == "fv-neutral" for t in labels),
            f"{[t.get_gid() for t in labels]}",
        )
    probs = audit_of(fig)
    check("ct-fl-clean", not probs and not warnings_of(fig), f"{probs[:2]}")
    plt.close(fig)

    # --- clabel 显式子集 + '{v:...}' 逐层 fmt 模板 ---
    spec = dict(
        base,
        series=[
            {
                "kind": "contour",
                "from": "d",
                "x": "x",
                "y": "y",
                "z": "z",
                "mode": "lines",
                "levels": [2.0, 4.0, 6.0],
                "clabel": {"levels": [4.0], "fmt": "{v:.0f}!"},
                "cbar": False,
            }
        ],
    )
    fig = render(spec)
    texts = {t.get_text() for t in fig.get_axes()[0].texts if t.get_text().strip()}
    check("ct-clabel-subset", texts == {"4!"}, f"{texts}")
    probs = audit_of(fig)
    check("ct-clabel-clean", not probs, f"{probs[:2]}")
    plt.close(fig)

    # --- matrix 直给：数值坐标轴、无 data 也画 ---
    mat = [[float(i + j * j) for j in range(6)] for i in range(5)]
    spec = {
        "version": 1,
        "xaxis": {"label": "x"},
        "yaxis": {"label": "y"},
        "series": [
            {
                "kind": "contour",
                "matrix": mat,
                "xlabels": [0.0, 0.5, 1.0, 2.0, 4.0, 8.0],
                "ylabels": [0.0, 1.0, 2.0, 4.0, 8.0],
                "levels": 4,
                "cbar": False,
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "ct-matrix-lim",
        ax.get_xlim()[0] < 0.0 and ax.get_xlim()[1] > 8.0,
        f"{ax.get_xlim()}",
    )
    check("ct-matrix-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    plt.close(fig)

    # --- matrix 类别标签：非数值 → 按位等距槽位 + 原串刻度 ---
    spec = {
        "version": 1,
        "xaxis": {"label": "k"},
        "yaxis": {"label": "pct"},
        "series": [
            {
                "kind": "contour",
                "matrix": [[1.0, 2.0, 4.0], [2.0, 5.0, 9.0], [4.0, 9.0, 17.0]],
                "xlabels": ["k=1", "k=2", "k=4"],
                "ylabels": ["p10", "p50", "p90"],
                "mode": "lines",
                "levels": 4,
                "cbar": False,
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    xt = ax.get_xticks()
    xl = [t.get_text() for t in ax.get_xticklabels()]
    yl = [t.get_text() for t in ax.get_yticklabels()]
    check(
        "ct-mat-cat-ticks",
        list(xt) == [0, 1, 2] and xl == ["k=1", "k=2", "k=4"],
        f"xticks={xt} labels={xl}",
    )
    check("ct-mat-cat-yticks", yl == ["p10", "p50", "p90"], f"{yl}")
    probs = audit_of(fig)
    check("ct-mat-cat-clean", not probs, f"{probs[:2]}")
    plt.close(fig)
    # 类别轴的刻度归 kind 层：用户 xaxis.ticks → axis-ignored
    spec2 = dict(spec)
    spec2["xaxis"] = {"label": "k", "ticks": [0, 1]}
    spec2["series"] = [dict(spec["series"][0])]
    expect_lint("ct-mat-cat-xaxis", spec2, "axis-ignored")

    # --- clabel manual：手工点位对全部画出层生效 ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "mode": "lines",
                    "levels": [2.0, 4.0, 6.0],
                    "clabel": {"manual": [[1.0, 0.5], [2.0, 1.0]]},
                    "cbar": False,
                }
            ],
        )
    )
    ax = fig.get_axes()[0]
    texts = [t for t in ax.texts if t.get_text().strip()]
    check("ct-clabel-manual", len(texts) >= 2, f"{len(texts)}")
    # 手工点位落在给定点附近（clabel 吸到最近的段上）
    if texts:
        pts = np.asarray([t.get_position() for t in texts])
        near = any(
            np.isclose(pts[:, 0], p[0], atol=0.8).any()
            and np.isclose(pts[:, 1], p[1], atol=0.8).any()
            for p in ([1.0, 0.5], [2.0, 1.0])
        )
        check("ct-clabel-manual-pos", near, f"pos={pts.tolist()}")
    plt.close(fig)

    # --- log levels：[zmin,zmax] 等比 ---
    lrows = _zrows(range(4), range(4), lambda x, y: 10 ** (x * 0.5 + y * 0.25))
    spec = {
        "version": 1,
        "data": {"d": lrows},
        "series": [
            {
                "kind": "contour",
                "from": "d",
                "x": "x",
                "y": "y",
                "z": "z",
                "levels": {"log": 4},
                "cbar": False,
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    cs = next(c for c in fig.get_axes()[0].collections if isinstance(c, QuadContourSet))
    lv = np.asarray(cs.levels, dtype=float)
    ratio = lv[1:] / lv[:-1]
    check(
        "ct-levels-log",
        len(lv) == 4 and np.allclose(ratio, ratio[0]),
        f"{lv}",
    )
    plt.close(fig)

    # --- div + vcenter：TwoSlopeNorm 居中 ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "cmap": "div",
                    "vcenter": 4.0,
                    "cbar": False,
                }
            ],
        )
    )
    cs = next(c for c in fig.get_axes()[0].collections if isinstance(c, QuadContourSet))
    check(
        "ct-vcenter",
        isinstance(cs.norm, TwoSlopeNorm) and cs.norm.vcenter == 4.0,
        f"{type(cs.norm).__name__} {getattr(cs.norm, 'vcenter', None)}",
    )
    plt.close(fig)

    # --- NaN 缺格：长表缺 (x,y) 组合 → masked cell 落 mist 坏色，照常渲染 ---
    hole = [r for r in rows if not (r["x"] == 1.0 and r["y"] == 0.0)]
    fig = render(
        dict(
            base,
            data={"d": hole},
            series=[
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "cbar": False,
                }
            ],
        )
    )
    check("ct-hole-render", True)  # 渲染成功即过——坏格不炸
    plt.close(fig)

    # --- grid 默认关：场面板不画网格线（heat 同口径） ---
    fig = render(
        dict(
            base,
            series=[{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
        )
    )
    ax = fig.get_axes()[0]
    on = [g for g in ax.get_xgridlines() + ax.get_ygridlines() if g.get_visible()]
    check("ct-grid-off", not on, f"{len(on)}")
    plt.close(fig)

    # --- 与散点叠加：场在下、点在上 ---
    srows = [{"x": 0.5, "y": 0.5}, {"x": 2.5, "y": 1.5}]
    fig = render(
        dict(
            base,
            data=dict(base["data"], s=srows),
            series=[
                {"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"},
                {"kind": "scatter", "from": "s", "x": "x", "y": "y"},
            ],
        )
    )
    ax = fig.get_axes()[0]
    cs = next(c for c in ax.collections if isinstance(c, QuadContourSet))
    sc = next(c for c in ax.collections if isinstance(c, PathCollection))
    check(
        "ct-under-scatter",
        cs.get_zorder() < sc.get_zorder(),
        f"{cs.get_zorder()} vs {sc.get_zorder()}",
    )
    check(
        "ct-scatter-not-occluded",
        not any(w.startswith("occluded-by-heat") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)


def contour_errors():
    rows = _zrows(range(5), range(5), lambda x, y: x + y)
    base = {"version": 1, "data": {"d": rows}}
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        s.update(kw)
        return s

    def ser(**kw):
        return mod(
            series=[
                dict(
                    {"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}, **kw
                )
            ]
        )

    expect_error("ct-clabel-on-fill", ser(clabel=True), "clabel labels contour lines")
    expect_error("ct-levels-1", ser(levels=1), "levels must be")
    expect_error("ct-levels-order", ser(levels=[3, 1]), "levels must be")
    expect_error("ct-levels-bad", ser(levels="many"), "levels must be")
    expect_error("ct-mode-bad", ser(mode="lines+fill"), "mode must be")
    expect_error(
        "ct-missing-z",
        mod(series=[{"kind": "contour", "from": "d", "x": "x", "y": "y"}]),
        "missing required 'z'",
    )
    expect_error("ct-of", ser(of="s0"), "unknown series", "'of'")
    expect_error("ct-color", ser(color="vteal"), "'color' does not apply")
    expect_error("ct-by", ser(by="x"), "'by' does not apply")
    expect_error(
        "ct-xl-long", ser(xlabels=[1, 2, 3, 4, 5]), "'xlabels' belongs to the 'matrix'"
    )
    expect_error("ct-bad-key", ser(zz=1), "unknown keys")
    expect_error(
        "ct-cmap-bad",
        ser(cmap="nope"),
        "unknown cmap",
    )
    expect_error(
        "ct-clabel-subset",
        ser(mode="lines", levels=[2.0, 4.0], clabel={"levels": [3.0]}),
        "clabel.levels [3.0] not among",
    )
    expect_error(
        "ct-clabel-badkey",
        ser(mode="lines", clabel={"zz": 1}),
        "unknown keys",
    )
    expect_error(
        "ct-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            series=[{"kind": "contour", "x": "x", "y": "y", "z": "z"}],
        ),
        "not allowed in",
    )
    # 类别坐标 → heat 语义提示
    expect_error(
        "ct-cat-x",
        mod(
            data={
                "d": [
                    {"x": "a", "y": 0, "z": 1},
                    {"x": "b", "y": 0, "z": 2},
                    {"x": "a", "y": 1, "z": 1},
                    {"x": "b", "y": 1, "z": 2},
                ]
            },
            series=[{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
        ),
        "grid coordinates must be numeric",
    )
    dup = [
        {"x": 0, "y": 0, "z": 1},
        {"x": 0, "y": 0, "z": 2},
        {"x": 1, "y": 0, "z": 1},
        {"x": 0, "y": 1, "z": 1},
    ]
    expect_error(
        "ct-dup",
        mod(
            data={"d": dup},
            series=[{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
        ),
        "duplicate cell",
    )
    # matrix 形态错误
    expect_error(
        "ct-mat-ragged",
        {"version": 1, "series": [{"kind": "contour", "matrix": [[1, 2], [3]]}]},
        "ragged",
    )
    expect_error(
        "ct-mat-cell",
        {"version": 1, "series": [{"kind": "contour", "matrix": [["a", 2], [3, 4]]}]},
        "non-numeric",
    )
    # 非数值 xlabels 现在是合法的类别标签；重复类别仍响亮拒绝
    expect_error(
        "ct-mat-xl-dupcat",
        {
            "version": 1,
            "series": [
                {
                    "kind": "contour",
                    "matrix": [[1, 2], [3, 4]],
                    "xlabels": ["a", "a"],
                }
            ],
        },
        "distinct",
    )
    expect_error(
        "ct-mat-xl-nonmono",
        {
            "version": 1,
            "series": [
                {"kind": "contour", "matrix": [[1, 2], [3, 4]], "xlabels": [0, 0]}
            ],
        },
        "monotonic",
    )
    expect_error(
        "ct-mat-xl-len",
        {
            "version": 1,
            "series": [
                {
                    "kind": "contour",
                    "matrix": [[1, 2], [3, 4]],
                    "xlabels": ["a", "b", "c"],
                }
            ],
        },
        "list of 2",
    )
    # clabel.manual：与 levels 互斥 + 形状校验
    expect_error(
        "ct-clabel-manual+levels",
        ser(mode="lines", clabel={"manual": [[0, 0]], "levels": 2}),
        "mutually exclusive",
    )
    expect_error(
        "ct-clabel-manual-bad",
        ser(mode="lines", clabel={"manual": [[0, 0, 1]]}),
        "manual must be",
    )
    expect_error(
        "ct-clabel-manual-empty",
        ser(mode="lines", clabel={"manual": []}),
        "manual must be",
    )
    expect_error(
        "ct-mat-x",
        {
            "version": 1,
            "series": [{"kind": "contour", "matrix": [[1, 2], [3, 4]], "x": "x"}],
        },
        "'x' belongs to the long-table",
    )
    # log 域：zmin<=0
    zrows = _zrows(range(4), range(4), lambda x, y: -x - y - 1)
    expect_error(
        "ct-log-neg",
        mod(
            data={"d": zrows},
            series=[
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "levels": "log",
                }
            ],
        ),
        "'log' levels need zmin > 0",
    )
    # 长表 1×N 网格
    thin = [{"x": float(x), "y": 0.0, "z": float(x)} for x in range(4)]
    expect_error(
        "ct-thin-grid",
        mod(
            data={"d": thin},
            series=[{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
        ),
        ">=2 distinct coordinates",
    )


def contour_lints():
    rows = _zrows(np.linspace(0, 3, 10), np.linspace(0, 2, 8), lambda x, y: x + y)
    cf = {"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z", "cbar": False}
    span = {"kind": "span", "dir": "v", "at": [0.5, 1.5]}
    expect_lint(
        "ct-covers-low",
        {
            "version": 1,
            "data": {"d": rows},
            "series": [dict(span, zorder=0.2), cf],
        },
        "occluded-by-heat",
    )
    expect_lint(
        "ct-fillplus-covers",
        {
            "version": 1,
            "data": {"d": rows},
            "series": [dict(span, zorder=0.2), dict(cf, mode="fill+lines")],
        },
        "occluded-by-heat",
    )
    expect_lint(
        "ct-lines-not-cover",
        {
            "version": 1,
            "data": {"d": rows},
            "series": [dict(span, zorder=0.2), dict(cf, mode="lines")],
        },
        "occluded-by-heat",
        present=False,
    )
    expect_lint(
        "ct-normal-z-not-cover",
        {"version": 1, "data": {"d": rows}, "series": [cf, span]},
        "occluded-by-heat",
        present=False,
    )
    # 空数据 → empty-series lint 而非 SpecError
    expect_lint(
        "ct-empty",
        {
            "version": 1,
            "data": {"d": []},
            "series": [{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
        },
        "empty-series",
    )


def quiver_kinds():
    xs, ys = np.linspace(-1, 1, 6), np.linspace(-1, 1, 6)
    rows = _vrows(xs, ys)
    base = {
        "version": 1,
        "data": {"d": rows},
        "xaxis": {"label": "x"},
        "yaxis": {"label": "y"},
        "meta": META,
    }

    # --- arrows 默认：Quiver artist、系列色、pivot/scale 透传 ---
    spec = dict(
        base,
        series=[
            {
                "kind": "quiver",
                "from": "d",
                "x": "x",
                "y": "y",
                "u": "u",
                "v": "v",
                "pivot": "mid",
                "scale": 8,
            }
        ],
    )
    fig = render(spec)
    ax = fig.get_axes()[0]
    qs = [c for c in ax.collections if isinstance(c, Quiver)]
    check("qv-arrows-one", len(qs) == 1, f"{len(qs)}")
    if qs:
        check("qv-arrows-pivot", qs[0].pivot == "middle", f"{qs[0].pivot}")
        check("qv-arrows-scale", qs[0].scale == 8, f"{qs[0].scale}")
        check("qv-arrows-zorder", qs[0].get_zorder() < 1, f"{qs[0].get_zorder()}")
    check("qv-arrows-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    plt.close(fig)

    # --- label → panel legend 收录 ---
    spec = dict(
        base,
        series=[
            {
                "kind": "quiver",
                "from": "d",
                "x": "x",
                "y": "y",
                "u": "u",
                "v": "v",
                "label": "vfield",
            }
        ],
        legend=True,
    )
    fig = render(spec)
    leg = fig.get_axes()[0].get_legend()
    check(
        "qv-legend",
        leg is not None and "vfield" in [t.get_text() for t in leg.get_texts()],
        f"{leg}",
    )
    plt.close(fig)

    # --- m → cmap 映射：array 绑定、cbar 出 ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "m": "m",
                    "cbar": {"label": "|v|"},
                }
            ],
        )
    )
    ax = fig.get_axes()[0]
    q = next(c for c in ax.collections if isinstance(c, Quiver))
    check("qv-m-array", q.get_array() is not None, "no magnitude array")
    check("qv-m-cbar", len(fig.get_axes()) == 2, f"{len(fig.get_axes())}")
    check("qv-m-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    plt.close(fig)

    # --- m + vcenter：TwoSlopeNorm ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "m": "m",
                    "vcenter": 1.0,
                    "cmap": "div",
                    "cbar": False,
                }
            ],
        )
    )
    q = next(c for c in fig.get_axes()[0].collections if isinstance(c, Quiver))
    check(
        "qv-m-vcenter",
        isinstance(q.norm, TwoSlopeNorm) and q.norm.vcenter == 1.0,
        f"{type(q.norm).__name__}",
    )
    plt.close(fig)

    # --- 缺字段行跳过、非数值响亮报错（报错面在 quiver_errors） ---
    miss = [*rows[:5], {"x": 0.0, "y": 0.0, "u": 1.0}, *rows[5:]]
    fig = render(
        dict(
            base,
            data={"d": miss},
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                }
            ],
        )
    )
    check(
        "qv-missing-lint",
        any(w.startswith("missing-rows") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)

    # --- stream：StreamplotSet lines+arrows、density 透传 ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                    "density": 1.4,
                    "linewidth": 0.8,
                    "arrowsize": 1.2,
                }
            ],
        )
    )
    ax = fig.get_axes()[0]
    lcs = [c for c in ax.collections if isinstance(c, LineCollection)]
    check("qv-stream-lines", len(lcs) == 1, f"{len(lcs)}")
    check("qv-stream-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    # grid 默认关（同 contour/heat 口径）
    on = [g for g in ax.get_xgridlines() + ax.get_ygridlines() if g.get_visible()]
    check("qv-stream-grid-off", not on, f"{len(on)}")
    plt.close(fig)

    # --- stream + m：LineCollection 绑 array + cbar ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                    "m": "m",
                }
            ],
        )
    )
    ax = fig.get_axes()[0]
    lc = next(c for c in ax.collections if isinstance(c, LineCollection))
    check("qv-stream-m-array", lc.get_array() is not None, "no array")
    check("qv-stream-m-cbar", len(fig.get_axes()) == 2, f"{len(fig.get_axes())}")
    check("qv-stream-m-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    plt.close(fig)

    # --- stream 无 m：系列色生效 ---
    fig = render(
        dict(
            base,
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                    "color": "vteal",
                }
            ],
        )
    )
    check("qv-stream-color-clean", not audit_of(fig), f"{audit_of(fig)[:2]}")
    plt.close(fig)


def quiver_errors():
    rows = _vrows(range(4), range(4))
    base = {"version": 1, "data": {"d": rows}}
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        s.update(kw)
        return s

    def ser(**kw):
        return mod(
            series=[
                dict(
                    {
                        "kind": "quiver",
                        "from": "d",
                        "x": "x",
                        "y": "y",
                        "u": "u",
                        "v": "v",
                    },
                    **kw,
                )
            ]
        )

    expect_error(
        "qv-missing-v",
        mod(series=[{"kind": "quiver", "from": "d", "x": "x", "y": "y", "u": "u"}]),
        "missing required 'v'",
    )
    expect_error("qv-mode", ser(mode="flow"), "mode must be")
    expect_error(
        "qv-scale-on-stream",
        ser(mode="stream", scale=5),
        "'scale' applies to mode:'arrows'",
    )
    expect_error(
        "qv-pivot-on-stream",
        ser(mode="stream", pivot="mid"),
        "'pivot' applies to mode:'arrows'",
    )
    expect_error(
        "qv-density-on-arrows", ser(density=2), "'density' applies to mode:'stream'"
    )
    expect_error(
        "qv-lw-on-arrows", ser(linewidth=1.5), "'linewidth' applies to mode:'stream'"
    )
    expect_error(
        "qv-arrowsize-on-arrows",
        ser(arrowsize=2),
        "'arrowsize' applies to mode:'stream'",
    )
    expect_error("qv-m-color", ser(m="m", color="vteal"), "'color' does not apply")
    expect_error("qv-cmap-no-m", ser(cmap="div"), "'cmap' needs 'm'")
    expect_error("qv-cbar-no-m", ser(cbar=True), "'cbar' needs 'm'")
    expect_error("qv-vcenter-no-m", ser(vcenter=0.5), "'vcenter' needs 'm'")
    expect_error("qv-pivot-bad", ser(pivot="center"), "pivot must be")
    expect_error("qv-scale-neg", ser(scale=-1), "scale must be a positive")
    expect_error(
        "qv-density-bad", ser(mode="stream", density=[1, 2, 3]), "density must be"
    )
    expect_error("qv-density-zero", ser(mode="stream", density=0), "density must be")
    expect_error("qv-lw-neg", ser(mode="stream", linewidth=-1), "linewidth must be")
    expect_error(
        "qv-arrowsize-neg", ser(mode="stream", arrowsize=0), "arrowsize must be"
    )
    expect_error("qv-m-noncol", ser(m="zzz"), "not a data column")
    expect_error("qv-m-nonstr", ser(m=5), "'m' must name a data column")
    expect_error("qv-bad-key", ser(zz=1), "unknown keys")
    expect_error(
        "qv-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            series=[{"kind": "quiver", "x": "x", "y": "y", "u": "u", "v": "v"}],
        ),
        "not allowed in",
    )
    # stream <2x2 网格
    thin = [{"x": 0.0, "y": 0.0, "u": 1, "v": 1}, {"x": 1.0, "y": 0.0, "u": 1, "v": 1}]
    expect_error(
        "qv-stream-thin",
        mod(
            data={"d": thin},
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                }
            ],
        ),
        ">=2x2",
    )
    # 非数值分量
    expect_error(
        "qv-nonnum",
        mod(
            data={"d": [{"x": 0, "y": 0, "u": "a", "v": 1}]},
            series=[
                {"kind": "quiver", "from": "d", "x": "x", "y": "y", "u": "u", "v": "v"}
            ],
        ),
        "x/y/u/v need numbers",
    )
    expect_error(
        "qv-m-nonnum",
        mod(
            data={"d": [{"x": 0, "y": 0, "u": 1, "v": 1, "m": "x"}]},
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "m": "m",
                }
            ],
        ),
        "'m' value",
    )
    # stream 类别坐标
    expect_error(
        "qv-stream-cat",
        mod(
            data={
                "d": [
                    {"x": "a", "y": 0, "u": 1, "v": 1},
                    {"x": "b", "y": 0, "u": 1, "v": 1},
                    {"x": "a", "y": 1, "u": 1, "v": 1},
                    {"x": "b", "y": 1, "u": 1, "v": 1},
                ]
            },
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                }
            ],
        ),
        "grid coordinates must be numeric",
    )
    # stream 重复格
    dup = [
        {"x": 0, "y": 0, "u": 1, "v": 1},
        {"x": 0, "y": 0, "u": 2, "v": 1},
        {"x": 1, "y": 0, "u": 1, "v": 1},
        {"x": 0, "y": 1, "u": 1, "v": 1},
    ]
    expect_error(
        "qv-stream-dup",
        mod(
            data={"d": dup},
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                }
            ],
        ),
        "duplicate cell",
    )
    # stream 非等距网格（CSV %.6g round-trip 截断的实锤场景）→ SpecError
    # 点名罪魁列；等距的 contour 不受影响（contour 容忍非等距网格）
    nu = [
        {"x": x, "y": y, "u": 1.0, "v": 1.0}
        for y in (0.0, 1.0, 2.0)
        for x in (0.0, 0.333333, 2.0)
    ]
    expect_error(
        "qv-stream-nonuniform",
        mod(
            data={"d": nu},
            series=[
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                }
            ],
        ),
        "evenly spaced",
        "column 'x'",
    )
    fig = render(
        mod(
            data={"d": [{"x": r["x"], "y": r["y"], "z": 1.0} for r in nu]},
            series=[{"kind": "contour", "from": "d", "x": "x", "y": "y", "z": "z"}],
        )
    )
    check("qv-stream-nonuniform-contour-ok", fig is not None)
    plt.close(fig)


def quiver_lints():
    # 空数据 → empty-series lint 而非 SpecError
    expect_lint(
        "qv-empty",
        {
            "version": 1,
            "data": {"d": []},
            "series": [
                {"kind": "quiver", "from": "d", "x": "x", "y": "y", "u": "u", "v": "v"}
            ],
        },
        "empty-series",
    )
    expect_lint(
        "qv-empty-stream",
        {
            "version": 1,
            "data": {"d": []},
            "series": [
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                }
            ],
        },
        "empty-series",
    )
    # 场默认 0.5：stream 是网格稀疏线条不算覆盖面，不报 occluded-by-heat
    rows = _vrows(range(4), range(4))
    expect_lint(
        "qv-stream-not-cover",
        {
            "version": 1,
            "data": {"d": rows},
            "series": [
                {"kind": "span", "dir": "v", "at": [0.5, 1.5], "zorder": 0.2},
                {
                    "kind": "quiver",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "u": "u",
                    "v": "v",
                    "mode": "stream",
                },
            ],
        },
        "occluded-by-heat",
        present=False,
    )


def field_legend_swatch():
    """contour/quiver-m 的图例 swatch 取 cmap 中上段色而非首段浅色。"""
    rows = _zrows(np.linspace(0, 3, 10), np.linspace(0, 2, 8), lambda x, y: x + y)
    fig = render(
        {
            "version": 1,
            "data": {"d": rows},
            "xaxis": {"label": "x"},
            "yaxis": {"label": "y"},
            "series": [
                {
                    "kind": "contour",
                    "from": "d",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "id": "cf",
                }
            ],
            "legend": {"entries": [{"series": "cf", "label": "f"}]},
            "meta": META,
        }
    )
    leg = fig.legends[0] if fig.legends else fig.get_axes()[0].get_legend()
    ok = leg is not None and [t.get_text() for t in leg.get_texts()] == ["f"]
    check("swatch-contour", ok, f"{leg}")
    if ok:
        fc = leg.legend_handles[0].get_facecolor()
        check(
            "swatch-contour-cmap",
            fc[:3] != (1.0, 1.0, 1.0) and fc[3] == 1.0,
            f"{fc}",
        )
    plt.close(fig)


def main() -> int:
    contour_kinds()
    contour_errors()
    contour_lints()
    quiver_kinds()
    quiver_errors()
    quiver_lints()
    field_legend_swatch()
    print(f"--- spec_field: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
