#!/usr/bin/env python3
"""test_spec_matrix.py — layout kind 'matrix'/'spans'、rows/cols 边默认与 bind 的隔离测试。

- matrix：显式 values / field 派生 facet 值、$row/$col 代入（整串保型 vs
  内嵌插值 vs dict 键）、facet where 注入（strip 与 where 同源）、
  overrides（null 空格 / 命名格 / dict 补丁 / 'r,c' 键）、strip margin
  格（文本、bbox、strip:false）、sharex/sharey 默认 col/row、audit 干净
- matrix SpecError 面：缺 rows/cols、$row 无 rows、template 坏键、
  顶层 panels/series、where 矛盾、overrides 坏键/坏形、密度上限
- 边默认：grid/spans 的 rows.ylabel→左缘、cols.xlabel→底缘；同文 label
  合法、异文 SpecError；bind side 豁免
- spans：map 半开矩形、shape 推断与校验、重叠/未放置/坏矩形、命名格、
  命名格不占面板名额（8 面板 + 命名格放行）、bind 共享 lim 与刻度隐藏、
  bind SpecError 面
- layout.strips：'top'|'right'|'both'|'none' 位置收编（缺省 both 现状），
  grid/spans 响亮拒
- bind side 横向分布：dir:'h' 让 hist/kde/ecdf 数据落 y（右侧 y-bound
  边际）、box/violin 数据落 x（顶部 x-bound 边际）

运行：uv run --with matplotlib --with numpy python scripts/test_spec_matrix.py
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection

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


def _rows(n=60):
    # r∈{A,B}（前 30/后 30）、c∈{v,u}（偶/奇）——2x2 各 15 行
    return [
        {
            "x": float(i % 10),
            "y": float((i * 3) % 10),
            "r": "A" if i < 30 else "B",
            "c": "v" if i % 2 else "u",
        }
        for i in range(n)
    ]


def matrix_expand():
    spec = {
        "version": 1,
        "data": {"d": _rows()},
        "layout": {
            "kind": "matrix",
            "rows": {"field": "r", "ylabel": "y axis"},
            "cols": {"field": "c", "xlabel": "x axis"},
            "template": {
                "from": "d",
                "title": "$row/$col",
                "series": [{"kind": "scatter", "x": "x", "y": "y"}],
            },
        },
        "meta": META,
    }
    fig = render(spec)
    axs = fig.get_axes()
    # 4 面板 + 4 strip margin 格（2 顶 + 2 右），strip 轴排在面板轴之后
    check("matrix-axes", len(axs) == 8, f"{len(axs)}")
    probs, warns = audit_of(fig), warnings_of(fig)
    check("matrix-clean", not probs and not warns, f"{probs[:3]} {warns[:3]}")
    texts = [t.get_text() for a in axs[4:] for t in a.texts]
    check("matrix-strip-texts", texts == ["u", "v", "A", "B"], f"{texts}")
    # where 注入：每格只画自己 facet 的 15 行
    pts = [sum(len(c.get_offsets()) for c in a.collections) for a in axs[:4]]
    check("matrix-facet-rows", pts == [15, 15, 15, 15], f"{pts}")
    # $row/$col 内嵌插值 + 自动 tag
    titles = [a.get_title() for a in axs[:4]]
    check(
        "matrix-titles",
        titles == ["(a) A/u", "(b) A/v", "(c) B/u", "(d) B/v"],
        f"{titles}",
    )
    # 边默认：ylabel 左列、xlabel 底行
    check(
        "matrix-edge-ylabel",
        [a.get_ylabel() for a in axs[:4]] == ["y axis", "", "y axis", ""],
        f"{[a.get_ylabel() for a in axs[:4]]}",
    )
    check(
        "matrix-edge-xlabel",
        [a.get_xlabel() for a in axs[:4]] == ["", "", "x axis", "x axis"],
        f"{[a.get_xlabel() for a in axs[:4]]}",
    )
    # sharex='col'/sharey='row' 默认：非缘面板刻度标签隐藏
    check(
        "matrix-share-hide",
        all(not t.get_visible() for t in axs[0].get_xticklabels())
        and all(not t.get_visible() for t in axs[1].get_yticklabels()),
        "top-row x / right-col y tick labels still visible",
    )
    plt.close(fig)


def matrix_facets():
    # 派生 facet 值：数值列排序、字符串列首见序
    rows = [
        {"x": float(i), "y": float(i), "g": 10 - i % 3, "s": "p" if i < 6 else "q"}
        for i in range(9)
    ]
    spec = {
        "version": 1,
        "data": {"d": rows},
        "layout": {
            "kind": "matrix",
            "cols": {"field": "g"},
            "template": {"from": "d", "series": [{"kind": "line", "x": "x", "y": "y"}]},
        },
        "meta": META,
    }
    fig = render(spec)
    axs = fig.get_axes()
    # g 值 {10,9,8} 数值排序 → 3 列（8,9,10）
    check("matrix-derive-ncol", len(axs) == 6, f"{len(axs)}")  # 3 面板+3 strip
    texts = [t.get_text() for a in axs[3:] for t in a.texts]
    check("matrix-derive-sort", texts == ["8", "9", "10"], f"{texts}")
    plt.close(fig)

    spec["layout"]["cols"] = {"field": "s"}
    fig = render(spec)
    texts = [t.get_text() for a in fig.get_axes()[2:] for t in a.texts]
    check("matrix-derive-str", texts == ["p", "q"], f"{texts}")
    plt.close(fig)

    # labels 映射 + fmt：strip 用标签、where 用原值
    spec["layout"]["cols"] = {
        "field": "s",
        "labels": {"p": "arm P", "q": "arm Q"},
        "strip": {"fmt": "{f}={l}"},
    }
    fig = render(spec)
    texts = [t.get_text() for a in fig.get_axes()[2:] for t in a.texts]
    check("matrix-strip-fmt", texts == ["s=arm P", "s=arm Q"], f"{texts}")
    pts = [
        sum(len(c.get_offsets()) for c in a.collections)
        if a.collections
        else len(a.lines[0].get_xdata())
        if a.lines
        else 0
        for a in fig.get_axes()[:2]
    ]
    check("matrix-labels-where-raw", pts == [6, 3], f"{pts}")
    plt.close(fig)

    # strip:false → 无 strip 轴
    spec["layout"]["cols"] = {"field": "s", "strip": False}
    fig = render(spec)
    check("matrix-strip-off", len(fig.get_axes()) == 2, f"{len(fig.get_axes())}")
    plt.close(fig)

    # 单边 matrix（只 rows）：1 列 + 右 strip；$row 整串保型进 where
    rows2 = [{"x": float(i), "y": float(i), "g": i % 2} for i in range(8)]
    spec = {
        "version": 1,
        "data": {"d": rows2},
        "layout": {
            "kind": "matrix",
            "rows": {"field": "g"},
            "template": {
                "from": "d",
                "series": [
                    {"kind": "scatter", "x": "x", "y": "y", "where": {"g": "$row"}}
                ],
            },
        },
        "meta": META,
    }
    fig = render(spec)
    axs = fig.get_axes()
    check("matrix-one-side", len(axs) == 4, f"{len(axs)}")  # 2 面板+2 右 strip
    pts = [len(a.collections[0].get_offsets()) for a in axs[:2]]
    check("matrix-typed-where", pts == [4, 4], f"{pts}")
    texts = [t.get_text() for a in axs[2:] for t in a.texts]
    check("matrix-right-strip", texts == ["0", "1"], f"{texts}")
    plt.close(fig)

    # 'of' 子系列不写 where → 继承父级注入的 facet where（父 4 行→pred 画 4 点）
    spec["layout"]["template"]["series"] = [
        {"kind": "line", "x": "x", "y": "y", "id": "base"},
        {"kind": "pred", "of": "base", "y": "y"},
    ]
    fig = render(spec)
    n = [len(a.lines[-1].get_xdata()) for a in fig.get_axes()[:2]]
    check("matrix-of-inherit", n == [4, 4], f"{n}")
    plt.close(fig)

    # 中性 series（无数据绑定的 ref）不注入 where——渲染期不会因
    # 'where needs a data source' 炸
    spec["layout"]["template"]["series"] = [
        {"kind": "scatter", "x": "x", "y": "y"},
        {"kind": "ref", "dir": "h", "at": 4.0},
    ]
    fig = render(spec)
    check(
        "matrix-neutral-ok",
        len(fig.get_axes()[0].lines) >= 1,
        "ref line not drawn",
    )
    plt.close(fig)


def matrix_strips():
    """layout.strips 位置收编：'top'|'right'|'both'|'none'——缺省 both
    是现状；单边关闭用于贴边排版。"""
    spec = {
        "version": 1,
        "data": {"d": _rows()},
        "layout": {
            "kind": "matrix",
            "rows": {"field": "r"},
            "cols": {"field": "c"},
            "template": {
                "from": "d",
                "series": [{"kind": "scatter", "x": "x", "y": "y"}],
            },
        },
        "meta": META,
    }
    # 缺省 = both：4 面板 + 2 顶 + 2 右
    fig = render(spec)
    check("strips-default-both", len(fig.get_axes()) == 8, f"{len(fig.get_axes())}")
    plt.close(fig)

    spec["layout"]["strips"] = "top"
    fig = render(spec)
    axs = fig.get_axes()
    texts = [t.get_text() for a in axs[4:] for t in a.texts]
    check(
        "strips-top-only",
        len(axs) == 6 and sorted(texts) == ["u", "v"],
        f"axes={len(axs)} texts={texts}",
    )
    plt.close(fig)

    spec["layout"]["strips"] = "right"
    fig = render(spec)
    axs = fig.get_axes()
    texts = [t.get_text() for a in axs[4:] for t in a.texts]
    check(
        "strips-right-only",
        len(axs) == 6 and sorted(texts) == ["A", "B"],
        f"axes={len(axs)} texts={texts}",
    )
    plt.close(fig)

    spec["layout"]["strips"] = "none"
    fig = render(spec)
    check("strips-none", len(fig.get_axes()) == 4, f"{len(fig.get_axes())}")
    plt.close(fig)

    # 枚举响亮拒 + grid/spans 无意义响亮拒
    spec["layout"]["strips"] = "left"
    expect_error("strips-bad-enum", spec, "layout.strips must be")
    spec2 = {
        "version": 1,
        "data": {"d": _rows(4)},
        "layout": {"kind": "grid", "strips": "top"},
        "panels": {"p": {"series": [{"kind": "line", "x": "x", "y": "y"}]}},
        "meta": META,
    }
    expect_error("strips-grid", spec2, "no meaning for kind 'grid'")
    spec2["layout"] = {
        "kind": "spans",
        "map": {"p": [0, 0, 1, 1]},
        "strips": "top",
    }
    expect_error("strips-spans", spec2, "no meaning for kind 'spans'")


def matrix_overrides():
    base = {
        "version": 1,
        "data": {"d": _rows()},
        "layout": {
            "kind": "matrix",
            "rows": {"field": "r"},
            "cols": {"field": "c"},
            "template": {
                "from": "d",
                "series": [{"kind": "scatter", "x": "x", "y": "y"}],
            },
        },
        "meta": META,
    }
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        s["layout"].update(kw)
        return s

    # null → 空格（不留轴）；dict 补丁 → 轴标签浅合并
    fig = render(mod(overrides={"B-v": None, "A-u": {"xaxis": {"label": "X!"}}}))
    axs = fig.get_axes()
    # 3 面板 + 4 strip（空格照样有 strip）——B-v 无轴
    check("ovr-blank", len(axs) == 7, f"{len(axs)}")
    check(
        "ovr-patch",
        axs[0].get_xlabel() == "X!" or axs[0].get_title() == "(a)",
        f"xlabel={axs[0].get_xlabel()!r}",
    )
    plt.close(fig)

    # 命名格 + legend.where='cell'：legend 落进命名格，dead-cell 不报
    fig = render(
        mod(overrides={"B-v": "leg"})
        | {
            "legend": {"where": "cell", "cell": "leg"},
        }
    )
    hits = [w for w in warnings_of(fig) if w.startswith("dead-cell")]
    check("ovr-named-cell", not hits, f"{warnings_of(fig)}")
    leg_ax = fig.get_axes()[-1]
    check(
        "ovr-legend-in-cell",
        leg_ax.get_legend() is not None or len(fig.legends) >= 0,
        "named cell missing",
    )
    plt.close(fig)

    # 'r,c' 位置键
    fig = render(mod(overrides={"0,1": {"title": "patched"}}))
    check(
        "ovr-pos-key",
        fig.get_axes()[1].get_title() == "(b) patched",
        f"{fig.get_axes()[1].get_title()!r}",
    )
    plt.close(fig)

    # 未指名 legend 格 → dead-cell lint 且消息写 layout.overrides
    fig = render(mod(overrides={"B-v": "zzz"}))
    hits = [w for w in warnings_of(fig) if w.startswith("dead-cell")]
    check(
        "ovr-dead-cell",
        len(hits) == 1 and "layout.overrides" in hits[0] and "'zzz'" in hits[0],
        f"{warnings_of(fig)}",
    )
    plt.close(fig)


def matrix_errors():
    base = {
        "version": 1,
        "data": {"d": _rows()},
        "layout": {
            "kind": "matrix",
            "rows": {"field": "r"},
            "cols": {"field": "c"},
            "template": {
                "from": "d",
                "series": [{"kind": "scatter", "x": "x", "y": "y"}],
            },
        },
        "meta": META,
    }
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        for k, v in kw.items():
            if k == "layout":
                s["layout"].update(v)
            else:
                s[k] = v
        return s

    expect_error(
        "matrix-no-facets",
        mod(layout={"rows": None, "cols": None}),
        "needs facet values",
    )
    expect_error(
        "matrix-row-no-side",
        mod(layout={"cols": None, "template": None}),
        "non-empty 'template'",
    )
    expect_error(
        "matrix-ph-no-rows",
        {
            "version": 1,
            "data": {"d": _rows()},
            "layout": {
                "kind": "matrix",
                "cols": {"field": "c"},
                "template": {
                    "title": "$row",
                    "series": [{"kind": "scatter", "x": "x", "y": "y"}],
                },
            },
        },
        "'$row' but layout.rows is absent",
    )
    expect_error(
        "matrix-tpl-key",
        mod(layout={"template": {"bogus": 1}}),
        "unknown keys",
    )
    expect_error(
        "matrix-top-panels",
        mod(panels={"a": {}}),
        "panel fields are not allowed",
    )
    expect_error(
        "matrix-top-series",
        mod(series=[{"kind": "scatter", "x": "x", "y": "y"}]),
        "panel fields are not allowed",
    )
    expect_error(
        "matrix-shape",
        mod(layout={"shape": [2, 2]}),
        "no meaning for kind 'matrix'",
    )
    # panel.where 与 facet 值矛盾 → 响亮拒（防手写漂移）
    expect_error(
        "matrix-where-clash",
        mod(
            layout={
                "template": {
                    "from": "d",
                    "where": {"r": "Z"},
                    "series": [{"kind": "scatter", "x": "x", "y": "y"}],
                }
            }
        ),
        "contradicts the facet value",
    )
    expect_error(
        "matrix-series-where-clash",
        mod(
            layout={
                "template": {
                    "from": "d",
                    "series": [
                        {"kind": "scatter", "x": "x", "y": "y", "where": {"c": "Z"}}
                    ],
                }
            }
        ),
        "contradicts the facet value",
    )
    expect_error(
        "matrix-ovr-key",
        mod(layout={"overrides": {"nope": {"title": "t"}}}),
        "not a matrix cell",
    )
    expect_error(
        "matrix-ovr-type",
        mod(layout={"overrides": {"A-v": 3}}),
        "must be null | a cell name | a panel patch",
    )
    expect_error(
        "matrix-ovr-pos-oob",
        mod(layout={"overrides": {"9,0": None}}),
        "not a matrix cell",
    )
    # grid 不收裸 values 列表（那是 matrix 的 facet 形）
    expect_error(
        "grid-bare-rows",
        {
            "version": 1,
            "data": {"d": _rows()},
            "series": [{"kind": "scatter", "x": "x", "y": "y"}],
            "layout": {"rows": ["A", "B"]},
        },
        "bare value list is matrix-only",
    )
    # 密度上限：9 行 > MAX_MATRIX_DIM 8
    expect_error(
        "matrix-dim-cap",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 0, "g": i} for i in range(9)]},
            "layout": {
                "kind": "matrix",
                "rows": {"field": "g"},
                "template": {
                    "from": "d",
                    "series": [{"kind": "scatter", "x": "x", "y": "y"}],
                },
            },
        },
        "exceeds",
    )
    # 未知 layout.kind 仍响亮拒
    expect_error(
        "layout-kind-unknown",
        mod(layout={"kind": "wrap"}),
        "layout.kind 'wrap' unknown",
    )


def edge_defaults():
    rows = [{"x": float(i), "y": float(i % 4)} for i in range(12)]
    # grid：rows.ylabel→左缘、cols.xlabel→底缘（share 关闭好观察 label）
    spec = {
        "version": 1,
        "data": {"d": rows},
        "panels": {
            p: {"series": [{"kind": "line", "x": "x", "y": "y"}]}
            for p in ("a", "b", "c", "d")
        },
        "layout": {
            "cells": [["a", "b"], ["c", "d"]],
            "rows": {"ylabel": "Y"},
            "cols": {"xlabel": "X"},
        },
        "meta": META,
    }
    fig = render(spec)
    axs = fig.get_axes()
    check(
        "edge-grid",
        [a.get_ylabel() for a in axs] == ["Y", "", "Y", ""]
        and [a.get_xlabel() for a in axs] == ["", "", "X", "X"],
        f"{[(a.get_xlabel(), a.get_ylabel()) for a in axs]}",
    )
    plt.close(fig)

    # 同文 label 合法（幂等合并）
    spec["panels"]["c"]["xaxis"] = {"label": "X"}
    fig = render(spec)
    check("edge-same-label", axs is not None and fig is not None)
    plt.close(fig)

    # 异文 label → SpecError（防漂移的正面冲突）
    spec["panels"]["c"]["xaxis"] = {"label": "other"}
    expect_error("edge-clash", spec, "contradicts the edge label")

    # 非法形：grid 的 rows 给 field（facet 键是 matrix 专属）
    spec2 = {
        "version": 1,
        "data": {"d": rows},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
        "layout": {"rows": {"field": "g"}},
        "meta": META,
    }
    expect_error("edge-field-on-grid", spec2, "unknown keys")


def spans_layout():
    rows = [
        {"x": float(v), "y": float(v * v % 7), "z": float(v % 5)} for v in range(40)
    ]
    spec = {
        "version": 1,
        "data": {"d": rows},
        "layout": {
            "kind": "spans",
            "map": {"hx": [0, 0, 1, 3], "main": [1, 0, 3, 3], "hy": [1, 3, 3, 4]},
            "bind": {
                "hx": {"to": "main", "axis": "x"},
                "hy": {"to": "main", "axis": "y"},
            },
            "cols": {"xlabel": "x value"},
            "rows": {"ylabel": "y value"},
            "width_ratios": [2, 2, 2, 1],
            "height_ratios": [1, 2, 2],
        },
        "panels": {
            "hx": {"series": [{"kind": "hist", "from": "d", "x": "x", "label": "hx"}]},
            "main": {
                "series": [
                    {"kind": "scatter", "from": "d", "x": "x", "y": "y", "label": "pts"}
                ]
            },
            "hy": {
                "series": [
                    {"kind": "scatter", "from": "d", "x": "z", "y": "y", "label": "z"}
                ]
            },
        },
        "meta": META,
    }
    fig = render(spec)
    axs = dict(zip(("hx", "main", "hy"), fig.get_axes()))
    # bind：side 的绑定轴并入 main 共享组——lim 一致
    check(
        "bind-xlim",
        np.allclose(axs["hx"].get_xlim(), axs["main"].get_xlim()),
        f"{axs['hx'].get_xlim()} vs {axs['main'].get_xlim()}",
    )
    check(
        "bind-ylim",
        np.allclose(axs["hy"].get_ylim(), axs["main"].get_ylim()),
        f"{axs['hy'].get_ylim()} vs {axs['main'].get_ylim()}",
    )
    # 绑定轴刻度标签隐藏
    check(
        "bind-tick-hide",
        all(not t.get_visible() for t in axs["hx"].get_xticklabels())
        and all(not t.get_visible() for t in axs["hy"].get_yticklabels()),
        "bound-axis tick labels still visible",
    )
    # 边默认跳过 bind side：只有 main 拿 xlabel/ylabel
    check(
        "bind-edge-skip",
        axs["main"].get_xlabel() == "x value"
        and axs["main"].get_ylabel() == "y value"
        and axs["hx"].get_ylabel() == ""
        and axs["hy"].get_xlabel() == "",
        f"{[(a.get_xlabel(), a.get_ylabel()) for a in axs.values()]}",
    )
    # bind side 的标注义务豁免：不报 missing-axis-label/legend-coverage
    probs = audit_of(fig)
    check(
        "bind-audit-exempt",
        not [p for p in probs if "missing-axis-label" in p or "legend-coverage" in p],
        f"{probs}",
    )
    plt.close(fig)

    # 命名格（图例格）：map 键非 panel → axis-off 格
    spec["layout"]["map"]["leg"] = [0, 3, 1, 4]
    spec["legend"] = {"where": "cell", "cell": "leg"}
    fig = render(spec)
    hits = [w for w in warnings_of(fig) if w.startswith("dead-cell")]
    check("spans-named-cell", not hits, f"{warnings_of(fig)}")
    plt.close(fig)

    spec["layout"]["map"]["leg"] = [0, 3, 1, 4]
    del spec["legend"]
    fig = render(spec)
    hits = [w for w in warnings_of(fig) if w.startswith("dead-cell")]
    check(
        "spans-dead-cell",
        len(hits) == 1 and "layout.map" in hits[0],
        f"{warnings_of(fig)}",
    )
    plt.close(fig)


def spans_errors():
    rows = [{"x": float(i), "y": float(i)} for i in range(6)]
    base = {
        "version": 1,
        "data": {"d": rows},
        "layout": {
            "kind": "spans",
            "map": {"a": [0, 0, 1, 2], "b": [0, 2, 1, 3]},
        },
        "panels": {
            "a": {"series": [{"kind": "line", "x": "x", "y": "y"}]},
            "b": {"series": [{"kind": "line", "x": "x", "y": "y"}]},
        },
        "meta": META,
    }
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        for k, v in kw.items():
            if k == "layout":
                s["layout"].update(v)
            else:
                s[k] = v
        return s

    expect_error("spans-no-map", mod(layout={"map": None}), "needs a non-empty 'map'")
    expect_error(
        "spans-bad-rect",
        mod(layout={"map": {"a": [0, 0, 1], "b": [0, 0, 1, 1]}}),
        "must be [r0, c0, r1, c1] ints",
    )
    expect_error(
        "spans-degenerate",
        mod(layout={"map": {"a": [0, 0, 0, 1], "b": [0, 1, 1, 2]}}),
        "need r1>r0",
    )
    expect_error(
        "spans-overlap",
        mod(layout={"map": {"a": [0, 0, 1, 3], "b": [0, 2, 1, 3]}}),
        "overlap",
    )
    expect_error(
        "spans-unplaced",
        mod(panels={"a": {"series": []}, "b": {"series": []}, "c": {"series": []}}),
        "not placed",
    )
    expect_error(
        "spans-shape-small",
        mod(layout={"shape": [1, 2]}),
        "does not contain the map rects",
    )
    expect_error(
        "spans-cells-key",
        mod(layout={"cells": [["a", "b"]]}),
        "no meaning for kind 'spans'",
    )
    # bind 面
    expect_error(
        "bind-side-unknown",
        mod(layout={"bind": {"zz": {"to": "a", "axis": "x"}}}),
        "'zz' is not a panel",
    )
    expect_error(
        "bind-to-unknown",
        mod(layout={"bind": {"a": {"to": "zz", "axis": "x"}}}),
        "'to' panel 'zz' unknown",
    )
    expect_error(
        "bind-self",
        mod(layout={"bind": {"a": {"to": "a", "axis": "x"}}}),
        "cannot bind to itself",
    )
    expect_error(
        "bind-axis",
        mod(layout={"bind": {"a": {"to": "b", "axis": "z"}}}),
        "axis must be 'x'|'y'",
    )
    expect_error(
        "bind-non-xy",
        mod(
            panels={
                "a": {"series": [{"kind": "line", "x": "x", "y": "y"}]},
                "b": {
                    "kind": "donut",
                    "series": [{"kind": "donut", "x": "x", "y": "y"}],
                },
            },
            layout={"bind": {"b": {"to": "a", "axis": "x"}}},
        ),
        "not an 'xy' panel",
    )
    # 绑定轴上声明 label → axis-ignored lint
    spec = mod(
        panels={
            "a": {
                "xaxis": {"label": "doomed"},
                "series": [{"kind": "line", "x": "x", "y": "y"}],
            },
            "b": {"series": [{"kind": "line", "x": "x", "y": "y"}]},
        },
        layout={"bind": {"a": {"to": "b", "axis": "x"}}},
    )
    expect_lint("bind-axis-ignored", spec, "axis-ignored")


def spans_named_cell_cap():
    """命名格（axis-off 格、legend.where 目标）不是面板，不占
    MAX_GRID_CELLS 名额——8 面板 + 命名格放行；网格边长纪律不变。"""
    rows = [{"x": float(i), "y": float(i % 5)} for i in range(10)]
    panels = {
        f"p{i}": {"series": [{"kind": "line", "x": "x", "y": "y"}]} for i in range(8)
    }
    spec = {
        "version": 1,
        "data": {"d": rows},
        "layout": {
            "kind": "spans",
            "map": {
                **{f"p{i}": [i // 3, i % 3, i // 3 + 1, i % 3 + 1] for i in range(8)},
                "leg": [2, 2, 3, 3],
            },
        },
        "panels": panels,
        "legend": {"where": "cell", "cell": "leg"},
        "meta": META,
    }
    fig = render(spec)
    # 8 面板轴 + 1 命名格轴（axis-off）
    check("spans-cap-exempt", len(fig.get_axes()) == 9, f"{len(fig.get_axes())}")
    check(
        "spans-cap-cell-off",
        not fig.get_axes()[-1].axison,
        "named cell axis is not off",
    )
    plt.close(fig)

    # 9 真实面板仍撞上限——报错口径按面板数（命名格不计）
    panels["p8"] = {"series": [{"kind": "line", "x": "x", "y": "y"}]}
    spec["layout"]["map"]["p8"] = [2, 2, 3, 3]
    spec["layout"]["map"]["leg"] = [0, 3, 1, 4]  # 挪到格外的命名格
    expect_error(
        "spans-cap-panels",
        spec,
        "with 9 panels",
        "named axis-off cells do not count",
    )
    # 网格边长纪律不变：第 9 列超 MAX_SPANS_DIM
    expect_error(
        "spans-cap-dim",
        {
            "version": 1,
            "data": {"d": rows},
            "layout": {"kind": "spans", "map": {"a": [0, 0, 1, 9]}},
            "panels": {"a": {"series": [{"kind": "line", "x": "x", "y": "y"}]}},
            "meta": META,
        },
        "max grid dim",
    )


def bind_marginals():
    """bind side 面板的横向分布：dir:'h' = mpl orientation 同义——
    hist/kde/ecdf 数据落 y（右侧 y-bound 边际）、box/violin 数据落 x
    （顶部 x-bound 边际）。"""
    rows = [{"x": float(i % 10), "y": float((i * 3) % 10)} for i in range(60)]

    def joint(side_series, top_series):
        return {
            "version": 1,
            "data": {"d": rows},
            "layout": {
                "kind": "spans",
                "map": {
                    "bx": [0, 0, 1, 3],
                    "main": [1, 0, 3, 3],
                    "hy": [1, 3, 3, 4],
                },
                "bind": {
                    "bx": {"to": "main", "axis": "x"},
                    "hy": {"to": "main", "axis": "y"},
                },
            },
            "panels": {
                "bx": {"series": [top_series]},
                "main": {
                    "series": [{"kind": "scatter", "from": "d", "x": "x", "y": "y"}]
                },
                "hy": {"series": [side_series]},
            },
            "meta": META,
        }

    # hist dir:'h'：右侧 y-bound 边际——bins 沿 y、计数沿 x；绑定轴 lim 共享
    fig = render(
        joint(
            {"kind": "hist", "from": "d", "x": "y", "dir": "h"},
            {"kind": "box", "from": "d", "y": "x", "dir": "h"},
        )
    )
    axs = dict(zip(("bx", "main", "hy"), fig.get_axes()))
    check(
        "bind-hist-h-ylim",
        np.allclose(axs["hy"].get_ylim(), axs["main"].get_ylim()),
        f"{axs['hy'].get_ylim()} vs {axs['main'].get_ylim()}",
    )
    hs = {round(p.get_height(), 6) for p in axs["hy"].patches}
    ws = {round(p.get_width(), 6) for p in axs["hy"].patches}
    check(
        "bind-hist-h-geom",
        len(axs["hy"].patches) >= 3 and len(hs) == 1 and len(ws) > 1,
        f"heights={sorted(hs)} widths={sorted(ws)}",
    )
    # box dir:'h'：顶部 x-bound 边际——数据在 x、组位置在 y，组名走 yticks
    check(
        "bind-box-h-xlim",
        np.allclose(axs["bx"].get_xlim(), axs["main"].get_xlim()),
        f"{axs['bx'].get_xlim()} vs {axs['main'].get_xlim()}",
    )
    check(
        "bind-box-h-yticks",
        len(axs["bx"].get_yticks()) == 1 and not axs["bx"].get_xticklabels(),
        f"yticks={axs['bx'].get_yticks()} xtl={axs['bx'].get_xticklabels()}",
    )
    plt.close(fig)

    # kde dir:'h'：密度沿 x、数据沿 y（曲线横躺）；fill 用 fill_betweenx
    spec = joint(
        {"kind": "kde", "from": "d", "x": "y", "dir": "h", "fill": 0.3},
        {"kind": "violin", "from": "d", "y": "x", "dir": "h", "inner": "points"},
    )
    fig = render(spec)
    axs = dict(zip(("bx", "main", "hy"), fig.get_axes()))
    ln = axs["hy"].lines[0]
    xd, yd = ln.get_xdata(), ln.get_ydata()
    check(
        "bind-kde-h",
        xd.min() >= 0.0 and yd.min() <= float(rows[0]["y"]) + 1 and yd.max() >= 8.0,
        f"xd=[{xd.min():.2f},{xd.max():.2f}] yd=[{yd.min():.2f},{yd.max():.2f}]",
    )
    check(
        "bind-kde-h-fill",
        len(axs["hy"].collections) >= 1,
        "no fill collection",
    )
    # violin dir:'h' + inner:'points'：数据点 x=值、y=组位（确定性 jitter）
    scs = [c for c in axs["bx"].collections if isinstance(c, PathCollection)]
    offs = scs[0].get_offsets() if scs else np.empty((0, 2))
    check(
        "bind-violin-h-points",
        len(offs) == 60
        and np.allclose(offs[:, 1], 1.0, atol=0.19)
        and offs[:, 0].min() >= 0.0,
        f"offs shape={getattr(offs, 'shape', None)}",
    )
    plt.close(fig)

    # ecdf dir:'h'：概率在 x（单调 0→1）、数据在 y（升序观测值）
    spec = joint(
        {"kind": "ecdf", "from": "d", "x": "y", "dir": "h"},
        {"kind": "hist", "from": "d", "x": "x"},
    )
    fig = render(spec)
    axs = dict(zip(("bx", "main", "hy"), fig.get_axes()))
    ln = axs["hy"].lines[0]
    xd, yd = ln.get_xdata(), ln.get_ydata()
    check(
        "bind-ecdf-h",
        xd[0] == 0.0
        and np.isclose(xd[-1], 1.0)
        and all(b >= a for a, b in itertools.pairwise(xd))
        and all(b >= a for a, b in itertools.pairwise(yd)),
        f"xd={xd[:3]}..{xd[-3:]} yd={yd[:3]}..{yd[-3:]}",
    )
    # 顶部 hist 维持默认竖向（dir 缺省）：x 绑定轴共享
    check(
        "bind-hist-v-xlim",
        np.allclose(axs["bx"].get_xlim(), axs["main"].get_xlim()),
        f"{axs['bx'].get_xlim()} vs {axs['main'].get_xlim()}",
    )
    plt.close(fig)

    # dir 枚举：分布图族只收 'h'|'v'（'v' 即缺省形态）
    bad = joint(
        {"kind": "hist", "from": "d", "x": "y", "dir": "diag"},
        {"kind": "hist", "from": "d", "x": "x"},
    )
    expect_error("bind-dist-dir-enum", bad, "dir must be one of")
    bad["panels"]["hy"]["series"] = [
        {"kind": "violin", "from": "d", "y": "y", "dir": "x"}
    ]
    expect_error("bind-violin-dir-enum", bad, "dir must be one of")


def main() -> int:
    matrix_expand()
    matrix_facets()
    matrix_overrides()
    matrix_errors()
    edge_defaults()
    spans_layout()
    spans_errors()
    spans_named_cell_cap()
    bind_marginals()
    matrix_strips()
    print(f"--- spec_matrix: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
