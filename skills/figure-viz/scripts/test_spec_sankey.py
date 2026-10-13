#!/usr/bin/env python3
"""test_spec_sankey.py — sankey 守恒流向图系列测试。

- 基础渲染：推导 nodes/stage 的三列流图——audit 干净、fv-neutral 全标记、
  NullLocator 刻度、frame 'minimal'、grid 'none' 默认
- 几何：列位、共中线居中、gap、列内堆叠序、缎带 CURVE4 端点、段偏移记账
- nodes 表：dataset 名 / 字面行、order/label/color 覆盖、orphan/未知端点/
  重复 id/坏行 SpecError、stage 混合与回退流、派生模式环检测
- 守恒：入=出强制（兼有出入流的节点）、纯源/纯汇豁免
- 流校验：非数值/负 z、自环、重复 (src,dst)、缺值行丢弃计 missing-rows
- 颜色：默认 dst 节点色（d3 target）、{'field'}/{'registry','field'} 按行、
  token/'registry:key'/'palette:N' 统一色、裸表/inline map/'parent' SpecError、
  节点 color + series color -> axis-ignored
- 标签与列头：默认模板/自定义/vfmt/fontsize/False、首列右置/末列左置/
  中列白带衬底、heads 列表位对齐与 dict 键控
- 面板约束：独占 panel（混 kind/多 sankey/y2 SpecError）、中性 overlay 放行、
  radar SpecError；axis ticks lint / lim / label 照用、frame/grid 钉回
- 样式：alpha/props(props-win)/zorder、gap:0 连续堆叠、字面数组对齐校验
- dir:'v' 竖向：列变行（stage0 在顶）、行内自左向右堆叠、段区间在 x、
  缎带行进轴在 y、首行标签上置/末行下置/中行白带、行头左缘右对齐
- flows 字面行：数据自由形态（无 from/x/y/z），节点按端点推导、守恒
  与几何同口径；长表键响亮拒；matrix facet 不注入 where

运行：uv run --with matplotlib --with numpy python scripts/test_spec_sankey.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.ticker import NullLocator

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


def _meta():
    return {"ledger": "l", "caption": "c"}


def _bands(ax):
    return [p for p in ax.patches if isinstance(p, PathPatch)]


def _rects(ax):
    return [p for p in ax.patches if isinstance(p, Rectangle)]


# 三列守恒流：a(100) -> b(80)+c(20)；b -> d(60)+e(20)。列布局手算见
# geometry 测试注释；节点色 = 调色板 (stage,order) 序 a..e -> palette[0..4]
FLOW_ROWS = [
    {"s": "a", "d": "b", "v": 80},
    {"s": "a", "d": "c", "v": 20},
    {"s": "b", "d": "d", "v": 60},
    {"s": "b", "d": "e", "v": 20},
]

NODE_ROWS = [
    {"id": "a", "stage": 0, "label": "A"},
    {"id": "b", "stage": 1, "label": "B"},
    {"id": "c", "stage": 1, "label": "C"},
    {"id": "d", "stage": 2, "label": "D"},
    {"id": "e", "stage": 2, "label": "E"},
]


def sk_spec(**series_kw):
    s = {"kind": "sankey", "from": "f", "x": "s", "y": "d", "z": "v"}
    s.update(series_kw)
    return {
        "version": 1,
        "data": {"f": [dict(r) for r in FLOW_ROWS]},
        "meta": _meta(),
        "series": [s],
    }


# ---------------------------------------------------------------- 基础渲染


def sankey_basic():
    fig = render(sk_spec())
    ax = fig.get_axes()[0]
    probs, warns = audit_of(fig), warnings_of(fig)
    check("sk-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    bands, rects = _bands(ax), _rects(ax)
    check(
        "sk-artist-counts",
        len(bands) == 4 and len(rects) == 6,
        f"bands={len(bands)} rects={len(rects)}",
    )
    # 全部 artist fv-neutral：轴语义规则不适用 sankey（fv-neutral 也是
    # missing-axis-label 自动放行的通道——无 audit_ignore 也干净）
    check(
        "sk-neutral-gid",
        all(p.get_gid() == "fv-neutral" for p in ax.patches)
        and all(t.get_gid() == "fv-neutral" for t in ax.texts),
        "some artist lacks fv-neutral",
    )
    check(
        "sk-null-locator",
        isinstance(ax.xaxis.get_major_locator(), NullLocator)
        and isinstance(ax.yaxis.get_major_locator(), NullLocator),
        "locators not NullLocator",
    )
    check(
        "sk-frame-minimal",
        all(not s.get_visible() for s in ax.spines.values()),
        "spines visible",
    )
    check(
        "sk-no-ticklabels",
        not ax.get_xticklabels() and not ax.get_yticklabels(),
        "tick labels leaked",
    )
    texts = [t.get_text() for t in ax.texts]
    check(
        "sk-label-texts",
        texts == ["a 100", "b 80", "c 20", "d 60", "e 20"],
        f"texts={texts}",
    )
    plt.close(fig)


# ------------------------------------------------------------------ 几何


def sankey_geometry():
    """手算布局（gap=0.05*100=5, max_h=105, mid=52.5, w=0.18 hw=0.09）：
    a@[2.5,102.5]@x0；b@[25,105]、c@[0,20]@x1；d@[35,95]、e@[10,30]@x2。"""
    fig = render(sk_spec())
    ax = fig.get_axes()[0]
    hw = 0.09
    rects = _rects(ax)
    geo = sorted(
        (round(p.get_x(), 4), round(p.get_y(), 4), round(p.get_height(), 4))
        for p in rects
    )
    want = sorted(
        [
            (-hw, 22.5, 80.0),  # a 出段 a->b
            (-hw, 2.5, 20.0),  # a 出段 a->c
            (1 - hw, 25.0, 80.0),  # b 入段
            (1 - hw, 0.0, 20.0),  # c 入段
            (2 - hw, 35.0, 60.0),  # d 入段
            (2 - hw, 10.0, 20.0),  # e 入段
        ]
    )
    check("sk-node-segs", geo == want, f"geo={geo}")

    # 缎带端点 = 两端段区间：a->b [22.5,102.5]@0.09 -> [25,105]@0.91
    band_ab = None
    for p in _bands(ax):
        v = p.get_path().vertices
        if np.isclose(v[0][0], hw) and np.isclose(v[0][1], 102.5):
            band_ab = v
    check("sk-band-found", band_ab is not None, "a->b ribbon not found")
    if band_ab is not None:
        v = band_ab
        ok = (
            np.allclose(v[0], (hw, 102.5))
            and np.allclose(v[3], (1 - hw, 105.0))
            and np.allclose(v[4], (1 - hw, 25.0))
            and np.allclose(v[7], (hw, 22.5))
        )
        # 控制点中点 x：CURVE4 列 (xm,xm,x1)
        mid_x_ok = np.isclose(v[1][0], 0.5) and np.isclose(v[2][0], 0.5)
        check("sk-band-verts", ok and mid_x_ok, f"verts={v.tolist()}")

    # 出段按对端列位自上向下堆：b->d（d rank0）压在 b->e 之上——
    # 由 b 的入段条无重叠读出：缎带锚点区间
    seg = {}
    for p in _bands(ax):
        v = p.get_path().vertices
        if np.isclose(v[0][0], 1 + hw):  # 从 b 右缘出发
            seg[round(v[0][1], 1)] = (round(v[4][1], 1), round(v[3][1], 1))
    # v[0]=左缘顶（b 侧 hi0）、v[3]/v[4]=右缘 dst 侧 hi1/lo1
    tops = sorted(seg, reverse=True)
    check(
        "sk-out-seg-order",
        tops == [105.0, 45.0] and seg[105.0] == (35.0, 95.0),
        f"out-segs={seg}",
    )
    plt.close(fig)

    # gap:0 —— 列内段连续无间隔；width 显式改条厚
    spec = sk_spec(gap=0, width=0.3)
    fig = render(spec)
    ax = fig.get_axes()[0]
    geo = sorted(
        (round(p.get_x(), 4), round(p.get_y(), 4), round(p.get_height(), 4))
        for p in _rects(ax)
    )
    # 重算（w=0.3 hw=0.15、gap=0）：max_h=100、mid=50；a 出段 b 在上
    # [20,100]、c [0,20]；col1 b [20,100]、c [0,20]；col2 d [30,90]、e [10,30]
    want = sorted(
        [
            (-0.15, 20.0, 80.0),
            (-0.15, 0.0, 20.0),
            (0.85, 20.0, 80.0),
            (0.85, 0.0, 20.0),
            (1.85, 30.0, 60.0),
            (1.85, 10.0, 20.0),
        ]
    )
    check("sk-gap0-width", geo == want, f"geo={geo}")
    plt.close(fig)


def sankey_order_field():
    """列内 order 覆盖首见序：c 提到 b 之上。"""
    spec = sk_spec(
        nodes=[
            {"id": "a", "stage": 0},
            {"id": "b", "stage": 1, "order": 1},
            {"id": "c", "stage": 1, "order": 0},
            {"id": "d", "stage": 2},
            {"id": "e", "stage": 2},
        ]
    )
    fig = render(spec)
    ax = fig.get_axes()[0]
    geo = {
        (round(p.get_y(), 1), round(p.get_height(), 1))
        for p in _rects(ax)
        if np.isclose(p.get_x(), 1 - 0.09)
    }
    # c(order0) 先堆 -> 顶 [85,105]；b 在下 [0,80]
    check(
        "sk-order-swap",
        geo == {(85.0, 20.0), (0.0, 80.0)},
        f"col1 segs={geo}",
    )
    plt.close(fig)


# ------------------------------------------------------------- nodes 表


def sankey_nodes_forms():
    # dataset 名形：label 覆盖 + heads
    spec = sk_spec(nodes="n", heads=["s0", "s1", "s2"])
    spec["data"]["n"] = [dict(r) for r in NODE_ROWS]
    fig = render(spec)
    ax = fig.get_axes()[0]
    texts = [t.get_text() for t in ax.texts]
    check(
        "sk-nodes-ds-labels",
        texts[:5] == ["A 100", "B 80", "C 20", "D 60", "E 20"]
        and texts[5:] == ["s0", "s1", "s2"],
        f"texts={texts}",
    )
    probs, warns = audit_of(fig), warnings_of(fig)
    check("sk-nodes-ds-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # heads dict 按 stage 值键控
    spec = sk_spec(nodes="n", heads={1: "mid"})
    spec["data"]["n"] = [dict(r) for r in NODE_ROWS]
    fig = render(spec)
    ax = fig.get_axes()[0]
    heads = [t for t in ax.texts if t.get_text() == "mid"]
    check(
        "sk-heads-dict",
        len(heads) == 1 and np.isclose(heads[0].get_position()[0], 1.0),
        f"heads={[(t.get_text(), t.get_position()) for t in ax.texts]}",
    )
    plt.close(fig)

    # 字面行 + stage 稀疏 {0,2}：列位按 rank 紧凑排（stage2 -> x=1）
    spec = sk_spec(nodes=[{"id": "a", "stage": 0}, {"id": "b", "stage": 2}])
    spec["data"]["f"] = [{"s": "a", "d": "b", "v": 5}]
    fig = render(spec)
    ax = fig.get_axes()[0]
    xs = {round(p.get_x(), 4) for p in _rects(ax)}
    check("sk-sparse-stage", xs == {-0.09, 0.91}, f"xs={xs}")
    plt.close(fig)


def sankey_nodes_errors():
    def spec(**kw):
        s = sk_spec(**kw)
        return s

    # 未知 dataset 名
    expect_error("sk-nodes-unknown-ds", spec(nodes="nope"), "unknown nodes dataset")
    # 端点缺席
    s = spec(nodes=[dict(r) for r in NODE_ROWS[:-1]])  # 少 e
    expect_error("sk-endpoint-absent", s, "absent from 'nodes'")
    # orphan 节点
    rows = [dict(r) for r in NODE_ROWS] + [{"id": "z", "stage": 2}]
    expect_error("sk-orphan", spec(nodes=rows), "not referenced")
    # 重复 id
    rows = [dict(r) for r in NODE_ROWS] + [{"id": "a", "stage": 0}]
    expect_error("sk-dup-node", spec(nodes=rows), "duplicate node id")
    # 非 dict 行 / 缺 id / 坏 stage / 坏 order / 坏 label / 未知键
    expect_error(
        "sk-node-nondict",
        spec(nodes=[{"id": "a"}, "x"]),
        "must be an object",
    )
    expect_error("sk-node-noid", spec(nodes=[{"stage": 0}]), "needs an 'id'")
    expect_error(
        "sk-node-badstage",
        spec(nodes=[{"id": "a", "stage": -1}]),
        "stage must be an integer",
    )
    expect_error(
        "sk-node-stage-str",
        spec(nodes=[{"id": "a", "stage": "x"}]),
        "stage must be numeric",
    )
    expect_error(
        "sk-node-badorder",
        spec(nodes=[{"id": "a", "order": "x"}]),
        "order must be numeric",
    )
    expect_error(
        "sk-node-badlabel",
        spec(nodes=[{"id": "a", "label": 5}]),
        "label must be a string",
    )
    expect_error(
        "sk-node-badkey",
        spec(nodes=[{"id": "a", "bogus": 1}]),
        "unknown keys",
        "bogus",
    )
    # stage 混给（部分节点有）
    rows = [dict(r) for r in NODE_ROWS]
    del rows[0]["stage"]
    expect_error("sk-stage-mixed", spec(nodes=rows), "all nodes or none")
    # 回退流（显式 stage src>=dst）
    s = spec(nodes=[{"id": "a", "stage": 1}, {"id": "b", "stage": 0}])
    s["data"]["f"] = [{"s": "a", "d": "b", "v": 5}]
    expect_error("sk-backward-flow", s, "later column")
    # 派生模式环
    s = spec()
    s["data"]["f"] = [
        {"s": "a", "d": "b", "v": 1},
        {"s": "b", "d": "a", "v": 1},
    ]
    expect_error("sk-cycle", s, "cycle")


def sankey_stage_topology():
    """longest-path 分层：a->b->c 与 a->c 并存时 c 落最深列（d3 justify），
    显式 stage 可把它拉回中间列。"""
    spec = sk_spec()
    spec["data"]["f"] = [
        {"s": "a", "d": "b", "v": 5},
        {"s": "b", "d": "c", "v": 5},
        {"s": "a", "d": "c", "v": 5},
    ]
    fig = render(spec)
    ax = fig.get_axes()[0]
    xs = {round(p.get_x(), 4) for p in _rects(ax)}
    # c 走最长链 -> 第 3 列（x=2-hw）；若按最短链会落 x=1-hw
    check("sk-justify-deep", 1.91 in xs, f"rect xs={xs}")
    plt.close(fig)

    # 显式 stage 可推迟节点制造更长列序：菱形拓扑派生给 3 列，把 b 推到
    # stage2、d 推到 stage3 得 4 列（派生模式产不出的排布）
    spec = sk_spec(
        nodes=[
            {"id": "a", "stage": 0},
            {"id": "b", "stage": 2},
            {"id": "c", "stage": 1},
            {"id": "d", "stage": 3},
        ]
    )
    spec["data"]["f"] = [
        {"s": "a", "d": "b", "v": 5},
        {"s": "a", "d": "c", "v": 5},
        {"s": "b", "d": "d", "v": 5},
        {"s": "c", "d": "d", "v": 5},
    ]
    fig = render(spec)
    xs = {round(p.get_x(), 4) for p in _rects(fig.get_axes()[0])}
    check(
        "sk-stage-explicit",
        2.91 in xs and 1.91 in xs,
        f"rect xs={xs}",
    )
    plt.close(fig)


# ------------------------------------------------------------------ 守恒


def sankey_conservation():
    spec = sk_spec()
    spec["data"]["f"] = [
        {"s": "a", "d": "b", "v": 10},
        {"s": "b", "d": "c", "v": 7},
    ]
    expect_error("sk-conservation", spec, "inflow 10 != outflow 7")

    # 纯源/纯汇豁免：b 只出不进、c 只进不出
    spec = sk_spec()
    spec["data"]["f"] = [
        {"s": "b", "d": "c", "v": 3},
        {"s": "a", "d": "c", "v": 5},
    ]
    fig = render(spec)
    check("sk-source-sink-ok", len(_bands(fig.get_axes()[0])) == 2, "render failed")
    plt.close(fig)


# --------------------------------------------------------------- 流行校验


def sankey_flow_errors():
    spec = sk_spec()
    spec["data"]["f"][0]["v"] = "lots"
    expect_error("sk-z-nonnumeric", spec, "non-numeric")

    spec = sk_spec()
    spec["data"]["f"][0]["v"] = -5
    expect_error("sk-z-negative", spec, "negative flow")

    spec = sk_spec()
    spec["data"]["f"].append({"s": "a", "d": "a", "v": 1})
    expect_error("sk-self-loop", spec, "self-loop")

    spec = sk_spec()
    spec["data"]["f"].append({"s": "a", "d": "b", "v": 1})
    expect_error("sk-dup-flow", spec, "duplicate flow")

    spec = sk_spec()
    spec["data"]["f"][0]["v"] = None
    fig = render(spec)
    hits = [w for w in warnings_of(fig) if w.startswith("missing-rows")]
    bands = _bands(fig.get_axes()[0])
    check(
        "sk-none-row-drop",
        bool(hits) and len(bands) == 3,
        f"warnings={warnings_of(fig)} bands={len(bands)}",
    )
    plt.close(fig)

    # 字面数组长度不齐
    spec = sk_spec()
    spec["series"][0]["x"] = ["a", "a", "b"]
    expect_error("sk-literal-misaligned", spec, "literal lists must align")

    # 缺 z 字段
    spec = sk_spec()
    del spec["series"][0]["z"]
    expect_error("sk-missing-z", spec, "missing required 'z'")

    # where 行过滤照常（删 a 出流后 b/c 变纯源——守恒仍成立）
    spec = sk_spec()
    spec["series"][0]["where"] = {"s": {"$ne": "a"}}
    fig = render(spec)
    check(
        "sk-where-filter",
        len(_bands(fig.get_axes()[0])) == 2,
        f"bands={len(_bands(fig.get_axes()[0]))}",
    )
    plt.close(fig)


# ------------------------------------------------------------------ 颜色


def sankey_colors():
    pal = fv.series_colors("paper", 9)

    # 默认：缎带色 = dst 节点色（palette 按 (stage,order) 序 a..e）
    fig = render(sk_spec())
    ax = fig.get_axes()[0]
    got = sorted(tuple(np.round(p.get_facecolor()[:3], 6)) for p in _bands(ax))
    # 四个 dst: b,c,d,e -> palette[1..4]
    want = sorted(
        tuple(np.round(to_rgba(c)[:3], 6)) for c in (pal[1], pal[2], pal[3], pal[4])
    )
    check("sk-dst-colors", got == want, f"got={got} want={want}")
    plt.close(fig)

    # 节点行 color 覆盖：b -> vrose（避开调色板前 5 色），a->b 缎带随之变、
    # 其余 dst 色不受影响
    spec = sk_spec(nodes="n")
    spec["data"]["n"] = [dict(r) for r in NODE_ROWS]
    spec["data"]["n"][1]["color"] = "vrose"
    fig = render(spec)
    got = sorted(
        tuple(np.round(p.get_facecolor()[:3], 6)) for p in _bands(fig.get_axes()[0])
    )
    want = sorted(
        tuple(np.round(to_rgba(c)[:3], 6))
        for c in (fv.HUES["vrose"], pal[2], pal[3], pal[4])
    )
    check("sk-node-color-override", got == want, f"got={got}")
    plt.close(fig)

    # {'field':h} 逐行 token
    spec = sk_spec(color={"field": "h"})
    for i, h in enumerate(["vteal", "vcoral", "vteal", "vgold"]):
        spec["data"]["f"][i]["h"] = h
    fig = render(spec)
    got = sorted(
        tuple(np.round(p.get_facecolor()[:3], 6)) for p in _bands(fig.get_axes()[0])
    )
    want6 = sorted(
        tuple(np.round(to_rgba(fv.HUES[h])[:3], 6))
        for h in ("vteal", "vcoral", "vteal", "vgold")
    )
    check("sk-field-colors", got == want6, f"got={got}")
    plt.close(fig)

    # {'registry','field'} 逐行查表
    spec = sk_spec(color={"registry": "arm", "field": "h"})
    spec["colors"] = {
        "registries": {"arm": {"t1": "vteal", "t2": "vcoral", "t3": "vgold"}}
    }
    for i, h in enumerate(["t1", "t2", "t1", "t3"]):
        spec["data"]["f"][i]["h"] = h
    fig = render(spec)
    got = sorted(
        tuple(np.round(p.get_facecolor()[:3], 6)) for p in _bands(fig.get_axes()[0])
    )
    want6 = sorted(
        tuple(np.round(to_rgba(fv.HUES[h])[:3], 6))
        for h in ("vteal", "vcoral", "vteal", "vgold")
    )
    check("sk-registry-field-colors", got == want6, f"got={got}")
    plt.close(fig)

    # 统一色三形态
    for cspec, want_hex in (
        ("vblue", fv.HUES["vblue"]),
        ("arm:t1", fv.HUES["vteal"]),
        ({"palette": 3}, pal[3]),
    ):
        spec = sk_spec(color=cspec)
        spec["colors"] = {"registries": {"arm": {"t1": "vteal"}}}
        fig = render(spec)
        ax = fig.get_axes()[0]
        ok = all(
            np.allclose(
                np.round(p.get_facecolor()[:3], 6),
                np.round(to_rgba(want_hex)[:3], 6),
            )
            for p in ax.patches  # 缎带与节点条同色
        )
        check(f"sk-uniform-{cspec}", ok, "not uniform")
        plt.close(fig)

    # 节点 color + series color 同写 -> axis-ignored
    spec = sk_spec(nodes="n", color="vblue")
    spec["data"]["n"] = [dict(r) for r in NODE_ROWS]
    spec["data"]["n"][1]["color"] = "vcoral"
    expect_lint("sk-node-vs-series-color", spec, "axis-ignored")


def sankey_color_errors():
    spec = sk_spec(color="arm")
    spec["colors"] = {"registries": {"arm": {"t1": "vteal"}}}
    expect_error("sk-bare-registry", spec, "names a whole table")

    spec = sk_spec(color={"a": "vteal"})
    expect_error("sk-inline-map", spec, "no group context")

    spec = sk_spec(color="parent")
    expect_error("sk-color-parent", spec, "needs a parent series")

    spec = sk_spec(color={"field": "h"})  # h 列不存在
    expect_error("sk-field-missing", spec, "missing or non-string")

    spec = sk_spec(color={"registry": "nope", "field": "h"})
    expect_error("sk-registry-unknown", spec, "no registry")

    spec = sk_spec(color={"ramp": "seq"})
    spec["colors"] = {"ramps": {"seq": {"a": "vteal", "b": "vcoral"}}}
    expect_error("sk-ramp-dict", spec, "no group context")


# ------------------------------------------------------------ 标签与列头


def sankey_labels():
    # False -> 无节点标签文本
    fig = render(sk_spec(labels=False))
    check(
        "sk-labels-off",
        len(fig.get_axes()[0].texts) == 0,
        f"texts={[t.get_text() for t in fig.get_axes()[0].texts]}",
    )
    plt.close(fig)

    # 模板串 + vfmt + fontsize
    spec = sk_spec(labels="{id}|{value:.0f}")
    fig = render(spec)
    texts = [t.get_text() for t in fig.get_axes()[0].texts]
    check(
        "sk-label-template",
        texts == ["a|100", "b|80", "c|20", "d|60", "e|20"],
        f"texts={texts}",
    )
    plt.close(fig)

    spec = sk_spec(labels={"vfmt": "{:.1f}", "fontsize": 12})
    fig = render(spec)
    ax = fig.get_axes()[0]
    texts = [t.get_text() for t in ax.texts]
    check(
        "sk-label-vfmt-fs",
        texts == ["a 100.0", "b 80.0", "c 20.0", "d 60.0", "e 20.0"]
        and all(t.get_fontsize() == 12 for t in ax.texts),
        f"texts={texts}",
    )
    plt.close(fig)

    # 放置策略：首列 ha=right 贴条左、末列 ha=left 贴条右、
    # 中列 ha=right + 白带衬底
    fig = render(sk_spec())
    ax = fig.get_axes()[0]
    by_text = {t.get_text().split()[0]: t for t in ax.texts}
    check(
        "sk-label-ha-first",
        by_text["a"].get_ha() == "right" and by_text["a"].get_bbox_patch() is None,
        f"a ha={by_text['a'].get_ha()}",
    )
    check(
        "sk-label-ha-last",
        by_text["d"].get_ha() == "left" and by_text["d"].get_bbox_patch() is None,
        f"d ha={by_text['d'].get_ha()}",
    )
    check(
        "sk-label-mid-bbox",
        by_text["b"].get_ha() == "right" and by_text["b"].get_bbox_patch() is not None,
        f"b ha={by_text['b'].get_ha()}",
    )
    plt.close(fig)

    # labels 形态错误
    expect_error("sk-labels-int", sk_spec(labels=5), "must be true|false")
    expect_error(
        "sk-labels-badkey",
        sk_spec(labels={"bogus": 1}),
        "unknown keys",
    )
    expect_error(
        "sk-labels-template-type",
        sk_spec(labels={"template": 5}),
        "must be a string",
    )
    expect_error(
        "sk-labels-badfmt",
        sk_spec(labels={"vfmt": "{bad"}),
        "bad labels template/vfmt",
    )
    expect_error("sk-heads-str", sk_spec(heads="x"), "must be a list of column labels")
    expect_error(
        "sk-heads-baditem", sk_spec(heads=[1, 2]), "must be a list of column labels"
    )


# ------------------------------------------------------------- 面板约束


def sankey_panel_rules():
    # 混 kind
    spec = sk_spec()
    spec["series"].append({"kind": "bar", "from": "f", "x": "s", "y": "v"})
    expect_error("sk-mix-kind", spec, "cannot share a panel", "bar")

    # 双 sankey
    spec = sk_spec()
    spec["series"].append(dict(spec["series"][0]))
    expect_error("sk-two-sankey", spec, "multiple sankey")

    # y2
    spec = sk_spec()
    spec["y2"] = {"label": "other"}
    expect_error("sk-y2", spec, "'y2' with sankey")

    # 中性 overlay 放行
    spec = sk_spec()
    spec["series"].append({"kind": "note", "at": [0.5, 50], "text": "hi"})
    fig = render(spec)
    check(
        "sk-note-overlay-ok",
        any(t.get_text() == "hi" for t in fig.get_axes()[0].texts),
        "note missing",
    )
    plt.close(fig)

    # radar 面板拒收
    spec = {
        "version": 1,
        "kind": "radar",
        "dims": ["a", "b"],
        "data": {"f": [{"s": "a", "d": "b", "v": 1}]},
        "series": [{"kind": "sankey", "x": "s", "y": "d", "z": "v"}],
        "meta": _meta(),
    }
    expect_error("sk-on-radar", spec, "not allowed in")


def sankey_axis_overrides():
    # xaxis.ticks -> axis-ignored；lim/label 照用
    spec = sk_spec()
    spec["xaxis"] = {"ticks": [0, 1, 2]}
    expect_lint("sk-xaxis-ticks", spec, "axis-ignored")

    spec = sk_spec()
    spec["xaxis"] = {"lim": {"left": -1, "right": 3}, "label": "flow"}
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "sk-xaxis-lim-label",
        ax.get_xlim() == (-1.0, 3.0) and ax.get_xlabel() == "flow",
        f"xlim={ax.get_xlim()} label={ax.get_xlabel()!r}",
    )
    plt.close(fig)

    # frame/grid 显式钉回
    spec = sk_spec()
    spec["frame"] = "closed"
    spec["grid"] = "y-only"
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "sk-frame-grid-pinned",
        all(s.get_visible() for s in ax.spines.values()),
        "spines not restored",
    )
    plt.close(fig)

    # 布局参数错误面
    expect_error("sk-gap-neg", sk_spec(gap=-1), "gap must be")
    expect_error("sk-width-0", sk_spec(width=0), "width must be")
    expect_error("sk-width-1", sk_spec(width=1.5), "width must be")
    expect_error("sk-pad-neg", sk_spec(pad=-0.1), "pad must be")
    expect_error("sk-dead-key-by", sk_spec(by="s"), "'by' does not apply")
    expect_error("sk-unknown-key", sk_spec(bogus=1), "unknown keys", "bogus")


# ------------------------------------------------------------------ 样式


def sankey_style():
    spec = sk_spec(alpha=0.3, zorder=5, props={"edgecolor": "black", "lw": 1.0})
    fig = render(spec)
    ax = fig.get_axes()[0]
    bands = _bands(ax)
    check(
        "sk-alpha",
        all(np.isclose(p.get_alpha(), 0.3) for p in bands),
        f"alphas={[p.get_alpha() for p in bands]}",
    )
    check(
        "sk-props-win",
        all(
            tuple(p.get_edgecolor()[:3]) == (0.0, 0.0, 0.0)
            and np.isclose(p.get_linewidth(), 1.0)
            for p in bands
        ),
        f"ecs={[p.get_edgecolor() for p in bands]} lws={[p.get_linewidth() for p in bands]}",
    )
    check(
        "sk-zorder",
        all(np.isclose(p.get_zorder(), 5) for p in bands),
        f"zorders={[p.get_zorder() for p in bands]}",
    )
    # 节点条随 zorder 基线抬 0.4
    check(
        "sk-node-zorder",
        all(np.isclose(p.get_zorder(), 5.4) for p in _rects(ax)),
        f"rect z={[p.get_zorder() for p in _rects(ax)]}",
    )
    plt.close(fig)


# ------------------------------------------------------------- dir:'v' 竖向


def sankey_vertical():
    """dir:'v'：列变行、流自上向下——几何是 h 的轴向镜像（行内自左向右
    堆叠、段区间在 x、行进轴在 y），守恒/节点表/标签策略语义不变。"""
    spec = sk_spec(dir="v", heads=["s0", "s1", "s2"])
    fig = render(spec)
    ax = fig.get_axes()[0]
    probs, warns = audit_of(fig), warnings_of(fig)
    check("skv-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    check(
        "skv-artist-counts",
        len(_bands(ax)) == 4 and len(_rects(ax)) == 6,
        f"bands={len(_bands(ax))} rects={len(_rects(ax))}",
    )
    check(
        "skv-neutral-gid",
        all(p.get_gid() == "fv-neutral" for p in ax.patches)
        and all(t.get_gid() == "fv-neutral" for t in ax.texts),
        "some artist lacks fv-neutral",
    )
    # 手算（同 h 口径、轴向对调）：gap=5、max_h=105、mid=52.5、hw=0.09；
    # 行位 y=R-1-rank（stage0 在顶 y=2）；行内自左向右堆——a[2.5,102.5]
    # @y2；b[0,80]、c[85,105]@y1；d[10,70]、e[75,95]@y0
    geo = sorted(
        (round(p.get_x(), 4), round(p.get_y(), 4), round(p.get_width(), 4))
        for p in _rects(ax)
    )
    want = sorted(
        [
            (2.5, 1.91, 80.0),  # a 出段 a->b（左切片）
            (82.5, 1.91, 20.0),  # a 出段 a->c（右切片）
            (0.0, 0.91, 80.0),  # b 入段
            (85.0, 0.91, 20.0),  # c 入段
            (10.0, -0.09, 60.0),  # d 入段
            (75.0, -0.09, 20.0),  # e 入段
        ]
    )
    check("skv-node-segs", geo == want, f"geo={geo}")
    # 缎带行进轴在 y：a->b 自 a 底缘 y=1.91 的 x 段 [2.5,82.5] 到 b 顶缘
    # y=1.09 的 x 段 [0,80]；verts[0]=(hi0,y0)、控制点中点 y=1.5
    band_ab = None
    for p in _bands(ax):
        v = p.get_path().vertices
        if np.isclose(v[0][1], 1.91) and np.isclose(v[0][0], 82.5):
            band_ab = v
    check("skv-band-found", band_ab is not None, "a->b ribbon not found")
    if band_ab is not None:
        v = band_ab
        ok = (
            np.allclose(v[0], (82.5, 1.91))
            and np.allclose(v[3], (80.0, 1.09))
            and np.allclose(v[4], (0.0, 1.09))
            and np.allclose(v[7], (2.5, 1.91))
        )
        mid_y_ok = np.isclose(v[1][1], 1.5) and np.isclose(v[2][1], 1.5)
        check("skv-band-verts", ok and mid_y_ok, f"verts={v.tolist()}")
    # 标签镜像：首行（a）上置 va=bottom、中行（b/c）上置 + 白带衬底、
    # 末行（d/e）下置 va=top
    lab = {t.get_text().split()[0]: t for t in ax.texts}
    check(
        "skv-label-pos",
        lab["a"].get_va() == "bottom"
        and np.isclose(lab["a"].get_position()[1], 2.14)
        and lab["b"].get_va() == "bottom"
        and lab["b"].get_bbox_patch() is not None
        and lab["d"].get_va() == "top"
        and lab["e"].get_va() == "top",
        f"{[(k, t.get_va()) for k, t in lab.items()]}",
    )
    # 行头镜像：左缘右对齐（row_left - head_off），head_off=0.04*105=4.2
    heads = {t.get_text(): t for t in ax.texts if t.get_text() in ("s0", "s1", "s2")}
    check(
        "skv-heads",
        all(t.get_ha() == "right" and t.get_va() == "center" for t in heads.values())
        and np.isclose(heads["s0"].get_position()[0], 2.5 - 4.2)
        and np.isclose(heads["s0"].get_position()[1], 2.0)
        and np.isclose(heads["s1"].get_position()[0], 0.0 - 4.2)
        and np.isclose(heads["s2"].get_position()[1], 0.0),
        f"{[(k, t.get_position()) for k, t in heads.items()]}",
    )
    # 视窗：行进轴 y 上下留标签通道（m=0.6+hw=0.69）、量轴 x 左留行头
    check(
        "skv-lims",
        np.allclose(ax.get_ylim(), (-0.69, 2.69))
        and ax.get_xlim()[1] > 105.0
        and ax.get_xlim()[0] < -4.2,
        f"xlim={ax.get_xlim()} ylim={ax.get_ylim()}",
    )
    plt.close(fig)

    # dir 枚举响亮拒
    expect_error("skv-bad-dir", sk_spec(dir="x"), "dir must be 'h'")
    # 守恒校验与方向无关：dir:'v' 下违例同样报
    spec = sk_spec(dir="v")
    spec["data"]["f"] = [
        {"s": "a", "d": "b", "v": 10},
        {"s": "b", "d": "c", "v": 7},
    ]
    expect_error("skv-conservation", spec, "inflow 10 != outflow 7")


# ----------------------------------------------------------- flows 字面行

LIT_FLOWS = [
    {"source": "a", "target": "b", "value": 80},
    {"source": "a", "target": "c", "value": 20},
    {"source": "b", "target": "d", "value": 60},
    {"source": "b", "target": "e", "value": 20},
]


def lit_spec(**series_kw):
    s = {"kind": "sankey", "flows": [dict(f) for f in LIT_FLOWS]}
    s.update(series_kw)
    return {"version": 1, "meta": _meta(), "series": [s]}


def sankey_literal_flows():
    """flows 字面行：数据自由形态（from/x/y/z/where 属长表形态）——
    节点仍按端点推导、几何/守恒与长表同口径。"""
    fig = render(lit_spec())
    ax = fig.get_axes()[0]
    probs, warns = audit_of(fig), warnings_of(fig)
    check("skf-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    check(
        "skf-artists",
        len(_bands(ax)) == 4 and len(_rects(ax)) == 6,
        f"bands={len(_bands(ax))} rects={len(_rects(ax))}",
    )
    texts = [t.get_text() for t in ax.texts]
    check(
        "skf-labels",
        texts == ["a 100", "b 80", "c 20", "d 60", "e 20"],
        f"texts={texts}",
    )
    plt.close(fig)

    # nodes 字面行同口径（label 覆盖）
    spec = lit_spec(nodes=[{"id": n, "label": n.upper()} for n in "abcde"])
    fig = render(spec)
    texts = [t.get_text() for t in fig.get_axes()[0].texts]
    check(
        "skf-nodes-literal",
        texts == ["A 100", "B 80", "C 20", "D 60", "E 20"],
        f"texts={texts}",
    )
    plt.close(fig)

    # nodes 仍可点名 dataset——系列无 'from' 不妨碍节点表查库
    spec = lit_spec(nodes="n")
    spec["data"] = {"n": [dict(r) for r in NODE_ROWS]}
    fig = render(spec)
    texts = [t.get_text() for t in fig.get_axes()[0].texts]
    check("skf-nodes-ds", texts[:2] == ["A 100", "B 80"], f"texts={texts}")
    plt.close(fig)

    # 流行多余键可作 color field（与数据行同口径）
    flows = [
        dict(f, h=h) for f, h in zip(LIT_FLOWS, ("vteal", "vcoral", "vteal", "vgold"))
    ]
    spec = lit_spec(color={"field": "h"})
    spec["series"][0]["flows"] = flows
    fig = render(spec)
    got = sorted(
        tuple(np.round(p.get_facecolor()[:3], 6)) for p in _bands(fig.get_axes()[0])
    )
    want = sorted(
        tuple(np.round(to_rgba(fv.HUES[h])[:3], 6))
        for h in ("vteal", "vcoral", "vteal", "vgold")
    )
    check("skf-color-field", got == want, f"got={got}")
    plt.close(fig)

    # dir:'v' 与 flows 组合：行内堆叠同 skv 手算
    fig = render(lit_spec(dir="v"))
    xs = {round(p.get_x(), 4) for p in _rects(fig.get_axes()[0])}
    check("skf-v-x0", 2.5 in xs and 85.0 in xs, f"xs={xs}")
    plt.close(fig)

    # matrix facet 不注入 where（_series_data_bound 镜像——裸 flows 形态
    # 注入会在渲染期炸 'where needs a data source'）
    spec = {
        "version": 1,
        "data": {"d": [{"g": "p"}, {"g": "q"}]},
        "layout": {
            "kind": "matrix",
            "cols": {"field": "g"},
            "template": {
                "series": [
                    {
                        "kind": "sankey",
                        "flows": [dict(f) for f in LIT_FLOWS],
                    }
                ]
            },
        },
        "meta": _meta(),
    }
    fig = render(spec)
    bands = [len(_bands(a)) for a in fig.get_axes()[:2]]
    check("skf-matrix-no-where", bands == [4, 4], f"bands={bands}")
    plt.close(fig)

    # 长表键响亮拒
    expect_error("skf-x-key", lit_spec(x="s"), "belongs to the long-table", "'flows'")
    expect_error("skf-from-key", lit_spec(**{"from": "f"}), "long-table")
    expect_error("skf-where-key", lit_spec(where={"s": "a"}), "long-table")
    # 形态校验：非表/非 dict 行/缺键/None 值
    expect_error("skf-not-list", lit_spec(flows="ab"), "non-empty list")
    expect_error(
        "skf-nondict-row",
        lit_spec(flows=[{"source": "a", "target": "b", "value": 1}, "x"]),
        "non-empty list",
    )
    expect_error(
        "skf-missing-key",
        lit_spec(flows=[{"source": "a", "target": "b"}]),
        "is missing",
    )
    expect_error(
        "skf-none-value",
        lit_spec(flows=[{"source": "a", "target": "b", "value": None}]),
        "is missing",
    )
    # 守恒/自环/负值同口径
    expect_error(
        "skf-conservation",
        lit_spec(
            flows=[
                {"source": "a", "target": "b", "value": 10},
                {"source": "b", "target": "c", "value": 7},
            ]
        ),
        "inflow 10 != outflow 7",
    )
    expect_error(
        "skf-self-loop",
        lit_spec(flows=[{"source": "a", "target": "a", "value": 1}]),
        "self-loop",
    )
    expect_error(
        "skf-negative",
        lit_spec(flows=[{"source": "a", "target": "b", "value": -1}]),
        "negative flow",
    )


def main() -> int:
    sankey_basic()
    sankey_geometry()
    sankey_order_field()
    sankey_nodes_forms()
    sankey_nodes_errors()
    sankey_stage_topology()
    sankey_conservation()
    sankey_flow_errors()
    sankey_colors()
    sankey_color_errors()
    sankey_labels()
    sankey_panel_rules()
    sankey_axis_overrides()
    sankey_style()
    sankey_vertical()
    sankey_literal_flows()
    print(f"--- spec_sankey: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
