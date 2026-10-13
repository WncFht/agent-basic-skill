#!/usr/bin/env python3
"""test_spec.py — fvspec 渲染引擎测试。

- 回归：examples/spec_*.json 全部渲染干净（无 lint、audit 零问题、产物落盘）
- 错误面：每类 SpecError 各一例，断言响亮报错（含关键子串）
- lint 面：empty-series / hex-literal / pred-indistinct / fill-ignored /
  ignore-unscoped / unknown-ignore 触发与抑制
- polar 回归：radar 面板的 scatter/band/ref/span 走 dim->angle 映射；
  未知 dim 响亮报错
- audit 接线：audit.ignore 图级豁免、panel audit_ignore -> scoped_ignore

运行：uv run --with matplotlib --with numpy python scripts/test_spec.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.container import BarContainer, ErrorbarContainer

SKILL_DIR = Path(__file__).resolve().parents[1]

EXAMPLES = sorted((SKILL_DIR / "scripts" / "examples").glob("spec_*.json"))


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


# ------------------------------------------------------------ golden 样例


def examples_clean():
    check("examples found", len(EXAMPLES) >= 5, f"{EXAMPLES}")
    for path in EXAMPLES:
        spec = json.loads(path.read_text())
        fig = render(spec)
        probs = audit_of(fig)
        warns = warnings_of(fig)
        check(
            f"example:{path.stem}",
            not probs and not warns,
            f"audit={probs[:2]} warnings={warns[:2]}",
        )
        plt.close(fig)


# --------------------------------------------------------------- SpecError 面


def errors():
    base = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }

    def mod(_drop=(), **kw):
        s = json.loads(json.dumps(base))
        s.update(kw)
        for k in _drop:
            s.pop(k, None)
        return s

    expect_error("version", mod(version=9), "version", "unsupported")
    expect_error("top-key", mod(bogus=1), "unknown keys")
    expect_error("theme", mod(theme="solarized"), "unknown theme")
    expect_error(
        "series-kind", mod(series=[{"kind": "ridgeline", "x": "x"}]), "unknown kind"
    )
    expect_error(
        "series-key",
        mod(series=[{"kind": "line", "x": "x", "y": "y", "zzz": 1}]),
        "unknown keys",
    )
    expect_error(
        "missing-y", mod(series=[{"kind": "line", "x": "x"}]), "missing required"
    )
    expect_error(
        "unknown-dataset",
        mod(series=[{"kind": "line", "from": "nope", "x": "x", "y": "y"}]),
        "unknown dataset",
    )
    expect_error(
        "color-namespace",
        mod(series=[{"kind": "line", "x": "x", "y": "y", "color": "bogus:1"}]),
        "unknown color namespace",
    )
    expect_error(
        "registry-miss",
        mod(
            colors={"registries": {"arm": {"a": "vteal"}}},
            series=[{"kind": "line", "x": "x", "y": "y", "by": "x", "color": "arm"}],
        ),
        "unresolved-color",
    )
    expect_error(
        "palette-oob",
        mod(series=[{"kind": "line", "x": "x", "y": "y", "color": "palette:99"}]),
        "out of range",
    )
    expect_error(
        "layout-matrix",
        mod(layout={"kind": "matrix"}),
        "expands layout.template into panels",
    )
    expect_error(
        "layout-heat",
        mod(series=[{"kind": "heatmap", "x": "x", "y": "y"}]),
        "unknown kind",
        "'heat'",
    )
    expect_error(
        "layout-overflow",
        mod(
            ("series",),
            layout={"shape": [3, 3]},
            panels={p: {"series": []} for p in "abcdefghi"},
        ),
        "exceeds",
    )
    expect_error(
        "cell-twice",
        mod(
            ("series",),
            layout={"cells": [["a", "a"], ["b", None]]},
            panels={"a": {"series": []}, "b": {"series": []}},
        ),
        "placed twice",
    )
    expect_error(
        "cell-missing",
        mod(
            ("series",),
            layout={"cells": [["a", None]]},
            panels={"a": {"series": []}, "b": {"series": []}},
        ),
        "not placed",
    )
    expect_error("share-mode", mod(layout={"sharex": "diagonal"}), "share mode")
    expect_error("span-at", mod(series=[{"kind": "span", "at": 0.5}]), "'at' must be")
    expect_error(
        "note-units",
        mod(series=[{"kind": "note", "at": [0, 1], "text": "t", "units": "pixels"}]),
        "bad units",
    )
    expect_error(
        "ref-nonunique",
        mod(series=[{"kind": "ref", "dir": "h", "at": "y"}]),
        "nonunique",
    )
    expect_error(
        "donut-labels",
        mod(
            kind="donut",
            series=[{"kind": "donut", "x": "x", "y": "y", "labels": "maybe"}],
        ),
        "labels",
    )
    expect_error("size-slot", mod(size={"slot": "quarto"}), "unknown")
    expect_error("raw-unresolvable", mod(raw="no.such.module:fn"), "raw ref")
    # --- 拒收输入的 SpecError（绝不裸抛 TypeError/KeyError）---
    expect_error("data-list", mod(data=[{"x": 0}]), "data must be an object")
    expect_error("series-dict", mod(series={"kind": "line"}), "'series' must be a list")
    expect_error("series-elem", mod(series=["nope"]), "series entries must be objects")
    expect_error(
        "dup-id",
        mod(
            series=[
                {"kind": "line", "id": "s", "x": "x", "y": "y"},
                {"kind": "line", "id": "s", "x": "x", "y": "y"},
            ]
        ),
        "duplicate series id",
    )
    expect_error(
        "by-no-field",
        mod(series=[{"kind": "line", "x": "x", "y": "y", "by": {"order": []}}]),
        "'by' needs a 'field' key",
    )
    expect_error(
        "by-order-str",
        mod(
            data={"d": [{"x": 0, "y": 1, "g": "a"}, {"x": 1, "y": 2, "g": "b"}]},
            series=[
                {
                    "kind": "line",
                    "x": "x",
                    "y": "y",
                    "by": {"field": "g", "order": "a"},
                }
            ],
        ),
        "'by.order' must be a list",
    )
    expect_error(
        "by-int",
        mod(series=[{"kind": "line", "x": "x", "y": "y", "by": 3}]),
        "'by' must be",
    )
    expect_error(
        "at-join-no-field",
        mod(series=[{"kind": "ref", "at": {"from": "d"}}]),
        "at-join dict needs a 'field' key",
    )
    expect_error("audit-ignore-str", mod(audit_ignore="collide"), "a list")
    expect_error("audit-ignore-fig", mod(audit={"ignore": "collide"}), "a list")
    expect_error("shape-1d", mod(layout={"shape": [3]}), "layout.shape")
    expect_error("shape-00", mod(layout={"shape": [0, 0]}), "layout.shape")
    expect_error(
        "cells-elem",
        mod(
            ("series",),
            layout={"cells": [["a", 3]]},
            panels={"a": {"series": []}},
        ),
        "cell ids",
    )
    expect_error("legend-where", mod(legend={"where": "above"}), "legend.where")
    expect_error(
        "legend-entries-str",
        mod(
            series=[{"kind": "line", "x": "x", "y": "y", "label": "s"}],
            legend={"where": "below", "entries": ["ln"]},
        ),
        "legend entry",
    )
    expect_error(
        "handle-color-int",
        mod(legend={"entries": [{"handle": {"label": "x", "color": 5}}]}),
        "color token",
    )
    expect_error(
        "y2-no-panel",
        mod(series=[{"kind": "line", "x": "x", "y": "y", "axis": "y2"}]),
        "axis 'y2'",
    )
    expect_error("dims-on-xy", mod(dims=["a", "b"]), "'dims' only applies to")
    expect_error("theta-on-xy", mod(theta={"offset": 90}), "'theta' only applies to")
    radar_theta = {
        "kind": "radar",
        "dims": ["a", "b"],
        "data": {"d": [{"dim": "a", "v": 1}, {"dim": "b", "v": 2}]},
        "series": [{"kind": "line", "x": "dim", "y": "v"}],
    }
    expect_error("theta-nonstr", mod(**radar_theta, theta="cw"), "must be an object")
    expect_error(
        "theta-bad-key",
        mod(**radar_theta, theta={"bogus": 1}),
        "unknown keys",
    )
    expect_error(
        "theta-bad-dir",
        mod(**radar_theta, theta={"direction": "left"}),
        "'cw'|'ccw'",
    )
    expect_error(
        "theta-bad-offset",
        mod(**radar_theta, theta={"offset": "top"}),
        "degrees",
    )
    expect_error(
        "y2-on-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            y2={"label": "oops"},
            data={"d": [{"dim": "a", "v": 1}, {"dim": "b", "v": 2}]},
            series=[{"kind": "line", "x": "dim", "y": "v"}],
        ),
        "'y2' only applies to",
    )
    expect_error(
        "donut-by",
        mod(
            kind="donut",
            data={"d": [{"x": "a", "y": 1, "g": "z"}]},
            series=[{"kind": "donut", "x": "x", "y": "y", "by": "g"}],
        ),
        "'by' does not apply",
    )
    expect_error(
        "span-str-elem",
        mod(
            series=[{"kind": "span", "at": ["x", "x"]}],
        ),
        "non-categorical",
    )
    expect_error(
        "band-stray-x",
        mod(
            data={
                "p": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
                "c": [{"x": 0, "lo": -1, "hi": 1}, {"x": 9, "lo": 0, "hi": 2}],
            },
            series=[
                {"kind": "line", "id": "ln", "from": "p", "x": "x", "y": "y"},
                {"kind": "band", "of": "ln", "from": "c", "lo": "lo", "hi": "hi"},
            ],
        ),
        "not on parent",
        "x grid",
    )
    expect_error(
        "legend-cell",
        mod(
            legend={"where": "cell", "cell": "zz"},
            series=[{"kind": "line", "x": "x", "y": "y", "label": "s"}],
        ),
        "where='cell'",
    )
    expect_error(
        "group-overflow",
        mod(
            series=[{"kind": "line", "x": "x", "y": "y", "by": "x"}],
            data={"d": [{"x": i, "y": i} for i in range(12)]},
        ),
        "exceed",
        "palette",
    )


# ------------------------------------------------------------------- lint 面


def lints():
    empty = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}]},
        "series": [{"kind": "line", "x": "x", "y": "y", "where": {"x": 999}}],
    }
    expect_lint("empty-series", empty, "empty-series")
    suppressed = dict(empty, audit={"ignore": ["empty-series"]})
    expect_lint("empty-series-suppressed", suppressed, "empty-series", present=False)

    hexy = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y", "color": "#123456"}],
    }
    expect_lint("hex-literal", hexy, "hex-literal")
    suppressed = dict(hexy, audit={"ignore": ["hex-literal"]})
    expect_lint("hex-literal-suppressed", suppressed, "hex-literal", present=False)

    indist = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1, "p": 1.1}, {"x": 1, "y": 2, "p": 2.1}]},
        "series": [
            {"kind": "line", "id": "obs", "x": "x", "y": "y"},
            {"kind": "pred", "of": "obs", "y": "p"},
        ],
    }
    expect_lint("pred-indistinct", indist, "pred-indistinct")

    fillxy = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y", "fill": 0.2}],
    }
    expect_lint("fill-ignored", fillxy, "fill-ignored")

    scoped = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    expect_lint(
        "ignore-unscoped", dict(scoped, audit_ignore=["collide"]), "ignore-unscoped"
    )
    expect_lint(
        # rb-label-diff 是图级规则：panel audit_ignore 不得静默映射成
        # scoped 对（该规则不查 scoped），要 lint 指路去 audit.ignore
        "ignore-unscoped-rb-label-diff",
        dict(scoped, audit_ignore=["rb-label-diff"]),
        "ignore-unscoped",
    )
    expect_lint(
        "unknown-ignore",
        dict(scoped, audit={"ignore": ["bogus-rule"]}),
        "unknown-ignore",
    )
    expect_lint(
        "unknown-ignore-panel",
        dict(scoped, audit_ignore=["bogus-rule"]),
        "unknown-ignore",
    )
    expect_lint("empty-legend", dict(scoped, legend={"where": "below"}), "empty-legend")


# --------------------------------------------------------------- polar 回归

RADAR = {
    "version": 1,
    "size": [2.7, 2.5],
    "data": {
        "prof": [
            {"m": "a", "dim": "d1", "v": 0.8, "lo": 0.7, "hi": 0.9},
            {"m": "a", "dim": "d2", "v": 0.6, "lo": 0.5, "hi": 0.7},
            {"m": "a", "dim": "d3", "v": 0.7, "lo": 0.6, "hi": 0.8},
        ]
    },
    "kind": "radar",
    "dims": ["d1", "d2", "d3"],
    "series": [{"kind": "line", "from": "prof", "x": "dim", "y": "v"}],
}


def polar():
    spec = json.loads(json.dumps(RADAR))
    spec["series"] = [
        {"kind": "scatter", "from": "prof", "x": "dim", "y": "v", "s": 15},
    ]
    fig = render(spec)
    offs = np.asarray(fig.get_axes()[0].collections[0].get_offsets())
    want = np.linspace(0, 2 * np.pi, 3, endpoint=False)
    check(
        "radar-scatter-angles",
        np.allclose(offs[:, 0], want),
        f"theta={offs[:, 0]} want={want}",
    )
    plt.close(fig)

    spec = json.loads(json.dumps(RADAR))
    spec["series"] = [
        {"kind": "line", "id": "ln", "from": "prof", "x": "dim", "y": "v"},
        {"kind": "band", "of": "ln", "lo": "lo", "hi": "hi"},
        {"kind": "ref", "dir": "v", "at": "d2"},
        {"kind": "ref", "dir": "h", "at": 0.5},
        {"kind": "span", "dir": "v", "at": ["d1", "d2"]},
        {"kind": "note", "at": ["d2", 0.6], "text": "hi", "legend": False},
    ]
    fig = render(spec)
    ax = fig.get_axes()[0]
    # ref dir:v -> 角度为 d2 的辐条（xdata 两点同角）
    spokes = [
        ln
        for ln in ax.lines
        if len(ln.get_xdata()) == 2 and np.allclose(ln.get_xdata(), want[1])
    ]
    check("radar-ref-dim", bool(spokes), f"lines={[ln.get_xdata() for ln in ax.lines]}")
    plt.close(fig)

    bad = json.loads(json.dumps(RADAR))
    bad["series"] = [{"kind": "ref", "dir": "v", "at": "nope", "from": "prof"}]
    expect_error("radar-ref-baddim", bad, "not a", "data column")

    # theta 一等字段：offset 度数 -> set_theta_offset(弧度)，
    # direction 'cw' -> -1
    spec = json.loads(json.dumps(RADAR))
    spec["theta"] = {"offset": 90, "direction": "cw"}
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "radar-theta",
        np.isclose(ax.get_theta_offset(), np.pi / 2) and ax.get_theta_direction() == -1,
        f"offset={ax.get_theta_offset()} dir={ax.get_theta_direction()}",
    )
    plt.close(fig)
    spec = json.loads(json.dumps(RADAR))
    spec["theta"] = {"direction": "ccw"}
    fig = render(spec)
    check(
        "radar-theta-ccw",
        fig.get_axes()[0].get_theta_direction() == 1,
        f"dir={fig.get_axes()[0].get_theta_direction()}",
    )
    plt.close(fig)


# ------------------------------------------------------------- audit 接线


def audit_wiring():
    clipped = {
        "version": 1,
        "data": {"d": [{"x": i, "y": float(i % 3)} for i in range(20)]},
        "yaxis": {"lim": [0, 1]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    fig = render(clipped)
    probs = audit_of(fig)
    check("clip fires", any(p.startswith("data-clipped") for p in probs), f"{probs}")
    plt.close(fig)

    spec = json.loads(json.dumps(clipped))
    spec["audit_ignore"] = ["data-clipped-outside-limits"]
    fig = render(spec)
    probs = audit_of(fig)
    check(
        "panel audit_ignore suppresses",
        not any(p.startswith("data-clipped") for p in probs),
        f"{probs}",
    )
    plt.close(fig)

    spec = json.loads(json.dumps(clipped))
    spec["audit"] = {"ignore": ["data-clipped-outside-limits"]}
    fig = render(spec)
    probs = audit_of(fig)
    check(
        "figure audit.ignore suppresses",
        not any(p.startswith("data-clipped") for p in probs),
        f"{probs}",
    )
    plt.close(fig)


# ------------------------------------------------------- 行为回归（修复探针）


def regressions():
    # band/pred 子系列按值并入父网格：父 x 排序 + 子行乱序时对齐不错位
    spec = {
        "version": 1,
        "data": {
            "p": [{"x": 2, "y": 2}, {"x": 0, "y": 0}, {"x": 1, "y": 1}],
            "c": [
                {"x": 2, "lo": 20, "hi": 22},
                {"x": 0, "lo": -1, "hi": 1},
                {"x": 1, "lo": 9, "hi": 11},
            ],
        },
        "series": [
            {"kind": "line", "id": "ln", "from": "p", "x": "x", "y": "y"},
            {"kind": "band", "of": "ln", "from": "c", "lo": "lo", "hi": "hi"},
        ],
    }
    fig = render(spec)
    verts = fig.get_axes()[0].collections[0].get_paths()[0].vertices
    got = sorted({float(v[0]) for v in verts})
    check("band-join-xgrid", got == [0.0, 1.0, 2.0], f"xs={got}")
    lo_at_1 = min((float(v[1]) for v in verts if v[0] == 1.0), default=None)
    check("band-join-values", lo_at_1 == 9.0, f"lo@x=1={lo_at_1}")
    plt.close(fig)

    # 子系列声明自有 'x' 列 -> 自己的网格，不经父网格 join（x=5 非父格点）
    spec["data"]["c"] = [{"x": 0, "lo": -1, "hi": 1}, {"x": 5, "lo": 0, "hi": 2}]
    spec["series"][1] = dict(spec["series"][1], x="x")
    fig = render(spec)
    verts = fig.get_axes()[0].collections[0].get_paths()[0].vertices
    got = sorted({float(v[0]) for v in verts})
    check("band-own-x", got == [0.0, 5.0], f"xs={got}")
    plt.close(fig)

    # ref/span/note 的 by/literal at 去重：同一位置只画一次
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1, "g": "a"}, {"x": 1, "y": 2, "g": "b"}]},
        "series": [
            {"kind": "ref", "dir": "h", "at": 1.5, "by": "g"},
            {"kind": "span", "dir": "h", "at": [0.5, 1.0], "by": "g"},
            {"kind": "note", "at": [0.5, 1.0], "text": "t", "by": "g"},
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("ref-dedupe", len(ax.lines) == 1, f"lines={len(ax.lines)}")
    check("span-dedupe", len(ax.patches) == 1, f"patches={len(ax.patches)}")
    notes = [t for t in ax.texts if t.get_gid() == "fv-neutral"]
    check("note-dedupe", len(notes) == 1, f"texts={len(ax.texts)}")
    # 画到 axes 上的 overlay artist 带 fv-neutral gid（audit 豁免依据）
    check(
        "overlay-neutral-gid",
        ax.lines[0].get_gid() == "fv-neutral"
        and ax.patches[0].get_gid() == "fv-neutral",
        f"line gid={ax.lines[0].get_gid()} patch={ax.patches[0].get_gid()}",
    )
    plt.close(fig)

    # ref/span legend 句柄克隆所画 artist（ref 虚线、pred '--'+'x'）
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1, "p": 1.2}, {"x": 1, "y": 2, "p": 2.2}]},
        "series": [
            {"kind": "line", "id": "obs", "x": "x", "y": "y", "marker": "o"},
            {"kind": "pred", "id": "pd", "of": "obs", "y": "p"},
            {"kind": "ref", "id": "rf", "dir": "h", "at": 1.5},
        ],
        "legend": {
            "where": "below",
            "entries": [
                {"series": "pd", "label": "pred"},
                {"series": "rf", "label": "ref"},
            ],
        },
    }
    fig = render(spec)
    handles = fig.legends[0].legend_handles
    ls = [getattr(h, "get_linestyle", lambda: None)() for h in handles]
    mk = [getattr(h, "get_marker", lambda: None)() for h in handles]
    check("pred-handle-clone", ls[0] == "--" and mk[0] == "x", f"ls={ls} mk={mk}")
    check("ref-handle-clone", ls[1] in ("--", ":"), f"ls={ls}")
    # pred 画到 axes 上的线带 fv-neutral gid
    pred_gids = {
        ln.get_gid() for ln in fig.get_axes()[0].lines if ln.get_gid() == "fv-neutral"
    }
    check("pred-neutral-gid", "fv-neutral" in pred_gids)
    plt.close(fig)

    # 多 donut 系列的切片句柄都汇进 figure legend
    spec = {
        "version": 1,
        "kind": "donut",
        "data": {
            "d": [{"x": "a", "y": 1}, {"x": "b", "y": 2}],
            "e": [{"x": "c", "y": 3}, {"x": "dd", "y": 4}],
        },
        "series": [
            {"kind": "donut", "x": "x", "y": "y", "from": "d", "labels": "legend"},
            {"kind": "donut", "x": "x", "y": "y", "from": "e", "labels": "legend"},
        ],
        "legend": {"where": "below"},
    }
    fig = render(spec)
    labels = [t.get_text() for t in fig.legends[0].get_texts()]
    check("multi-donut-legend", labels == ["a", "b", "c", "dd"], f"{labels}")
    plt.close(fig)

    # donut labels:'legend' + legend:false + 无 figure legend -> lint
    expect_lint(
        "donut-labels-dropped",
        {
            "version": 1,
            "kind": "donut",
            "data": {"d": [{"x": "a", "y": 1}, {"x": "b", "y": 2}]},
            "series": [{"kind": "donut", "x": "x", "y": "y", "labels": "legend"}],
            "legend": False,
        },
        "empty-legend",
    )

    # layout.cells 非 panel 且非 legend 格 -> dead-cell lint；
    # 指向 legend.where='cell' 的命名格不报
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "panels": {
            "a": {"series": [{"kind": "line", "x": "x", "y": "y", "label": "s"}]},
            "b": {"series": [{"kind": "line", "x": "x", "y": "y"}]},
        },
        "layout": {"cells": [["a", "TYPO"], ["b", "L"]]},
        "legend": {"where": "cell", "cell": "L"},
    }
    fig = render(spec)
    hits = [w for w in warnings_of(fig) if w.startswith("dead-cell")]
    check("dead-cell", len(hits) == 1 and "'TYPO'" in hits[0], f"{warnings_of(fig)}")
    plt.close(fig)

    # audit_ignore 只对所在 panel 生效（scoped_ignore），其余 panel 仍报
    spec = {
        "version": 1,
        "data": {"d": [{"x": i, "y": float(i % 3)} for i in range(20)]},
        "panels": {
            "a": {
                "yaxis": {"lim": [0, 1]},
                "audit_ignore": ["data-clipped-outside-limits"],
                "series": [{"kind": "line", "x": "x", "y": "y"}],
            },
            "b": {
                "yaxis": {"lim": [0, 1]},
                "series": [{"kind": "line", "x": "x", "y": "y"}],
            },
        },
        "layout": {"cells": [["a", "b"]]},
    }
    fig = render(spec)
    kw = fig.fvspec_report["audit_kwargs"]
    ax_a = fig.get_axes()[0]
    check(
        "scoped-ignore-emitted",
        ("data-clipped-outside-limits", ax_a) in kw["scoped_ignore"],
        f"{kw}",
    )
    probs = audit_of(fig)
    clipped = [p for p in probs if p.startswith("data-clipped")]
    check(
        "scoped-ignore-other-panel",
        any("axes 1" in p for p in clipped) and not any("axes 0" in p for p in clipped),
        f"{probs}",
    )
    plt.close(fig)

    # radar dim 未命中 -> dim-unresolved lint（响亮告警而非静默丢行）
    spec = {
        "version": 1,
        "kind": "radar",
        "dims": ["a", "b", "c"],
        "data": {
            "d": [{"dim": "a", "v": 1}, {"dim": "TYPO", "v": 2}, {"dim": "c", "v": 3}]
        },
        "series": [{"kind": "line", "x": "dim", "y": "v"}],
    }
    expect_lint("dim-unresolved", spec, "dim-unresolved")

    # render() 不泄漏 rcParams（finding 16：restore purity）
    before = dict(plt.rcParams)
    fig = render(
        {
            "version": 1,
            "theme": "mono",
            "rc": {"font": "sans", "base": 12},
            "data": {"d": [{"x": 0, "y": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
        }
    )
    plt.close(fig)
    after = dict(plt.rcParams)
    diff = {k for k in before if str(before[k]) != str(after.get(k))}
    check("rc-purity", not diff, f"leaked {sorted(diff)[:8]}")


# ------------------------------------------------- 新 lint / errorbar / meta


def _errbars(ax):
    return [c for c in ax.containers if isinstance(c, ErrorbarContainer)]


def _err_segs(cont):
    return [s for lc in cont[2] for s in lc.get_segments()]


def stacked_bars():
    """stacked bar：宽度不按组数缩；正负分向累加；yerr 锚在累计尖端。"""
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"x": "a", "y": 1.0, "e": 0.1, "g": "p"},
                {"x": "b", "y": -2.0, "e": 0.2, "g": "p"},
                {"x": "c", "y": 2.0, "e": 0.1, "g": "p"},
                {"x": "a", "y": -0.5, "e": 0.1, "g": "q"},
                {"x": "b", "y": 1.5, "e": 0.1, "g": "q"},
                {"x": "c", "y": 0.5, "e": 0.1, "g": "q"},
            ]
        },
        "series": [
            {
                "kind": "bar",
                "from": "d",
                "x": "x",
                "y": "y",
                "by": "g",
                "stack": True,
                "yerr": "e",
            }
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    bars = [c for c in ax.containers if isinstance(c, BarContainer)]
    widths = {p.get_width() for c in bars for p in c.patches}
    check("stacked-width-full", widths == {0.8}, f"widths={widths}")
    geo = sorted(
        (round(p.get_y(), 3), round(p.get_height(), 3)) for c in bars for p in c.patches
    )
    # cat b: g_p=-2.0 向下、g_q=+1.5 向上 —— 都从 0 出发互不吞没；
    # cat c: g_p=2.0、g_q=0.5 同向累加 -> q 底在 2.0
    want = {(0.0, 1.0), (0.0, -2.0), (0.0, 2.0), (0.0, -0.5), (0.0, 1.5), (2.0, 0.5)}
    check("stacked-mixed-sign", set(geo) == want, f"geo={geo}")
    # cat c 的 q 组柱顶在 2.5，err=0.1 -> 竖直段 [[2,2.4],[2,2.6]]
    segs = [s for c in _errbars(ax) for s in _err_segs(c)]
    check(
        "stacked-yerr-tip",
        any(np.allclose(s, [[2.0, 2.4], [2.0, 2.6]]) for s in segs),
        f"segs={segs}",
    )
    plt.close(fig)

    # 横条：yerr 沿数值轴换成水平段
    spec["series"][0]["dir"] = "h"
    fig = render(spec)
    ax = fig.get_axes()[0]
    segs = [s for c in _errbars(ax) for s in _err_segs(c)]
    check(
        "barh-yerr-horizontal",
        bool(segs) and all(np.isclose(s[0][1], s[1][1]) for s in segs),
        f"segs={segs[:2]}",
    )
    plt.close(fig)


def errbars():
    """errorbar 通道：line/scatter/bar 的 sym/asym/列/标量四种形态。"""
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1.0, "e": 0.2}, {"x": 1, "y": 2.0, "e": 0.3}]},
        "series": [{"kind": "line", "x": "x", "y": "y", "yerr": "e"}],
    }
    fig = render(spec)
    errs = _errbars(fig.get_axes()[0])
    check("line-yerr", len(errs) == 1, f"{len(errs)}")
    check(
        "errbar-neutral-gid",
        bool(errs) and all(ln.get_gid() == "fv-neutral" for ln in errs[0][1]),
        f"cap gids={[ln.get_gid() for ln in errs[0][1]] if errs else []}",
    )
    plt.close(fig)

    # scatter 双侧不等误差 + 缺值行锁步过滤
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"x": 0, "y": 1.0, "lo": 0.2, "hi": 0.5},
                {"x": 1, "y": None, "lo": 0.1, "hi": 0.1},
                {"x": 2, "y": 3.0, "lo": 0.4, "hi": 0.1},
            ]
        },
        "series": [
            {"kind": "scatter", "x": "x", "y": "y", "yerr": {"lo": "lo", "hi": "hi"}}
        ],
        "meta": {"ledger": "l", "caption": "c"},
        "audit": {"ignore": ["missing-rows"]},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    offs = np.asarray(ax.collections[0].get_offsets())
    check(
        "scatter-drop-missing",
        len(offs) == 2 and np.allclose(offs[:, 0], [0, 2]),
        f"offs={offs.tolist()}",
    )
    segs = [s for c in _errbars(ax) for s in _err_segs(c)]
    check(
        "scatter-yerr-asym",
        any(np.allclose(s, [[0.0, 0.8], [0.0, 1.5]]) for s in segs),
        f"segs={segs}",
    )
    plt.close(fig)

    expect_lint(
        "missing-rows",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}, {"x": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
        },
        "missing-rows",
    )
    expect_lint(
        "missing-rows-suppressed",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}, {"x": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
            "audit_ignore": ["missing-rows"],
        },
        "missing-rows",
        present=False,
    )

    # errorbar spec 的响亮报错面
    expect_error(
        "err-asym-missing-hi",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1, "e": 0.1}]},
            "series": [{"kind": "line", "x": "x", "y": "y", "yerr": {"lo": "e"}}],
        },
        "needs both",
    )
    expect_error(
        "err-on-band",
        {
            "version": 1,
            "data": {
                "p": [{"x": 0, "y": 0}],
                "c": [{"x": 0, "lo": 0, "hi": 1, "e": 0.1}],
            },
            "series": [
                {"kind": "line", "id": "ln", "from": "p", "x": "x", "y": "y"},
                {
                    "kind": "band",
                    "of": "ln",
                    "from": "c",
                    "lo": "lo",
                    "hi": "hi",
                    "yerr": "e",
                },
            ],
        },
        "unknown keys",
    )
    expect_error(
        "radar-yerr",
        {
            "version": 1,
            "kind": "radar",
            "dims": ["a", "b"],
            "data": {
                "d": [{"dim": "a", "v": 1, "e": 0.1}, {"dim": "b", "v": 2, "e": 0.2}]
            },
            "series": [{"kind": "line", "x": "dim", "y": "v", "yerr": "e"}],
        },
        "unsupported on radar",
    )
    expect_lint(
        "bar-xerr",
        {
            "version": 1,
            "data": {"d": [{"x": "a", "y": 1, "e": 0.1}]},
            "series": [{"kind": "bar", "x": "x", "y": "y", "xerr": "e"}],
        },
        "axis-ignored",
    )


def new_lints():
    """新 lint 面：触发 + 抑制各一例。"""
    # unknown-field：by/err 引用了整列缺失的字段（where 字段归
    # where-field-missing——见下）
    uf = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1, "score": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y", "by": "scor"}],
    }
    fig = render(uf)
    hits = [w for w in warnings_of(fig) if w.startswith("unknown-field")]
    check(
        "unknown-field-hint",
        bool(hits) and "did you mean 'score'" in hits[0],
        f"{warnings_of(fig)}",
    )
    plt.close(fig)
    expect_lint(
        "unknown-field-suppressed",
        dict(uf, audit_ignore=["unknown-field"]),
        "unknown-field",
        present=False,
    )

    # where-field-missing：where 引用字段整列缺席——点名系列与来源
    # （series where vs panel.where 下发），与 unknown-field 分开抑制
    wf = {
        "version": 1,
        "data": {
            "d": [{"x": 0, "y": 1, "split": "t"}],
            "s": [{"a": 0, "b": 1, "y": 2.0, "p": 0.01}],
        },
        "where": {"split": "t"},
        "meta": {"ledger": "l", "caption": "c"},
        "series": [
            {"kind": "line", "from": "d", "x": "x", "y": "y"},
            {"kind": "sig", "from": "s", "id": "sg"},
        ],
    }
    fig = render(wf)
    hits = [w for w in warnings_of(fig) if w.startswith("where-field-missing")]
    check(
        "where-field-missing-panel",
        len(hits) == 1
        and "sg" in hits[0]
        and "'split'" in hits[0]
        and "panel.where" in hits[0],
        f"{warnings_of(fig)}",
    )
    plt.close(fig)
    expect_lint(
        "where-field-missing-suppressed",
        dict(wf, audit_ignore=["where-field-missing"]),
        "where-field-missing",
        present=False,
    )
    # series 自带 where（非 panel 下发）→ 来源词是 'where'
    fig = render(
        dict(
            wf,
            series=[
                dict(wf["series"][0], where={"scor": 1}),
                wf["series"][1],
            ],
        )
    )
    hits = [w for w in warnings_of(fig) if w.startswith("where-field-missing")]
    check(
        "where-field-missing-series",
        any("'scor'" in w and "panel.where" not in w for w in hits)
        and any("sg" in w for w in hits),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)

    # axis-ignored：tick_labels 无 ticks 锚点 / categorical x 的 ticks
    tl = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
        "xaxis": {"tick_labels": ["a", "b"]},
    }
    expect_lint("axis-ignored-tl", tl, "axis-ignored")
    expect_lint(
        "axis-ignored-suppressed",
        dict(tl, audit_ignore=["axis-ignored"]),
        "axis-ignored",
        present=False,
    )
    catx = {
        "version": 1,
        "data": {"d": [{"x": "a", "y": 1}, {"x": "b", "y": 2}]},
        "series": [{"kind": "bar", "x": "x", "y": "y"}],
        "xaxis": {"ticks": [0, 1], "tick_labels": ["A", "B"], "lim": [-0.6, 1.6]},
    }
    fig = render(catx)
    check(
        "axis-ignored-catx",
        any(w.startswith("axis-ignored") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    # lim 在 categorical x 上照常生效（按类别序号定限）
    check(
        "catx-lim-honored",
        tuple(fig.get_axes()[0].get_xlim()) == (-0.6, 1.6),
        f"xlim={fig.get_axes()[0].get_xlim()}",
    )
    plt.close(fig)

    # log-tick-unlabeled：log 轴显式 ticks 含非 10 幂且无 tick_labels
    ltu = {
        "version": 1,
        "data": {"d": [{"x": 1, "y": 1}, {"x": 10, "y": 2}, {"x": 50, "y": 3}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
        "xaxis": {"scale": "log", "ticks": [1, 2, 5, 10, 50], "lim": [1, 60]},
    }
    expect_lint("log-tick-unlabeled", ltu, "log-tick-unlabeled")
    expect_lint(
        "log-tick-unlabeled-suppressed",
        dict(ltu, audit_ignore=["log-tick-unlabeled"]),
        "log-tick-unlabeled",
        present=False,
    )
    # 给了 tick_labels（含 'ticks' 直通）或 ticks 全 10 幂都不报
    expect_lint(
        "log-tick-labeled-quiet",
        dict(
            ltu,
            xaxis={
                "scale": "log",
                "ticks": [1, 2, 5, 10, 50],
                "tick_labels": ["1", "2", "5", "10", "50"],
            },
        ),
        "log-tick-unlabeled",
        present=False,
    )
    expect_lint(
        "log-tick-ticks-passthrough-quiet",
        dict(
            ltu,
            xaxis={"scale": "log", "ticks": [1, 2, 5, 10, 50], "tick_labels": "ticks"},
        ),
        "log-tick-unlabeled",
        present=False,
    )
    expect_lint(
        "log-tick-powers-quiet",
        dict(ltu, xaxis={"scale": "log", "ticks": [0.1, 1, 10, 100]}),
        "log-tick-unlabeled",
        present=False,
    )

    # y2：{} 空配置建 twin + 两条 lint；带 label 则只有…不，label 齐则无 lint
    y2 = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y", "axis": "y2"}],
        "y2": {},
    }
    fig = render(y2)
    warns = warnings_of(fig)
    check("empty-y2", any(w.startswith("empty-y2") for w in warns), f"{warns}")
    check(
        "twin-axis-unlabeled",
        any(w.startswith("twin-axis-unlabeled") for w in warns),
        f"{warns}",
    )
    check("y2-twin-created", len(fig.get_axes()) == 2, f"{len(fig.get_axes())}")
    plt.close(fig)
    expect_lint(
        "empty-y2-suppressed",
        dict(y2, audit_ignore=["empty-y2", "twin-axis-unlabeled"]),
        "empty-y2",
        present=False,
    )
    fig = render(dict(y2, y2={"label": "rpm"}))
    warns = warnings_of(fig)
    check(
        "y2-labeled-quiet",
        not any(w.startswith(("empty-y2", "twin-axis-unlabeled")) for w in warns),
        f"{warns}",
    )
    plt.close(fig)
    expect_error("y2-nonstr", dict(y2, y2="rpm"), "must be an object")

    # meta：缺失告警、写齐不报、类型校验
    bare = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    expect_lint("missing-ledger", bare, "missing-ledger")
    expect_lint("missing-caption", bare, "missing-caption")
    expect_lint(
        "meta-lints-suppressed",
        dict(bare, audit={"ignore": ["missing-ledger", "missing-caption"]}),
        "missing-ledger",
        present=False,
    )
    fig = render(dict(bare, meta={"ledger": "l", "caption": "c"}))
    warns = warnings_of(fig)
    check(
        "meta-lints-quiet",
        not any(w.startswith(("missing-ledger", "missing-caption")) for w in warns),
        f"{warns}",
    )
    plt.close(fig)
    expect_error(
        "meta-ledger-int",
        dict(bare, meta={"ledger": 3}),
        "meta.ledger must be a string",
    )
    expect_error(
        "meta-usermeta-list",
        dict(bare, meta={"usermeta": [1]}),
        "meta.usermeta must be an object",
    )
    expect_error(
        "meta-bad-key",
        dict(bare, meta={"bogus": 1}),
        "unknown keys",
    )

    # tight-bbox：声明 size 且显式 bbox:'tight' 才报；缺省（所有 size 形态
    # 统一 null 不重裁）/bbox:null/无 size 不报
    with tempfile.TemporaryDirectory() as td:
        tight = dict(
            bare,
            size="half",
            meta={"ledger": "l", "caption": "c"},
            output={"path": "f.png", "bbox": "tight"},
        )
        fig = fvspec.render(tight, base_dir=td)
        check(
            "tight-bbox",
            any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)
        fig = fvspec.render(
            dict(tight, output={"path": "f.png"}),
            base_dir=td,
        )
        check(
            "tight-bbox-default",
            not any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)
        fig = fvspec.render(
            dict(tight, output={"path": "f.png", "bbox": None}),
            base_dir=td,
        )
        check(
            "tight-bbox-null",
            not any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)
        nosize = dict(tight)
        nosize.pop("size")
        fig = fvspec.render(nosize, base_dir=td)
        check(
            "tight-bbox-nosize",
            not any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)

    # 聚合：一个 spec 的多条 lint 一次性全部报出
    agg = {
        "version": 1,
        "size": "half",
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1}]},
        "series": [
            {
                "kind": "line",
                "x": "x",
                "y": "y",
                "where": {"bogus": 3},
                "by": "bogus2",
            }
        ],
        "output": {"path": "f.png", "bbox": "tight"},
    }
    with tempfile.TemporaryDirectory() as td:
        fig = fvspec.render(agg, base_dir=td)
        warns = warnings_of(fig)
        got = {w.split(":")[0] for w in warns}
        want = {
            "missing-ledger",
            "missing-caption",
            "unknown-field",
            "where-field-missing",
            "empty-series",
            "tight-bbox",
        }
        check("lint-aggregate", want <= got, f"got={sorted(got)}")
        plt.close(fig)

    # did-you-mean：未知键/枚举值的 difflib 提示
    expect_error(
        "hint-series-key",
        dict(bare, series=[{"kind": "line", "x": "x", "y": "y", "colour": "vteal"}]),
        "did you mean 'color'",
    )
    expect_error(
        "hint-kind",
        dict(bare, series=[{"kind": "lin", "x": "x", "y": "y"}]),
        "did you mean 'line'",
    )
    expect_error(
        "hint-theme",
        dict(bare, theme="papers"),
        "did you mean 'paper'",
    )
    expect_error(
        "hint-legend-where",
        dict(bare, legend={"where": "belowe"}),
        "did you mean 'below'",
    )

    # csv 缺失 -> SpecError 而非裸 traceback
    expect_error(
        "csv-missing",
        dict(bare, data={"d": {"csv": "no_such_file.csv"}}),
        "cannot read",
    )

    # dodge-single-group：by 扇出但逐 x 槽位至多一组有行——柱宽仍按组
    # 数缩窄且逐槽偏离槽位中心
    dg = {
        "version": 1,
        "data": {
            "d": [
                {"x": "a", "y": 1, "g": "g1"},
                {"x": "b", "y": 2, "g": "g2"},
                {"x": "c", "y": 3, "g": "g3"},
            ]
        },
        "series": [{"kind": "bar", "x": "x", "y": "y", "by": "g"}],
    }
    expect_lint("dodge-single-group", dg, "dodge-single-group")
    expect_lint(
        "dodge-single-group-suppressed",
        dict(dg, audit_ignore=["dodge-single-group"]),
        "dodge-single-group",
        present=False,
    )
    # by==x 字段误用：lint 文案点名
    dgx = dict(dg, series=[{"kind": "bar", "x": "x", "y": "y", "by": "x"}])
    fig = render(dgx)
    hits = [w for w in warnings_of(fig) if w.startswith("dodge-single-group")]
    check(
        "dodge-by-x-misuse-hint",
        bool(hits) and "misuse" in hits[0],
        f"{warnings_of(fig)}",
    )
    plt.close(fig)
    # 真 dodge（槽位内有多组配对）不报
    dd = {
        "version": 1,
        "data": {
            "d": [
                {"x": "a", "y": 1, "g": "g1"},
                {"x": "a", "y": 2, "g": "g2"},
                {"x": "b", "y": 1, "g": "g1"},
                {"x": "b", "y": 3, "g": "g2"},
            ]
        },
        "series": [{"kind": "bar", "x": "x", "y": "y", "by": "g"}],
    }
    expect_lint("dodge-paired-quiet", dd, "dodge-single-group", present=False)


def meta_and_output():
    """meta.caption 落位、图例让位、产物 metadata 溯源、pgf 输出。"""
    base = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1, "g": "a"}, {"x": 1, "y": 2, "g": "b"}]},
        "series": [
            {
                "kind": "line",
                "from": "d",
                "x": "x",
                "y": "y",
                "by": "g",
                "label": {"a": "A", "b": "B"},
            }
        ],
        "meta": {"ledger": "l", "caption": "ident line"},
        "legend": {"where": "below"},
    }
    fig = render(base)
    check(
        "caption-drawn",
        any(t.get_text() == "ident line" for t in fig.texts),
        f"{[t.get_text() for t in fig.texts]}",
    )
    # caption 在画布内 + 图例被 cap_frac 抬成点锚（非整图 bbox）
    anchor = fig.legends[0].get_bbox_to_anchor().bounds
    check(
        "caption-lifts-legend",
        anchor[2] == 0 and anchor[3] == 0 and anchor[1] > 0,
        f"{anchor}",
    )
    probs = audit_of(fig)
    check(
        "caption-size-ok",
        not any(p.startswith("text-too-small") and "ident line" in p for p in probs),
        f"{probs}",
    )
    plt.close(fig)

    # 无 caption：legend 锚回整图
    fig = render(dict(base, meta={"ledger": "l"}))
    anchor = fig.legends[0].get_bbox_to_anchor().bounds
    check("no-caption-no-lift", anchor[2] > 0 and anchor[3] > 0, f"{anchor}")
    plt.close(fig)

    # provenance：PNG metadata 带 spec 指纹与生成器
    spec = dict(base, output={"path": "f.png"})
    with tempfile.TemporaryDirectory() as td:
        fig = fvspec.render(spec, base_dir=td)
        blob = (Path(td) / "f.png").read_bytes()
        check(
            "provenance-png",
            b"fvspec-spec-sha256:" in blob and b"figure-viz fvspec" in blob,
            "sha256/Creator missing from PNG text chunks",
        )
        plt.close(fig)

        # usermeta 透传（png 任意键）
        spec2 = dict(
            base,
            meta={"ledger": "l", "caption": "c", "usermeta": {"project": "fvproj"}},
            output={"path": "g.png"},
        )
        fig = fvspec.render(spec2, base_dir=td)
        blob = (Path(td) / "g.png").read_bytes()
        check("usermeta-png", b"project" in blob and b"fvproj" in blob)
        plt.close(fig)

        # pdf/svg 白名单：Title 收、BadKey 丢并 lint
        spec3 = dict(
            base,
            meta={
                "ledger": "l",
                "caption": "c",
                "usermeta": {"Title": "T", "BadKey": "x"},
            },
            output={"path": "h.pdf"},
        )
        fig = fvspec.render(spec3, base_dir=td)
        warns = warnings_of(fig)
        check(
            "meta-key-dropped",
            any(w.startswith("meta-key-dropped") and "BadKey" in w for w in warns),
            f"{warns}",
        )
        check("pdf-saved", (Path(td) / "h.pdf").is_file())
        plt.close(fig)

        # 保留键：Creator/Keywords 是溯源指纹，三格式统一 provenance 赢，
        # 被盖的 usermeta 键走 meta-key-reserved lint
        spec5 = dict(
            base,
            meta={
                "ledger": "l",
                "caption": "c",
                "usermeta": {"Creator": "ZZZCreator", "Keywords": "ZZZKeywords"},
            },
            output={"path": "r.png"},
        )
        fig = fvspec.render(spec5, base_dir=td)
        blob = (Path(td) / "r.png").read_bytes()
        warns = warnings_of(fig)
        check(
            "meta-key-reserved",
            any(
                w.startswith("meta-key-reserved") and "Creator" in w and "Keywords" in w
                for w in warns
            ),
            f"{warns}",
        )
        check(
            "provenance-wins-png",
            b"figure-viz fvspec" in blob and b"ZZZCreator" not in blob,
            "usermeta Creator shadowed the provenance fingerprint",
        )
        plt.close(fig)

        # pdf 路径同样 provenance 赢（Keywords 在白名单内也照样被盖）
        spec6 = dict(spec5, output={"path": "r.pdf"})
        fig = fvspec.render(spec6, base_dir=td)
        blob = (Path(td) / "r.pdf").read_bytes()
        warns = warnings_of(fig)
        check(
            "meta-key-reserved-pdf",
            any(w.startswith("meta-key-reserved") and "Keywords" in w for w in warns),
            f"{warns}",
        )
        check(
            "provenance-wins-pdf",
            b"fvspec-spec-sha256:" in blob and b"ZZZKeywords" not in blob,
            "usermeta Keywords shadowed the provenance fingerprint",
        )
        plt.close(fig)

        # pgf：后端可用时落盘；不可用时跳过（不强依赖本地 LaTeX）
        spec4 = dict(base, output={"path": "k.pgf"})
        try:
            fig = fvspec.render(spec4, base_dir=td)
            pgf = Path(td) / "k.pgf"
            check(
                "pgf-saved",
                pgf.is_file() and pgf.stat().st_size > 0,
                "pgf not written",
            )
            plt.close(fig)
        except Exception as e:  # backend 不可用 -> skip
            check("pgf-saved", True, f"skipped: {e}")


def _dist_rows(n=90):
    """确定性双峰数值列 + 两组标签；首行即 'a' -> 组序恒为 ['a','b']。"""
    rows = []
    for i in range(n):
        peak = -1.2 if i % 2 else 1.2
        v = peak + ((i * 37) % 40) / 20.0 - 1.0
        rows.append({"v": round(v, 4), "g": "a" if (i + 2) % 3 else "b"})
    return rows


def dist_kinds():
    """hist/ecdf/box/violin：渲染 + audit 干净 + 关键几何断言。"""
    meta = {"ledger": "l", "caption": "c"}
    # --- hist：by 双组重叠，默认 alpha=.55 + vink 描边，legend below ---
    spec = {
        "version": 1,
        "data": {"d": _dist_rows()},
        "xaxis": {"label": "value"},
        "yaxis": {"label": "count"},
        "series": [
            {
                "kind": "hist",
                "from": "d",
                "x": "v",
                "by": "g",
                "bins": 14,
                "label": {"a": "arm A", "b": "arm B"},
            }
        ],
        "meta": meta,
        "legend": {"where": "below"},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    bars = [c for c in ax.containers if isinstance(c, BarContainer)]
    check("hist-groups", len(bars) == 2, f"{len(bars)}")
    p0 = bars[0].patches[0]
    check(
        "hist-alpha",
        abs(p0.get_facecolor()[3] - 0.55) < 1e-6,
        f"alpha={p0.get_facecolor()[3]}",
    )
    ink = (0x3A / 255, 0x3F / 255, 0x45 / 255)
    check(
        "hist-edge-vink",
        np.allclose(p0.get_edgecolor()[:3], ink, atol=1e-3),
        f"edge={p0.get_edgecolor()}",
    )
    check("hist-bins", len(bars[0].patches) == 14, f"{len(bars[0].patches)}")
    probs, warns = audit_of(fig), warnings_of(fig)
    check("hist-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # --- ecdf：右连续阶梯，起笔 0 收笔 1 ---
    spec = {
        "version": 1,
        "data": {"d": _dist_rows(40)},
        "xaxis": {"label": "value"},
        "yaxis": {"label": "$F(x)$"},
        "series": [{"kind": "ecdf", "from": "d", "x": "v", "label": "ecdf"}],
        "meta": meta,
        "legend": {"loc": "lower right"},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    ys = ax.lines[0].get_ydata()
    xs = ax.lines[0].get_xdata()
    check(
        "ecdf-bounds",
        ys[0] == 0.0 and ys[-1] == 1.0 and np.all(np.diff(ys) >= 0),
        f"y0={ys[0]} yN={ys[-1]}",
    )
    check("ecdf-sorted", np.all(np.diff(xs) >= 0), "xs not sorted")
    probs, warns = audit_of(fig), warnings_of(fig)
    check("ecdf-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # --- box：三组箱体族色 fill + 结构件全 fv-neutral + 组名刻度 ---
    spec = {
        "version": 1,
        "data": {"d": _dist_rows()},
        "yaxis": {"label": "score"},
        "series": [{"kind": "box", "from": "d", "y": "v", "by": "g"}],
        "meta": meta,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("box-patches", len(ax.patches) == 2, f"{len(ax.patches)}")
    check(
        "box-neutral-lines",
        bool(ax.lines) and all(ln.get_gid() == "fv-neutral" for ln in ax.lines),
        f"gids={ {ln.get_gid() for ln in ax.lines} }",
    )
    check(
        "box-ticklabels",
        [t.get_text() for t in ax.get_xticklabels()] == ["a", "b"],
        f"{[t.get_text() for t in ax.get_xticklabels()]}",
    )
    probs, warns = audit_of(fig), warnings_of(fig)
    check("box-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # box positions/labels：显式槽位 + label 覆写刻度文本
    spec["series"][0]["positions"] = [1, 3]
    spec["series"][0]["label"] = {"a": "arm A", "b": "arm B"}
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "box-positions",
        list(ax.get_xticks()) == [1, 3]
        and [t.get_text() for t in ax.get_xticklabels()] == ["arm A", "arm B"],
        f"ticks={ax.get_xticks()} labels={[t.get_text() for t in ax.get_xticklabels()]}",
    )
    plt.close(fig)

    # --- violin：inner points + 全部件 fv-neutral ---
    spec = {
        "version": 1,
        "data": {"d": _dist_rows()},
        "yaxis": {"label": "score"},
        "series": [
            {"kind": "violin", "from": "d", "y": "v", "by": "g", "inner": "points"}
        ],
        "meta": meta,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("violin-bodies", len(ax.collections) >= 3, f"{len(ax.collections)}")
    check(
        "violin-neutral",
        all(c.get_gid() == "fv-neutral" for c in ax.collections),
        f"gids={ {c.get_gid() for c in ax.collections} }",
    )
    # inner 散点：PathCollection offsets 行数 = 组内点数
    from matplotlib.collections import PathCollection

    scats = [c for c in ax.collections if isinstance(c, PathCollection)]
    check(
        "violin-inner-pts",
        len(scats) == 2 and sum(len(c.get_offsets()) for c in scats) == 90,
        f"{[len(c.get_offsets()) for c in scats]}",
    )
    probs, warns = audit_of(fig), warnings_of(fig)
    check("violin-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)


def dist_errors():
    """分布图族 SpecError 面。"""
    base = {
        "version": 1,
        "data": {"d": _dist_rows(30)},
        "series": [{"kind": "hist", "x": "v"}],
    }

    def mod(**kw):
        s = json.loads(json.dumps(base))
        s.update(kw)
        return s

    expect_error(
        "hist-missing-x",
        mod(series=[{"kind": "hist"}]),
        "missing required 'x'",
    )
    expect_error(
        "box-missing-y",
        mod(series=[{"kind": "box"}]),
        "missing required 'y'",
    )
    expect_error(
        "hist-bins-float",
        mod(series=[{"kind": "hist", "x": "v", "bins": 2.5}]),
        "bad bins",
    )
    expect_error(
        "hist-bins-name",
        mod(series=[{"kind": "hist", "x": "v", "bins": "nope"}]),
        "bad bins",
    )
    expect_error(
        "hist-range",
        mod(series=[{"kind": "hist", "x": "v", "range": [3, 1]}]),
        "range must be",
    )
    expect_error(
        "box-positions-len",
        mod(series=[{"kind": "box", "y": "v", "by": "g", "positions": [1, 2, 3]}]),
        "positions must be",
    )
    expect_error(
        "violin-widths-len",
        mod(series=[{"kind": "violin", "y": "v", "by": "g", "widths": [0.3]}]),
        "widths must be",
    )
    expect_error(
        "violin-inner",
        mod(series=[{"kind": "violin", "y": "v", "inner": "quartile"}]),
        "inner must be",
    )
    expect_error(
        "violin-on-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            data={"d": [{"dim": "a", "v": 1}, {"dim": "b", "v": 2}]},
            series=[{"kind": "violin", "y": "v"}],
        ),
        "not allowed in",
        "panel",
    )
    expect_error(
        "ecdf-nonnumeric",
        mod(
            data={"d": [{"v": "hi"}, {"v": "lo"}]},
            series=[{"kind": "ecdf", "x": "v"}],
        ),
        "non-numeric",
    )
    expect_error(
        "ecdf-bad-key",
        mod(series=[{"kind": "ecdf", "x": "v", "y": "v"}]),
        "unknown keys",
    )


def dist_lints():
    """新语义 lint：每条一个触发例 + 豁免例。"""
    # markers-on-dense-line：60 点带 marker 触发；同数据无 marker 不触发
    dense = {
        "version": 1,
        "data": {"d": [{"x": i, "y": float((i * 7) % 11)} for i in range(60)]},
        "series": [{"kind": "line", "x": "x", "y": "y", "marker": "o"}],
    }
    expect_lint("markers-on-dense", dense, "markers-on-dense-line")
    nomarker = json.loads(json.dumps(dense))
    nomarker["series"][0].pop("marker")
    expect_lint("markers-none-quiet", nomarker, "markers-on-dense-line", present=False)
    expect_lint(
        "markers-suppressed",
        dict(dense, audit_ignore=["markers-on-dense-line"]),
        "markers-on-dense-line",
        present=False,
    )

    # tick-density：full 宽（5.5in）+ xlim [0,40] → AutoLocator 给 9 个
    # 刻度触发；half/third 宽下 mpl 的 nbins="auto" 会把刻度自适应减到
    # ~5 个，本来就稀，不告警；显式 ticks 豁免检测
    many = {
        "version": 1,
        "size": "full",
        "data": {"d": [{"x": i, "y": float(i % 3)} for i in range(41)]},
        "xaxis": {"lim": [0, 40]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    expect_lint("tick-density-x", many, "tick-density")
    sparse = dict(many, xaxis={"ticks": [0, 20, 40]})
    fig = render(sparse)
    check(
        "tick-density-explicit-quiet",
        not any(w.startswith("tick-density") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)
    expect_lint(
        "tick-density-fig-suppressed",
        dict(many, audit={"ignore": ["tick-density"]}),
        "tick-density",
        present=False,
    )

    # tick-density 类别轴：13 类 bar 触发（>12）
    cats = {
        "version": 1,
        "data": {"d": [{"x": f"c{i}", "y": float(i)} for i in range(13)]},
        "series": [{"kind": "bar", "x": "x", "y": "y"}],
    }
    expect_lint("tick-density-cat", cats, "tick-density")

    # bar-count：同一 spec 触发（13 根未分组柱）；分组后不触发
    expect_lint("bar-count", cats, "bar-count")
    grouped = json.loads(json.dumps(cats))
    for i, r in enumerate(grouped["data"]["d"]):
        r["g"] = "p" if i % 2 else "q"
    grouped["series"][0]["by"] = "g"
    expect_lint("bar-count-grouped-quiet", grouped, "bar-count", present=False)

    # hist-bin-sanity：bins=3 与 bins=250 两端都触发
    hb = {
        "version": 1,
        "data": {"d": _dist_rows(60)},
        "series": [{"kind": "hist", "x": "v", "bins": 3}],
    }
    expect_lint("hist-bins-low", hb, "hist-bin-sanity")
    expect_lint(
        "hist-bins-high",
        dict(hb, series=[{"kind": "hist", "x": "v", "bins": 250}]),
        "hist-bin-sanity",
    )
    expect_lint(
        "hist-bins-auto-quiet",
        dict(hb, series=[{"kind": "hist", "x": "v"}]),
        "hist-bin-sanity",
        present=False,
    )

    # violin-min-points：5 点组触发；>=10 点不触发
    few = {
        "version": 1,
        "data": {"d": _dist_rows(10)},
        "series": [{"kind": "violin", "y": "v", "by": "g"}],
    }
    expect_lint("violin-min-points", few, "violin-min-points")
    expect_lint(
        "violin-min-points-suppressed",
        dict(few, audit_ignore=["violin-min-points"]),
        "violin-min-points",
        present=False,
    )
    enough = dict(few, data={"d": _dist_rows(60)})
    expect_lint("violin-enough-quiet", enough, "violin-min-points", present=False)


def _add_inset(ax, ctx):
    iax = ax.inset_axes([0.55, 0.55, 0.4, 0.35])
    iax.plot([0, 1, 2], [5, 9, 4])
    iax.set_ylim(0, 1)


def scoped_ignore_children():
    """audit_ignore 覆盖 child_axes（inset 不在 fig.get_axes() 里）。"""
    spec = {
        "version": 1,
        "data": {"d": [{"x": i, "y": float(i % 3)} for i in range(20)]},
        "panels": {
            "a": {
                "yaxis": {"lim": [0, 1]},
                "audit_ignore": ["data-clipped-outside-limits"],
                "series": [{"kind": "line", "x": "x", "y": "y"}],
                "raw": _add_inset,
            },
        },
    }
    fig = render(spec)
    scoped = fig.fvspec_report["audit_kwargs"]["scoped_ignore"]
    ax = fig.get_axes()[0]
    inset = ax.child_axes[0]
    check(
        "scoped-ignore-child-axes",
        ("data-clipped-outside-limits", inset) in scoped,
        f"{scoped}",
    )
    probs = audit_of(fig)
    clipped = [p for p in probs if p.startswith("data-clipped")]
    check("scoped-ignore-inset-effective", not clipped, f"{probs}")
    plt.close(fig)


def _add_inset_grandchild(ax, ctx):
    iax = ax.inset_axes([0.55, 0.55, 0.4, 0.35])
    gg = iax.inset_axes([0.2, 0.2, 0.5, 0.5])
    gg.plot([0, 1, 2], [5, 9, 4])
    gg.set_ylim(0, 1)


def scoped_ignore_grandchildren():
    """audit_ignore 豁免半径含孙轴：inset 上再 inset/secondary 的后代轴。"""
    spec = {
        "version": 1,
        "data": {"d": [{"x": i, "y": float(i % 3)} for i in range(20)]},
        "panels": {
            "a": {
                "yaxis": {"lim": [0, 1]},
                "audit_ignore": ["data-clipped-outside-limits"],
                "series": [{"kind": "line", "x": "x", "y": "y"}],
                "raw": _add_inset_grandchild,
            },
        },
    }
    fig = render(spec)
    scoped = fig.fvspec_report["audit_kwargs"]["scoped_ignore"]
    ax = fig.get_axes()[0]
    grandchild = ax.child_axes[0].child_axes[0]
    check(
        "scoped-ignore-grandchild-axes",
        ("data-clipped-outside-limits", grandchild) in scoped,
        f"{scoped}",
    )
    probs = audit_of(fig)
    clipped = [p for p in probs if p.startswith("data-clipped")]
    check("scoped-ignore-grandchild-effective", not clipped, f"{probs}")
    plt.close(fig)


def donut_missing():
    """donut：缺值行落片（pie 不吃 None），missing-rows 已先行告警。"""
    spec = {
        "version": 1,
        "kind": "donut",
        "data": {"d": [{"x": "a", "y": 1}, {"x": "b", "y": None}, {"x": "c", "y": 3}]},
        "series": [{"kind": "donut", "x": "x", "y": "y"}],
        "meta": {"ledger": "l", "caption": "c"},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("donut-drop-none", len(ax.patches) == 2, f"{len(ax.patches)}")
    check(
        "donut-missing-rows",
        any(w.startswith("missing-rows") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)


def donut_pct_ink():
    """donut autopct 字色按扇区底色取 WCAG 对比高者：深扇区白字、
    浅扇区主题墨色（vteal/vcoral 深、vorange 浅——paper 序前三色）。"""
    spec = {
        "version": 1,
        "kind": "donut",
        "data": {"d": [{"x": "a", "y": 1}, {"x": "b", "y": 1}, {"x": "c", "y": 1}]},
        "series": [{"kind": "donut", "x": "x", "y": "y", "pct": "%d", "labels": False}],
        "meta": {"ledger": "l", "caption": "c"},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    # labels:False 仍会留空壳 Text——按非空文本过滤出 autopct 标签
    got = [t.get_color() for t in ax.texts if t.get_text().strip()]
    want = ["white", "#3A3F45", "white"]  # vteal / vorange / vcoral
    check("donut-pct-ink", got == want, f"colors={got}")
    plt.close(fig)


# ------------------------------------------------------------- CLI 错误面


def cli():
    import subprocess

    with tempfile.TemporaryDirectory() as td:
        for name, payload in [("null", "null"), ("list", "[1, 2]")]:
            p = Path(td) / f"{name}.json"
            p.write_text(payload)
            r = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_DIR / "scripts" / "render_mpl.py"),
                    str(p),
                    "--no-audit",
                ],
                capture_output=True,
                text=True,
            )
            check(
                f"cli-non-dict-{name}",
                r.returncode == 2 and "spec error" in r.stderr,
                f"rc={r.returncode} stderr={r.stderr[:120]}",
            )


# ------------------------------------------------------------------ 输出落盘


def output_save():
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
        "output": {"path": "out/fig.png", "formats": ["png", "pdf"]},
    }
    with tempfile.TemporaryDirectory() as td:
        fig = fvspec.render(spec, base_dir=td)
        saved = fig.fvspec_report["saved"]
        names = {p.name for p in saved}
        check("save formats", names == {"fig.png", "fig.pdf"}, f"{names}")
        check("save exists", all(p.is_file() for p in saved))
        plt.close(fig)


def _heat_rows():
    """3x3 confusion 长表：x=predicted、y=actual（字符类，首见序/排序皆可）。"""
    mat = {"svm": [12, 2, 1], "rf": [3, 9, 2], "mlp": [1, 4, 15]}
    return [
        {"x": x, "y": y, "z": mat[y][i]}
        for y in mat
        for i, x in enumerate(["svm", "rf", "mlp"])
    ]


def heat_kinds():
    """heat：长表透视与 matrix 直给两种形态 + cbar/annotate/norm 行为。"""
    meta = {"ledger": "l", "caption": "c"}
    # --- 长表 {x,y,z}：透视成矩阵、行 0 在顶、cbar 轴自动加、audit 干净 ---
    spec = {
        "version": 1,
        "data": {"d": _heat_rows()},
        "xaxis": {"label": "predicted"},
        "yaxis": {"label": "actual"},
        "series": [{"kind": "heat", "from": "d", "x": "x", "y": "y", "z": "z"}],
        "meta": meta,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    meshes = [c for c in ax.collections if c.get_array() is not None]
    check("heat-mesh", len(meshes) == 1, f"{len(meshes)}")
    arr = meshes[0].get_array()
    check("heat-cells", arr.size == 9, f"{arr.size}")
    check(
        "heat-ylim-top",
        tuple(ax.get_ylim()) == (3, 0),
        f"ylim={ax.get_ylim()}",
    )
    check(
        "heat-xticklabels",
        [t.get_text() for t in ax.get_xticklabels()] == ["svm", "rf", "mlp"],
        f"{[t.get_text() for t in ax.get_xticklabels()]}",
    )
    check("heat-cbar-ax", len(fig.axes) == 2, f"{len(fig.axes)}")
    probs, warns = audit_of(fig), warnings_of(fig)
    check("heat-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # --- matrix 直给：无 dataset、xlabels/ylabels、annotate 模板、cbar dict ---
    spec = {
        "version": 1,
        "series": [
            {
                "kind": "heat",
                "matrix": [[0.9, 0.4, None], [0.3, 0.7, 0.6]],
                "xlabels": ["a", "b", "c"],
                "ylabels": ["r1", "r2"],
                "cbar": {"label": "win rate"},
                "annotate": "{v:.1f}",
            }
        ],
        "meta": meta,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "heat-matrix-labels",
        [t.get_text() for t in ax.get_xticklabels()] == ["a", "b", "c"]
        and [t.get_text() for t in ax.get_yticklabels()] == ["r1", "r2"],
        "axis labels wrong",
    )
    # None 格不写字——5 个有限格 = 5 个注记
    texts = [t.get_text() for t in ax.texts]
    check("heat-ann-count", len(texts) == 5, f"{texts}")
    check("heat-ann-fmt", "0.9" in texts, f"{texts}")
    probs, warns = audit_of(fig), warnings_of(fig)
    check("heat-matrix-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # --- div cmap：默认 vc=0 对称 TwoSlopeNorm ---
    spec = {
        "version": 1,
        "series": [
            {
                "kind": "heat",
                "matrix": [[-0.8, 0.2], [0.6, -0.1]],
                "xlabels": ["a", "b"],
                "ylabels": ["r1", "r2"],
                "cmap": "div",
            }
        ],
        "meta": meta,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    mesh = next(c for c in ax.collections if c.get_array() is not None)
    check(
        "heat-div-norm",
        mesh.norm.vcenter == 0 and abs(mesh.norm.vmin + mesh.norm.vmax) < 1e-9,
        f"vc={mesh.norm.vcenter} [{mesh.norm.vmin},{mesh.norm.vmax}]",
    )
    probs, warns = audit_of(fig), warnings_of(fig)
    check("heat-div-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)

    # --- 长表顺序钉：xlabels 列出先排、未列出的按原序追加 ---
    spec = {
        "version": 1,
        "data": {"d": _heat_rows()},
        "series": [
            {
                "kind": "heat",
                "from": "d",
                "x": "x",
                "y": "y",
                "z": "z",
                "xlabels": ["rf", "svm"],  # mlp 未列出 → 追加尾部
            }
        ],
        "meta": meta,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "heat-order-pin",
        [t.get_text() for t in ax.get_xticklabels()] == ["rf", "svm", "mlp"],
        f"{[t.get_text() for t in ax.get_xticklabels()]}",
    )
    plt.close(fig)


def heat_errors():
    """heat 的 SpecError 面：形态混用、坏矩阵、重复格、坏 cmap/vcenter。"""
    base = {"version": 1, "meta": {"ledger": "l", "caption": "c"}}
    expect_error(
        "heat-mixed-form",
        base
        | {
            "series": [{"kind": "heat", "matrix": [[1]], "x": "x"}],
        },
        "belongs to the long-table",
    )
    expect_error(
        "heat-ragged",
        base | {"series": [{"kind": "heat", "matrix": [[1, 2], [3]]}]},
        "ragged",
    )
    expect_error(
        "heat-nonnum-cell",
        base | {"series": [{"kind": "heat", "matrix": [["a"]]}]},
        "non-numeric",
    )
    expect_error(
        "heat-missing-z",
        base
        | {
            "data": {"d": [{"x": "a", "y": "b"}]},
            "series": [{"kind": "heat", "x": "x", "y": "y"}],
        },
        "missing required 'z'",
    )
    expect_error(
        "heat-by",
        base
        | {
            "data": {"d": [{"x": "a", "y": "b", "z": 1}]},
            "series": [{"kind": "heat", "x": "x", "y": "y", "z": "z", "by": "g"}],
        },
        "'by' does not apply",
    )
    expect_error(
        "heat-bad-cmap",
        base | {"series": [{"kind": "heat", "matrix": [[1]], "cmap": "virdis"}]},
        "unknown cmap",
    )
    expect_error(
        "heat-dup-cell",
        base
        | {
            "data": {
                "d": [
                    {"x": "a", "y": "b", "z": 1},
                    {"x": "a", "y": "b", "z": 2},
                ]
            },
            "series": [{"kind": "heat", "x": "x", "y": "y", "z": "z"}],
        },
        "duplicate cell",
    )
    expect_error(
        "heat-vcenter-range",
        base
        | {
            "series": [{"kind": "heat", "matrix": [[1, 2]], "vcenter": 5}],
        },
        "outside data range",
    )
    expect_error(
        "heat-bad-ann",
        base
        | {
            "series": [{"kind": "heat", "matrix": [[1]], "annotate": "{w:.1f}"}],
        },
        "annotate",
    )


def heat_lints():
    """heat 语义 lint：heat-cell-text 阈值与类别轴 axis-ignored。"""
    meta = {"ledger": "l", "caption": "c"}
    big = {"version": 1, "meta": meta}
    # 21 列 + annotate → heat-cell-text；关掉 annotate → 不报
    wide = [[float(i + j) for i in range(21)] for j in range(3)]
    spec = big | {"series": [{"kind": "heat", "matrix": wide, "annotate": True}]}
    expect_lint("heat-cell-text", spec, "heat-cell-text")
    spec = big | {"series": [{"kind": "heat", "matrix": wide}]}
    expect_lint("heat-cell-text-off", spec, "heat-cell-text", present=False)
    # heat 双轴类别：xaxis.ticks / yaxis.scale 归 kind 层 → axis-ignored
    spec = big | {
        "xaxis": {"ticks": [0, 1, 2]},
        "yaxis": {"scale": "log"},
        "series": [{"kind": "heat", "matrix": [[1, 2], [3, 4]]}],
    }
    expect_lint("heat-axis-ignored", spec, "axis-ignored")
    expect_lint("heat-scale-ignored", spec, "scale-ignored")


def spec_regressions():
    """回归：props 调色板 token、类别刻度就地身份、marker-clipped。"""
    # props 里 'vteal' 必须经 _resolve_props 换成 hex——直通 mpl 炸 ValueError
    # note 落点须离开 y=x+1 线迹——压线触发 text-overlaps-data
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [
            {"kind": "line", "x": "x", "y": "y"},
            {
                "kind": "note",
                "at": [0.5, 1.8],
                "text": "hi",
                "props": {"color": "vteal", "fontsize": 8},
            },
        ],
        "xaxis": {"label": "x"},
        "yaxis": {"label": "y"},
    }
    fig = render(spec)
    check("props-token-note", not audit_of(fig), f"{audit_of(fig)}")
    plt.close(fig)

    # 嵌套 dict（arrowprops）里的 token 也递归解析
    spec["series"][1]["arrow"] = True
    spec["series"][1]["props"]["arrowprops"] = {"color": "vcoral"}
    fig = render(spec)
    check("props-token-arrowprops", not audit_of(fig), f"{audit_of(fig)}")
    plt.close(fig)

    # violin+by 无 legend：类别刻度就地给出身份 -> 不报 legend-coverage
    rows = [
        {"g": g, "v": float(v)}
        for g in ("alpha", "beta")
        for v in np.linspace(0, 1, 12)
    ]
    spec = {
        "version": 1,
        "data": {"d": rows},
        "series": [{"kind": "violin", "y": "v", "by": "g"}],
    }
    fig = render(spec)
    probs = audit_of(fig)
    check(
        "violin-catlabels-no-legend",
        not any(p.startswith("legend-coverage") for p in probs),
        f"{probs}",
    )
    plt.close(fig)

    # PathCollection 散点不适用类别豁免：贴边 marker -> marker-clipped
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 0.5}, {"x": 1, "y": 0.6}]},
        "series": [{"kind": "scatter", "x": "x", "y": "y", "s": 200}],
        "xaxis": {"lim": [0, 1]},
        "yaxis": {"lim": [0, 1]},
    }
    fig = render(spec)
    probs = audit_of(fig)
    check(
        "marker-clipped-edge",
        any(p.startswith("marker-clipped") for p in probs),
        f"{probs}",
    )
    plt.close(fig)

    # props color 走完整 resolve：registry 'fam:Key' 引用与系列 color 同口径
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "colors": {"registries": {"fam": {"Main": "vteal"}}},
        "series": [
            {"kind": "line", "x": "x", "y": "y"},
            {
                "kind": "note",
                "at": [0.5, 1.8],
                "text": "hi",
                "props": {"color": "fam:Main"},
            },
        ],
    }
    fig = render(spec)
    col = fig.get_axes()[0].texts[0].get_color()
    check("props-color-registry", col.lower() == "#4f8fa5", f"{col}")
    plt.close(fig)

    # registry 键不存在 -> SpecError 带候选，不再穿透 mpl 炸裸 ValueError
    bad = json.loads(json.dumps(spec))
    bad["series"][1]["props"]["color"] = "fam:Nope"
    expect_error("props-color-badkey", bad, "unresolved-color", "fam")
    bad["series"][1]["props"]["color"] = "zz:top"
    expect_error("props-color-namespace", bad, "unknown color namespace")
    bad["series"][1]["props"]["color"] = "notacolor"
    expect_error("props-color-badtoken", bad, "color token")

    # mpl 原生色仍放行（'red'/'tab:blue' 这类直通 mpl 判定）
    spec["series"][1]["props"]["color"] = "red"
    fig = render(spec)
    check(
        "props-color-mpl-native",
        fig.get_axes()[0].texts[0].get_color() == "red",
    )
    plt.close(fig)

    # panel.where 不再泄漏给中性 note：此前撞 'where'/'from' need a
    # data source；panel.from 本就不泄漏，现在两边对称
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1, "g": "a"}, {"x": 1, "y": 2, "g": "b"}]},
        "where": {"g": "a"},
        "series": [
            {"kind": "line", "x": "x", "y": "y"},
            {"kind": "note", "at": [0.5, 1.5], "text": "hi"},
        ],
    }
    fig = render(spec)
    check("panel-where-neutral-note", fig is not None)
    plt.close(fig)
    # 中性系列自带 where 仍响亮报错，且点名出问题的 sid/kind
    bad = json.loads(json.dumps(spec))
    bad["series"][1] = dict(bad["series"][1], id="nn", where={"g": "a"})
    expect_error("note-own-where", bad, "nn", "note", "data source")

    # units:'figure' 的 note 自动 in_layout=False——不再计入宿主 axes
    # 的 tight bbox 把面板挤出版心；data 坐标 note 不受影响
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [
            {"kind": "line", "x": "x", "y": "y"},
            {"kind": "note", "at": [0.98, 0.02], "units": "figure", "text": "fig"},
            {"kind": "note", "at": [0.5, 1.5], "text": "dat"},
        ],
    }
    fig = render(spec)
    inl = {t.get_text(): t.get_in_layout() for t in fig.get_axes()[0].texts}
    check(
        "note-figure-in-layout",
        inl.get("fig") is False and bool(inl.get("dat")),
        f"{inl}",
    )
    plt.close(fig)


def cat_coords():
    """类别坐标统一经 _cat_map：scatter/line/note/ref/span 的字符串坐标按
    同面板类别轴（bar 槽位 / box 组位 / heat 格心）解析——结构所有者优
    先，缺席时消费型 kind（scatter/line）按数据首见序兜底建表，面板层
    补画刻度；scatter 不再按自身首见序私建映射——跨系列共享同一槽位口
    径；无类别轴或未知名响亮报错，数值直过。"""
    # bar 类目序按首见 [b,a,c]；scatter 数据序 [a,c] 不同——须落 bar 槽位
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"arm": "b", "v": 2},
                {"arm": "a", "v": 1},
                {"arm": "c", "v": 3},
            ],
            "s": [{"arm": "a", "y": 2.5}, {"arm": "c", "y": 0.5}],
        },
        "series": [
            {"kind": "bar", "from": "d", "x": "arm", "y": "v"},
            {"kind": "scatter", "from": "s", "x": "arm", "y": "y"},
            {"kind": "note", "from": "d", "at": ["c", 3.4], "text": "top"},
            {"kind": "ref", "from": "d", "dir": "v", "at": "a"},
            {"kind": "span", "from": "d", "at": ["a", "c"]},
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    sc = next(
        c for c in ax.collections if isinstance(c, mpl.collections.PathCollection)
    )
    check(
        "catmap-scatter-x",
        np.allclose(sc.get_offsets()[:, 0], [1.0, 2.0]),
        f"{sc.get_offsets()[:, 0]}",
    )
    note = next(t for t in ax.texts if t.get_text() == "top")
    check("catmap-note-at", np.allclose(note.xy, [2.0, 3.4]), f"{note.xy}")
    check(
        "catmap-ref-at",
        np.allclose(ax.lines[0].get_xdata(), [1.0, 1.0]),
        f"{ax.lines[0].get_xdata()}",
    )
    span = next(p for p in ax.patches if p.get_gid() == "fv-neutral")
    check(
        "catmap-span-at",
        np.allclose([span.get_x(), span.get_width()], [1.0, 1.0]),
        f"x={span.get_x()} w={span.get_width()}",
    )
    plt.close(fig)

    # note 逐行扇出：at:{x:col} 的列值是类别名 → 落槽位
    spec["series"] = [
        {"kind": "bar", "from": "d", "x": "arm", "y": "v"},
        {
            "kind": "note",
            "from": "n",
            "at": {"x": "who", "y": "hh"},
            "text": "{who}",
        },
    ]
    spec["data"]["n"] = [{"who": "a", "hh": 2.0}, {"who": "b", "hh": 2.5}]
    fig = render(spec)
    ax = fig.get_axes()[0]
    xy = {t.get_text(): tuple(t.xy) for t in ax.texts}
    check(
        "catmap-note-fanout",
        np.allclose(xy["a"], [1.0, 2.0]) and np.allclose(xy["b"], [0.0, 2.5]),
        f"{xy}",
    )
    plt.close(fig)

    # dir:'h' 的 bar 把类别轴换到 y——scatter 的字符串 y 落同一组槽位
    spec = {
        "version": 1,
        "data": {
            "d": [{"arm": "b", "v": 2}, {"arm": "a", "v": 1}],
            "s": [{"xx": 2.5, "arm": "a"}],
        },
        "series": [
            {"kind": "bar", "dir": "h", "from": "d", "x": "arm", "y": "v"},
            {"kind": "scatter", "from": "s", "x": "xx", "y": "arm"},
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    sc = next(
        c for c in ax.collections if isinstance(c, mpl.collections.PathCollection)
    )
    check(
        "catmap-scatter-y-horiz",
        np.allclose(sc.get_offsets()[0], [2.5, 1.0]),
        f"{sc.get_offsets()}",
    )
    plt.close(fig)

    # box 组位（默认 1..n）：note 按组名落位
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"g": "m", "v": 1},
                {"g": "m", "v": 2},
                {"g": "z", "v": 3},
                {"g": "z", "v": 4},
            ]
        },
        "series": [
            {"kind": "box", "y": "v", "by": "g"},
            {"kind": "note", "from": "d", "at": ["z", 5], "text": "hi"},
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    note = next(t for t in ax.texts if t.get_text() == "hi")
    check("catmap-box-note", np.allclose(note.xy, [2.0, 5.0]), f"{note.xy}")
    plt.close(fig)

    # xaxis.lim 收类别名（按序号定限、裁尾部类别）——字符串经同一 catmap
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"arm": "b", "v": 2},
                {"arm": "a", "v": 1},
                {"arm": "c", "v": 3},
            ]
        },
        "xaxis": {"lim": ["a", "c"]},
        "series": [{"kind": "bar", "x": "arm", "y": "v"}],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("catmap-xlim", np.allclose(ax.get_xlim(), [1.0, 2.0]), f"{ax.get_xlim()}")
    plt.close(fig)

    # 未知名 / 非类别轴 / scatter 自映射（已移除）→ SpecError
    expect_error(
        "catmap-unknown",
        {
            "version": 1,
            "data": {"d": [{"arm": "a", "v": 1}]},
            "series": [
                {"kind": "bar", "x": "arm", "y": "v"},
                {"kind": "note", "at": ["zz", 1], "text": "t"},
            ],
        },
        "not a known x-axis category",
    )
    expect_error(
        "catmap-noncat",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
            "series": [
                {"kind": "line", "x": "x", "y": "y"},
                {"kind": "note", "at": ["a", 1], "text": "t"},
            ],
        },
        "non-categorical",
    )

    # 消费型兜底：scatter 独面板的类别列按首见序自建槽位 + 面板层补刻度
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"arm": "a", "v": 1}, {"arm": "b", "v": 2}]},
            "series": [{"kind": "scatter", "x": "arm", "y": "v"}],
        }
    )
    ax = fig.get_axes()[0]
    sc = next(
        c for c in ax.collections if isinstance(c, mpl.collections.PathCollection)
    )
    check(
        "catmap-consumer-x",
        np.allclose(sc.get_offsets()[:, 0], [0.0, 1.0]),
        f"{sc.get_offsets()[:, 0]}",
    )
    check(
        "catmap-consumer-ticks",
        [t.get_text() for t in ax.get_xticklabels()] == ["a", "b"],
        f"{[t.get_text() for t in ax.get_xticklabels()]}",
    )
    plt.close(fig)

    # 消费型槽位对其他 kind 同样可解析；未知名报错列出可用类别
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"arm": "a", "v": 1}, {"arm": "b", "v": 2}]},
            "series": [
                {"kind": "scatter", "x": "arm", "y": "v"},
                {"kind": "note", "at": ["b", 2.5], "text": "t"},
            ],
        }
    )
    ax = fig.get_axes()[0]
    note = next(t for t in ax.texts if t.get_text() == "t")
    check(
        "catmap-note-consumer",
        np.allclose(note.xy, [1.0, 2.5]),
        f"{note.xy}",
    )
    plt.close(fig)
    expect_error(
        "catmap-consumer-unknown",
        {
            "version": 1,
            "data": {"d": [{"arm": "a", "v": 1}]},
            "series": [
                {"kind": "scatter", "x": "arm", "y": "v"},
                {"kind": "note", "at": ["zz", 1], "text": "t"},
            ],
        },
        "not a known x-axis category",
    )

    # dir:'h'：类别轴在 y——yaxis.ticks 被 lint 忽略，x 轴是数值轴
    # （spec ticks 正常生效、不报 axis-ignored）
    hbar = {
        "version": 1,
        "data": {"d": [{"arm": "a", "v": 1}, {"arm": "b", "v": 2}]},
        "series": [{"kind": "bar", "dir": "h", "x": "arm", "y": "v"}],
    }
    expect_lint(
        "horiz-cat-y-axis-ignored",
        dict(hbar, yaxis={"ticks": [0]}),
        "axis-ignored",
    )
    expect_lint(
        "horiz-num-x-ticks-ok",
        dict(hbar, xaxis={"ticks": [0, 1, 2]}),
        "axis-ignored",
        present=False,
    )


def bar_label_yerr():
    """bar 带 yerr 时 labels 锚点 = 柱尖 + 对外帽长（数据单位），dy 的
    offset points 落在帽外；sym 双侧同值、asym 取对外一侧。"""
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"arm": "a", "v": 2, "e": 0.5},
                {"arm": "b", "v": 1, "e": 0.25},
            ]
        },
        "series": [
            {
                "kind": "bar",
                "x": "arm",
                "y": "v",
                "yerr": "e",
                "labels": {"mode": "value"},
            }
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    ys = sorted(t.xy[1] for t in ax.texts)
    check("bar-label-yerr", np.allclose(ys, [1.25, 2.5]), f"{ys}")
    plt.close(fig)

    spec["series"][0].pop("yerr")
    fig = render(spec)
    ax = fig.get_axes()[0]
    ys = sorted(t.xy[1] for t in ax.texts)
    check("bar-label-noerr", np.allclose(ys, [1.0, 2.0]), f"{ys}")
    plt.close(fig)

    # asym：取对外一侧（正值柱 → hi）
    spec["series"][0]["yerr"] = {"lo": "lo", "hi": "hi"}
    spec["data"]["d"] = [{"arm": "a", "v": 2, "lo": 0.1, "hi": 0.5}]
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "bar-label-yerr-asym",
        np.allclose(ax.texts[0].xy[1], 2.5),
        f"{ax.texts[0].xy}",
    )
    plt.close(fig)


def legend_order():
    """自动图例（无 entries）按 spec 系列声明序——mpl 收集序按 artist
    类型分组（PathCollection 排 BarContainer 前），与声明序脱钩；
    entries 显式给出时不变。"""
    spec = {
        "version": 1,
        "data": {
            "d": [{"arm": "a", "v": 1}, {"arm": "b", "v": 2}],
            "s": [{"x": 0, "y": 1.5}, {"x": 1, "y": 0.5}],
        },
        "legend": True,
        "series": [
            {"kind": "bar", "from": "d", "x": "arm", "y": "v", "label": "bars"},
            {"kind": "scatter", "from": "s", "x": "x", "y": "y", "label": "pts"},
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    got = [t.get_text() for t in ax.get_legend().get_texts()]
    check("legend-order-panel", got == ["bars", "pts"], f"{got}")
    plt.close(fig)

    # flat 顶层 legend 带 figure-only 键 → figure legend 同口径排序
    spec["legend"] = {"where": "below"}
    fig = render(spec)
    got = [t.get_text() for t in fig.legends[0].get_texts()]
    check("legend-order-figure", got == ["bars", "pts"], f"{got}")
    plt.close(fig)


def audit_file():
    """render_mpl 把审计行落到 <stem>.audit.txt（spec 头 + warn/ERR 行 +
    确认行）；--no-audit 写一行 skipped 而不是留过期报告。"""
    import subprocess

    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "fig.json"
        p.write_text(json.dumps(spec))
        r = subprocess.run(
            [sys.executable, str(SKILL_DIR / "scripts" / "render_mpl.py"), str(p)],
            capture_output=True,
            text=True,
        )
        af = Path(td) / "fig.audit.txt"
        check(
            "audit-file-exists",
            af.is_file(),
            f"rc={r.returncode} stderr={r.stderr[:120]}",
        )
        body = af.read_text() if af.is_file() else ""
        # 行集与 stdout 一致（spec 头 + warn/ERR + audit: 确认行；ok:/artifacts:
        # 只属 stdout 不落盘）
        want = [
            ln
            for ln in r.stdout.splitlines()
            if ln.startswith(("warn ", "ERR ", "audit:"))
        ]
        check(
            "audit-file-content",
            body.startswith("spec:")
            and body.splitlines()[1:] == want
            and want
            and want[-1].startswith("audit:"),
            body[:160],
        )
        r = subprocess.run(
            [
                sys.executable,
                str(SKILL_DIR / "scripts" / "render_mpl.py"),
                str(p),
                "--no-audit",
            ],
            capture_output=True,
            text=True,
        )
        body = af.read_text() if af.is_file() else ""
        check("audit-file-skip", "skipped" in body, body[:160])


def raw_ctx_panel_axes():
    """raw ctx['panel_axes']：面板 id -> Axes 稳定快照，跨面板辅助不必
    再按 position.x0 猜 fig.get_axes() 顺序。"""
    seen = {}

    def _touch_a(ax, ctx):
        pa = ctx["panel_axes"]
        seen["keys"] = sorted(pa)
        seen["self"] = pa["b"] is ax and pa["b"] is ctx["ax"]
        pa["a"].axhline(0.5, color="red", lw=0.8)

    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "panels": {
            "a": {"series": [{"kind": "line", "x": "x", "y": "y"}]},
            "b": {
                "series": [{"kind": "line", "x": "x", "y": "y"}],
                "raw": _touch_a,
            },
        },
        "layout": {"cells": [["a", "b"]]},
    }
    fig = render(spec)
    ax_a = fig.get_axes()[0]
    check("raw-panel-axes-keys", seen.get("keys") == ["a", "b"], f"{seen}")
    check("raw-panel-axes-self", seen.get("self"), f"{seen}")
    check(
        "raw-panel-axes-cross",
        any(list(ln.get_ydata()) == [0.5, 0.5] for ln in ax_a.lines),
        f"{[list(ln.get_ydata()) for ln in ax_a.lines]}",
    )
    plt.close(fig)


def edgecolor_registry():
    """scatter 一等 edgecolor 走完整 resolve：'fam:Key' registry 引用
    与系列 color 同口径，坏引用 SpecError 而非 mpl 裸 ValueError。"""
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}]},
        "colors": {"registries": {"fam": {"Main": "vteal"}}},
        "series": [{"kind": "scatter", "x": "x", "y": "y", "edgecolor": "fam:Main"}],
    }
    fig = render(spec)
    coll = fig.get_axes()[0].collections[0]
    ec = mpl.colors.to_hex(coll.get_edgecolors()[0])
    check("edgecolor-registry", ec == "#4f8fa5", f"{ec}")
    plt.close(fig)

    bad = json.loads(json.dumps(spec))
    bad["series"][0]["edgecolor"] = "fam:Nope"
    expect_error("edgecolor-badkey", bad, "unresolved-color", "fam")
    bad["series"][0]["edgecolor"] = "notacolor"
    expect_error("edgecolor-badtoken", bad, "color token")


def main() -> int:
    examples_clean()
    errors()
    lints()
    polar()
    audit_wiring()
    regressions()
    stacked_bars()
    errbars()
    new_lints()
    dist_kinds()
    dist_errors()
    dist_lints()
    heat_kinds()
    heat_errors()
    heat_lints()
    spec_regressions()
    meta_and_output()
    scoped_ignore_children()
    scoped_ignore_grandchildren()
    donut_missing()
    donut_pct_ink()
    cat_coords()
    bar_label_yerr()
    legend_order()
    cli()
    audit_file()
    output_save()
    raw_ctx_panel_axes()
    edgecolor_registry()
    print(f"--- spec: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
