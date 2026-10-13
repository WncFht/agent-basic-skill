#!/usr/bin/env python3
"""test_spec_sig.py — sig 显著性括号与 bar connect.label 的隔离测试。

- sig：每行 {a,b,y} + 'p'|'text' 恰一；挂点收数值 x 或类别名（同面板
  bar 类目序 / box、violin 组位）；p→星号映射 p<.001/*** p<.01/**
  p<.05/* 否则 'ns'；tick/pad 缺省随 y 量程自适应；color token /
  props / textprops 覆写口；全 artist fv-neutral——不算系列、不进
  legend-coverage、不产图例条目
- sig SpecError 面：行缺字段、p+text 互斥与全缺、非数值 p/y、非串
  text、坏锚点类型、未知类别名、死键（label/by/legend/ls…）、坏
  tick/pad/textprops、radar/donut 面板拒绝、未知系列键
- sig-outside-axes lint：梁出窗 / 顶沿无余量告警；正常落位不报
- connect.label：图例幽灵条目克隆 connector 样式（color/ls/lw）、
  panel/figure 图例都收；无图例 → empty-legend lint；groups 零命中
  不出幽灵；非串 SpecError

运行：uv run --with matplotlib --with numpy python scripts/test_spec_sig.py
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
from matplotlib.colors import to_hex
from matplotlib.lines import Line2D

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

BAR_ROWS = [
    {"x": "A", "y": 3.0},
    {"x": "B", "y": 4.2},
    {"x": "C", "y": 3.6},
]
SIG_ROWS = [
    {"a": "A", "b": "B", "y": 5.0, "p": 0.004},
    {"a": "B", "b": "C", "y": 5.8, "p": 0.0004},
    {"a": "A", "b": "C", "y": 6.6, "p": 0.4},
]


def sig_spec(sig_rows=SIG_ROWS, bar_rows=BAR_ROWS, sig_kw=None, **kw):
    s = {"kind": "sig", "from": "sig"}
    if sig_kw:
        s.update(sig_kw)
    spec = {
        "version": 1,
        "data": {"d": [dict(r) for r in bar_rows], "sig": [dict(r) for r in sig_rows]},
        "xaxis": {"label": "grp"},
        # lim [0,8] 给最顶括号留足字高余量——auto-ylim 会贴梁顶触发 lint
        "yaxis": {"label": "score", "lim": [0, 8.0]},
        "meta": META,
        "series": [
            {"kind": "bar", "from": "d", "x": "x", "y": "y", "width": 0.55},
            s,
        ],
    }
    spec.update(kw)
    return spec


def _bracket_lines(ax):
    """fv-neutral 的 4 点 Π 形折线（区分 connect/ghost：均 4 顶点）。"""
    return [
        ln
        for ln in ax.lines
        if ln.get_gid() == "fv-neutral" and len(ln.get_xdata()) == 4
    ]


# --------------------------------------------------------------------- sig


def sig_basic():
    fig = render(sig_spec())
    ax = fig.get_axes()[0]
    lines = _bracket_lines(ax)
    check("sig-line-count", len(lines) == 3, f"{len(lines)}")
    # 第一条：a='A'→0, b='B'→1，梁 y=5.0，垂足向下
    xd, yd = lines[0].get_xdata(), lines[0].get_ydata()
    check(
        "sig-cat-geo",
        list(xd) == [0, 0, 1, 1] and yd[1] == yd[2] == 5.0 and yd[0] == yd[3] < 5.0,
        f"x={list(xd)} y={list(yd)}",
    )
    texts = [t.get_text() for t in ax.texts]
    check("sig-stars", texts == ["**", "***", "ns"], f"{texts}")
    fs = [t.get_fontsize() for t in ax.texts]
    check("sig-ns-smaller", fs[2] < fs[0], f"fs={fs}")
    check(
        "sig-text-anchor",
        all(t.get_ha() == "center" and t.get_va() == "bottom" for t in ax.texts),
        f"{[(t.get_ha(), t.get_va()) for t in ax.texts]}",
    )
    probs = audit_of(fig)
    check("sig-audit-clean", not probs and not warnings_of(fig), f"{probs[:3]}")
    plt.close(fig)


def sig_anchors():
    # a>b 乱序自动左→右
    fig = render(sig_spec(sig_rows=[{"a": "C", "b": "A", "y": 5.0, "p": 0.01}]))
    ax = fig.get_axes()[0]
    ln = _bracket_lines(ax)[0]
    check(
        "sig-swap",
        list(ln.get_xdata()) == [0, 0, 2, 2],
        f"{list(ln.get_xdata())}",
    )
    plt.close(fig)

    # 数值挂点直接是 x 坐标
    fig = render(sig_spec(sig_rows=[{"a": 0.3, "b": 1.7, "y": 5.0, "text": "Δ"}]))
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-num-anchor",
        list(ln.get_xdata()) == [0.3, 0.3, 1.7, 1.7],
        f"{list(ln.get_xdata())}",
    )
    plt.close(fig)

    # 数值 x 柱：类别名按真实坐标解（'0.5' 经 _norm_key ≡ 0.5）
    spec = sig_spec(
        sig_rows=[{"a": "0.5", "b": "1.5", "y": 5.0, "p": 0.02}],
        bar_rows=[{"x": 0.5, "y": 3.0}, {"x": 1.5, "y": 4.0}],
    )
    fig = render(spec)
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-numx-bar",
        list(ln.get_xdata()) == [0.5, 0.5, 1.5, 1.5],
        f"{list(ln.get_xdata())}",
    )
    check("sig-numx-star", fig.get_axes()[0].texts[0].get_text() == "*")
    plt.close(fig)

    # box/violin 组位：组键与 label 都收，位置 = 1..n
    spec = {
        "version": 1,
        "data": {
            "d": [
                {"g": "ctl", "v": 1.0},
                {"g": "ctl", "v": 2.0},
                {"g": "trt", "v": 3.0},
                {"g": "trt", "v": 4.0},
            ],
            "sig": [{"a": "ctl", "b": "trt", "y": 5.0, "p": 0.0009}],
        },
        "xaxis": {"label": "grp"},
        "yaxis": {"label": "v"},
        "meta": META,
        "series": [
            {"kind": "box", "from": "d", "y": "v", "by": "g"},
            {"kind": "sig", "from": "sig"},
        ],
    }
    fig = render(spec)
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-box-pos",
        list(ln.get_xdata()) == [1, 1, 2, 2],
        f"{list(ln.get_xdata())}",
    )
    check(
        "sig-box-star",
        fig.get_axes()[0].texts[0].get_text() == "***",
    )
    plt.close(fig)


def sig_group_anchor():
    """'槽位:组值' 复合挂点：命中 by 扇出柱时解到组内 dodge 柱心。"""
    rows = [
        {"x": "A", "g": "ctl", "y": 3.0},
        {"x": "A", "g": "trt", "y": 4.0},
        {"x": "B", "g": "ctl", "y": 3.4},
        {"x": "B", "g": "trt", "y": 4.4},
    ]

    def spec(sig_rows):
        return {
            "version": 1,
            "data": {"d": [dict(r) for r in rows], "sig": sig_rows},
            "yaxis": {"label": "score", "lim": [0, 8.0]},
            "meta": META,
            "series": [
                {"kind": "bar", "from": "d", "x": "x", "y": "y", "by": "g"},
                {"kind": "sig", "from": "sig"},
            ],
        }

    # n=2 → width=0.4，off=(gi-0.5)*0.4：ctl(gi=0)→-0.2，trt→+0.2
    fig = render(spec([{"a": "A:ctl", "b": "A:trt", "y": 5.0, "p": 0.02}]))
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-dodge-anchor",
        list(ln.get_xdata()) == [-0.2, -0.2, 0.2, 0.2],
        f"{list(ln.get_xdata())}",
    )
    plt.close(fig)

    # 跨槽位的复合挂点
    fig = render(spec([{"a": "A:trt", "b": "B:ctl", "y": 5.0, "text": "x"}]))
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-dodge-cross-slot",
        list(ln.get_xdata()) == [0.2, 0.2, 0.8, 0.8],
        f"{list(ln.get_xdata())}",
    )
    plt.close(fig)

    # 整串是类别名时优先整串（不与复合形抢）
    fig = render(spec([{"a": "A", "b": "B", "y": 5.0, "p": 0.02}]))
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-plain-cat-still-center",
        list(ln.get_xdata()) == [0, 0, 1, 1],
        f"{list(ln.get_xdata())}",
    )
    plt.close(fig)

    # 组值命中但槽位不归该 bar / 组值不在任何 by 扇出 → SpecError
    expect_error(
        "sig-dodge-no-group",
        spec([{"a": "A:zzz", "b": "B", "y": 5.0, "p": 0.02}]),
        "A:zzz",
        "dodged bar",
    )
    expect_error(
        "sig-dodge-no-bar",
        sig_spec(sig_rows=[{"a": "A:ctl", "b": "B", "y": 5.0, "p": 0.02}]),
        "A:ctl",
        "dodged bar",
    )


def sig_style():
    # color token + textprops + tick/pad 显式值
    spec = sig_spec(
        sig_rows=[{"a": "A", "b": "B", "y": 5.0, "text": "Δ=+1.2"}],
        sig_kw={
            "color": "vcoral",
            "tick": 0.3,
            "pad": 0.15,
            "textprops": {"fontsize": 12},
        },
    )
    fig = render(spec)
    ax = fig.get_axes()[0]
    ln = _bracket_lines(ax)[0]
    check(
        "sig-color-token",
        to_hex(ln.get_color()) == fv.HUES["vcoral"].lower(),
        f"{to_hex(ln.get_color())}",
    )
    check(
        "sig-tick-pad",
        list(ln.get_ydata()) == [4.7, 5.0, 5.0, 4.7]
        and np.isclose(ax.texts[0].get_position()[1], 5.15),
        f"y={list(ln.get_ydata())} ty={ax.texts[0].get_position()}",
    )
    check(
        "sig-text-literal",
        ax.texts[0].get_text() == "Δ=+1.2" and ax.texts[0].get_fontsize() == 12,
        f"{ax.texts[0].get_text()!r} fs={ax.texts[0].get_fontsize()}",
    )
    plt.close(fig)

    # props → bracket Line2D（linestyle 别名不撞车）
    spec = sig_spec(
        sig_rows=[{"a": "A", "b": "B", "y": 5.0, "p": 0.02}],
        sig_kw={"props": {"linestyle": ":", "linewidth": 1.6}},
    )
    fig = render(spec)
    ln = _bracket_lines(fig.get_axes()[0])[0]
    check(
        "sig-props-win",
        ln.get_linestyle() == ":" and np.isclose(ln.get_linewidth(), 1.6),
        f"{ln.get_linestyle()} lw={ln.get_linewidth()}",
    )
    plt.close(fig)

    # where 过滤子集
    spec = sig_spec(sig_kw={"where": {"p": {"$lt": 0.01}}})
    fig = render(spec)
    check(
        "sig-where",
        len(_bracket_lines(fig.get_axes()[0])) == 2,
        f"{len(_bracket_lines(fig.get_axes()[0]))}",
    )
    plt.close(fig)


def sig_errors():
    def ser(rows=None, **kw):
        rows = SIG_ROWS if rows is None else rows
        return sig_spec(sig_rows=rows, sig_kw=kw)

    expect_error(
        "sig-missing-y",
        ser(rows=[{"a": "A", "b": "B", "p": 0.01}]),
        "missing",
        "'y'",
    )
    expect_error(
        "sig-p+text",
        ser(rows=[{"a": "A", "b": "B", "y": 5, "p": 0.01, "text": "x"}]),
        "exactly one",
    )
    expect_error(
        "sig-neither",
        ser(rows=[{"a": "A", "b": "B", "y": 5}]),
        "exactly one",
    )
    expect_error(
        "sig-p-nonnum",
        ser(rows=[{"a": "A", "b": "B", "y": 5, "p": "low"}]),
        "'p' must be a number",
    )
    expect_error(
        "sig-text-nonstr",
        ser(rows=[{"a": "A", "b": "B", "y": 5, "text": 3}]),
        "'text' must be a string",
    )
    expect_error(
        "sig-y-nonnum",
        ser(rows=[{"a": "A", "b": "B", "y": "top", "p": 0.01}]),
        "'y' must be a number",
    )
    expect_error(
        "sig-anchor-list",
        ser(rows=[{"a": ["A"], "b": "B", "y": 5, "p": 0.01}]),
        "'a' must be",
    )
    expect_error(
        "sig-unknown-cat",
        ser(rows=[{"a": "A", "b": "zzz", "y": 5, "p": 0.01}]),
        "neither a numeric",
        "known category",
    )
    expect_error("sig-dead-label", ser(label="x"), "'label' does not apply")
    expect_error("sig-dead-by", ser(by="x"), "'by' does not apply")
    expect_error("sig-dead-ls", ser(ls="--"), "'ls' does not apply")
    expect_error("sig-tick-neg", ser(tick=-1), "tick must be a non-negative")
    expect_error("sig-pad-bad", ser(pad="x"), "pad must be a non-negative")
    expect_error("sig-textprops-bad", ser(textprops=[1]), "textprops must be")
    expect_error("sig-bad-key", ser(zz=1), "unknown keys")
    expect_error(
        "sig-radar",
        {
            "version": 1,
            "kind": "radar",
            "dims": ["a", "b", "c"],
            "data": {"sig": [{"a": 0, "b": 1, "y": 5, "p": 0.01}]},
            "series": [{"kind": "sig", "from": "sig"}],
            "meta": META,
        },
        "not allowed in",
    )


def sig_lints():
    # 梁出 y 窗（显式 lim）
    expect_lint(
        "sig-outside",
        sig_spec(yaxis={"label": "score", "lim": [0, 6.0]}),
        "sig-outside-axes",
    )
    # 贴顶沿无字高余量
    expect_lint(
        "sig-headroom",
        sig_spec(
            sig_rows=[{"a": "A", "b": "B", "y": 5.95, "p": 0.01}],
            yaxis={"label": "score", "lim": [0, 6.0]},
        ),
        "sig-outside-axes",
    )
    # 正常落位不报
    expect_lint(
        "sig-fits",
        sig_spec(yaxis={"label": "score", "lim": [0, 8.0]}),
        "sig-outside-axes",
        present=False,
    )
    # where 滤空 → empty-series
    spec = sig_spec(sig_kw={"where": {"p": {"$lt": 0}}})
    expect_lint("sig-empty", spec, "empty-series")
    # y2 面板：括号画在 twin 上
    spec = {
        "version": 1,
        "data": {
            "d": [{"x": "A", "y": 3.0}, {"x": "B", "y": 4.2}],
            "d2": [{"x": "A", "y": 30.0}, {"x": "B", "y": 42.0}],
            "sig": [{"a": "A", "b": "B", "y": 50.0, "p": 0.01}],
        },
        "y2": {"label": "alt"},
        "xaxis": {"label": "grp"},
        "yaxis": {"label": "score"},
        "meta": META,
        "series": [
            {"kind": "bar", "from": "d", "x": "x", "y": "y"},
            {"kind": "line", "from": "d2", "x": "x", "y": "y", "axis": "y2"},
            {"kind": "sig", "from": "sig", "axis": "y2"},
        ],
    }
    fig = render(spec)
    ax, ax2 = fig.get_axes()[0], fig.get_axes()[1]
    check(
        "sig-y2",
        _bracket_lines(ax2) and not _bracket_lines(ax),
        f"ax={len(_bracket_lines(ax))} ax2={len(_bracket_lines(ax2))}",
    )
    plt.close(fig)


# ----------------------------------------------------------- connect.label

WF_ROWS = [
    {"stage": "k=1", "base": 0.0, "d": 38.4},
    {"stage": "k=2", "base": 38.4, "d": 8.7},
    {"stage": "k=4", "base": 47.1, "d": 5.9},
]


def conn_spec(connect=None, **kw):
    spec = {
        "version": 1,
        "data": {"wf": [dict(r) for r in WF_ROWS]},
        "xaxis": {"label": "k"},
        "yaxis": {"label": "pass@k"},
        "meta": META,
        "series": [
            {
                "kind": "bar",
                "from": "wf",
                "x": "stage",
                "y": "d",
                "bottom": "base",
                "width": 0.55,
                "connect": connect if connect is not None else {"label": "run-in"},
            }
        ],
    }
    spec.update(kw)
    return spec


def _conn_lines(ax):
    """connect 段 = fv-neutral 2 点线（ghost 是 0 点 Line2D）。"""
    return [
        ln
        for ln in ax.lines
        if ln.get_gid() == "fv-neutral" and len(ln.get_xdata()) == 2
    ]


def connect_label():
    # panel legend 收幽灵条目，样式克隆 connector
    fig = render(conn_spec(legend=True))
    ax = fig.get_axes()[0]
    leg = ax.get_legend()
    check("conn-legend-present", leg is not None)
    if leg:
        texts = [t.get_text() for t in leg.get_texts()]
        check("conn-legend-entry", "run-in" in texts, f"{texts}")
        ghost = next((h for h in leg.legend_handles if h.get_label() == "run-in"), None)
        segs = _conn_lines(ax)
        ok = (
            ghost is not None
            and segs
            and isinstance(ghost, Line2D)
            and ghost.get_linestyle() == segs[0].get_linestyle()
            and np.isclose(ghost.get_linewidth(), segs[0].get_linewidth())
            and to_hex(ghost.get_color()) == to_hex(segs[0].get_color())
        )
        check(
            "conn-ghost-style",
            bool(ok),
            f"ghost={ghost} seg={segs[0].get_linestyle() if segs else None}",
        )
    check(
        "conn-ghost-neutral",
        any(
            ln.get_gid() == "fv-neutral" and len(ln.get_xdata()) == 0 for ln in ax.lines
        ),
        f"{[(ln.get_gid(), len(ln.get_xdata())) for ln in ax.lines]}",
    )
    probs = audit_of(fig)
    check("conn-label-audit", not probs, f"{probs[:3]}")
    plt.close(fig)

    # figure legend 同样收得到
    fig = render(conn_spec(legend={"where": "below"}))
    flegs = fig.legends
    check(
        "conn-figlegend",
        flegs and "run-in" in [t.get_text() for t in flegs[0].get_texts()],
        f"{fig.legends}",
    )
    plt.close(fig)

    # 自定义 connector 样式透传到幽灵
    fig = render(
        conn_spec(
            connect={
                "label": "run-in",
                "color": "vcoral",
                "ls": ":",
                "lw": 1.5,
            },
            legend=True,
        )
    )
    ax = fig.get_axes()[0]
    leg = ax.get_legend()
    ghost = next((h for h in leg.legend_handles if h.get_label() == "run-in"), None)
    check(
        "conn-ghost-props",
        ghost is not None
        and ghost.get_linestyle() == ":"
        and np.isclose(ghost.get_linewidth(), 1.5)
        and to_hex(ghost.get_color()) == fv.HUES["vcoral"].lower(),
        f"{ghost}",
    )
    plt.close(fig)


def connect_label_lints():
    # 无图例 → empty-legend（label 静默蒸发预警）
    expect_lint("conn-label-noleg", conn_spec(), "empty-legend")
    # legend 声明后不再报
    expect_lint(
        "conn-label-leg",
        conn_spec(legend=True),
        "empty-legend",
        present=False,
    )
    # groups 零命中：无幽灵（axis-ignored 由既有路径报），empty-legend 不误报
    spec = conn_spec(connect={"groups": ["nope"], "label": "x"}, legend=True)
    fig = render(spec)
    ax = fig.get_axes()[0]
    ghosts = [
        ln
        for ln in ax.lines
        if ln.get_gid() == "fv-neutral" and len(ln.get_xdata()) == 0
    ]
    check(
        "conn-label-miss-noghost",
        not ghosts
        and any(w.startswith("axis-ignored") for w in warnings_of(fig))
        and not any(w.startswith("empty-legend") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)
    # <2 类别：connector 空转 → 幽灵不出现
    spec = conn_spec(
        connect={"label": "run-in"},
        legend=True,
    )
    spec["data"]["wf"] = [{"stage": "k=1", "base": 0.0, "d": 38.4}]
    fig = render(spec)
    ghosts = [
        ln
        for ln in fig.get_axes()[0].lines
        if ln.get_gid() == "fv-neutral" and len(ln.get_xdata()) == 0
    ]
    check("conn-label-single-noghost", not ghosts, f"{warnings_of(fig)}")
    plt.close(fig)


def connect_label_errors():
    expect_error(
        "conn-label-nonstr",
        conn_spec(connect={"label": 5}),
        "connect.label must be a string",
    )
    expect_error(
        "conn-label-badkey",
        conn_spec(connect={"label": "x", "zz": 1}),
        "unknown keys",
    )


def main() -> int:
    sig_basic()
    sig_anchors()
    sig_group_anchor()
    sig_style()
    sig_errors()
    sig_lints()
    connect_label()
    connect_label_lints()
    connect_label_errors()
    print(f"--- spec_sig: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
