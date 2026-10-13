#!/usr/bin/env python3
"""test_spec_waterfall.py — bar 瀑布图三件套测试。

- `bottom` 列：逐行浮动底边（含负增量下垂、缺值回落 baseline、barh/数值 x、
  与 stack 互斥、非数值/未知列 SpecError、不声明时行为不变）
- `connect`：相邻柱间隙边到边虚线（level = 前一根远端边），组过滤、props
  透传、fv-neutral gid、零命中/单类别 lint
- `labels` 扩展：`mode: value|delta|cum`（delta 带符号默认 fmt、cum 标
  bottom+v 远端边、负值柱标值推到远端边外侧）与 `groups` 组过滤

运行：uv run --with matplotlib --with numpy python scripts/test_spec_waterfall.py
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
from matplotlib.colors import to_hex
from matplotlib.container import BarContainer

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


def _bars(ax):
    return [c for c in ax.containers if isinstance(c, BarContainer)]


def _meta():
    return {"ledger": "l", "caption": "c"}


# pass@k 瀑布台账：y=带符号增量、base=run-in 累计；cum tips=[38.4,47.1,53,49.2,59]
WF_ROWS = [
    {"stage": "k=1", "base": 0, "d": 38.4},
    {"stage": "k=2", "base": 38.4, "d": 8.7},
    {"stage": "k=4", "base": 47.1, "d": 5.9},
    {"stage": "k=8", "base": 53.0, "d": -3.8},
    {"stage": "k=16", "base": 49.2, "d": 9.8},
]


def wf_spec(**series_kw):
    s = {
        "kind": "bar",
        "from": "wf",
        "x": "stage",
        "y": "d",
        "width": 0.55,
        "color": "vteal",
    }
    s.update(series_kw)
    return {
        "version": 1,
        "data": {"wf": [dict(r) for r in WF_ROWS]},
        "meta": _meta(),
        "series": [s],
    }


# ---------------------------------------------------------------- bottom 列


def bottom_column():
    fig = render(wf_spec(bottom="base"))
    ax = fig.get_axes()[0]
    bars = _bars(ax)
    check("bottom-1series", len(bars) == 1, f"{len(bars)}")
    geo = sorted(
        (round(p.get_y(), 3), round(p.get_height(), 3)) for p in bars[0].patches
    )
    want = sorted((r["base"], r["d"]) for r in WF_ROWS)
    check(
        "bottom-floating-geo",
        geo == [(round(b, 3), round(d, 3)) for b, d in want],
        f"geo={geo}",
    )
    plt.close(fig)

    # 缺值行回落 baseline（无声明时 0）
    spec = wf_spec(bottom="base", baseline=5)
    spec["data"]["wf"][2] = {"stage": "k=4", "d": 5.9}  # base 缺值
    fig = render(spec)
    ax = fig.get_axes()[0]
    ys = sorted(p.get_y() for p in _bars(ax)[0].patches)
    check("bottom-missing-fallback", 5.0 in ys, f"ys={ys}")
    plt.close(fig)

    # barh：bottom 换到 left
    fig = render(wf_spec(bottom="base", dir="h"))
    ax = fig.get_axes()[0]
    geo = sorted(
        (round(p.get_x(), 3), round(p.get_width(), 3)) for p in _bars(ax)[0].patches
    )
    check(
        "bottom-barh-left",
        geo == sorted((round(r["base"], 3), round(r["d"], 3)) for r in WF_ROWS),
        f"geo={geo}",
    )
    plt.close(fig)

    # 数值 x：柱心落真实坐标、bottom 照走列映射
    spec = wf_spec(bottom="base")
    for i, r in enumerate(spec["data"]["wf"]):
        r["x"] = [0.0, 0.5, 1.5, 3.0, 3.5][i]
        del r["stage"]
    spec["series"][0]["x"] = "x"
    fig = render(spec)
    ax = fig.get_axes()[0]
    xs = sorted(p.get_x() + p.get_width() / 2 for p in _bars(ax)[0].patches)
    check(
        "bottom-num-x",
        np.allclose(xs, [0.0, 0.5, 1.5, 3.0, 3.5]),
        f"xs={xs}",
    )
    plt.close(fig)

    # 字面数组 bottom（_vals 三形同口径）
    fig = render(wf_spec(bottom=[0, 38.4, 47.1, 53.0, 49.2]))
    ax = fig.get_axes()[0]
    ys = sorted(p.get_y() for p in _bars(ax)[0].patches)
    check(
        "bottom-literal-list",
        np.allclose(ys, [0, 38.4, 47.1, 49.2, 53.0]),
        f"ys={ys}",
    )
    plt.close(fig)


def bottom_compat():
    # 不声明 bottom：全部柱底 = baseline（行为不变）
    fig = render(wf_spec(baseline=2))
    ax = fig.get_axes()[0]
    ys = {p.get_y() for p in _bars(ax)[0].patches}
    check("bottom-absent-baseline", ys == {2}, f"ys={ys}")
    plt.close(fig)

    fig = render(wf_spec())
    ax = fig.get_axes()[0]
    ys = {p.get_y() for p in _bars(ax)[0].patches}
    check("bottom-absent-zero", ys == {0}, f"ys={ys}")
    plt.close(fig)


def bottom_errors():
    spec = wf_spec(bottom="base")
    spec["series"][0]["stack"] = True
    expect_error("bottom+stack", spec, "mutually", "stack")

    spec = wf_spec(bottom={"a": 1})
    expect_error("bottom-dict", spec, "column name", "literal list")

    spec = wf_spec(bottom="base")
    spec["data"]["wf"][0]["base"] = "low"
    expect_error("bottom-non-numeric", spec, "must be", "numeric")

    spec = wf_spec(bottom="nope")
    expect_error("bottom-unknown-col", spec, "not a data column")


# ------------------------------------------------------------------ connect


def connect_basic():
    fig = render(wf_spec(bottom="base", connect=True))
    ax = fig.get_axes()[0]
    check(
        "connect-count",
        len(ax.lines) == len(WF_ROWS) - 1,
        f"lines={len(ax.lines)}",
    )
    # 每段：level = 前一根远端边（cum_i），x 跨 [右缘_i, 左缘_{i+1}]
    got = sorted((ln.get_xdata().tolist(), ln.get_ydata().tolist()) for ln in ax.lines)
    want_x = [[i + 0.275, i + 1 - 0.275] for i in range(4)]
    want_y = [[38.4, 38.4], [47.1, 47.1], [53.0, 53.0], [49.2, 49.2]]
    ok = all(
        np.allclose(g[0], wx) and np.allclose(g[1], wy)
        for g, wx, wy in zip(got, want_x, want_y)
    )
    check("connect-geo", ok, f"segs={got}")
    check(
        "connect-neutral-gid",
        all(ln.get_gid() == "fv-neutral" for ln in ax.lines),
        f"gids={[ln.get_gid() for ln in ax.lines]}",
    )
    check(
        "connect-default-style",
        all(
            ln.get_linestyle() == "--" and np.isclose(ln.get_linewidth(), 0.8)
            for ln in ax.lines
        ),
        f"styles={[(ln.get_linestyle(), ln.get_linewidth()) for ln in ax.lines]}",
    )
    plt.close(fig)

    # props/lw/color 透传与 token 解析
    fig = render(
        wf_spec(
            bottom="base",
            connect={"color": "vcoral", "lw": 1.4, "props": {"linestyle": ":"}},
        )
    )
    ax = fig.get_axes()[0]
    import fvstyle as fv

    check(
        "connect-props",
        all(
            ln.get_linestyle() == ":"
            and np.isclose(ln.get_linewidth(), 1.4)
            and to_hex(ln.get_color()) == fv.HUES["vcoral"].lower()
            for ln in ax.lines
        ),
        f"lines={[(ln.get_linestyle(), ln.get_linewidth(), to_hex(ln.get_color())) for ln in ax.lines]}",
    )
    plt.close(fig)


def connect_groups():
    # pad+gain 堆叠编码的瀑布：connect.groups 只连 gain 段远端边 = cum_i
    rows = []
    for stage, pad, gain in [
        ("k=1", 0, 38.4),
        ("k=2", 38.4, 8.7),
        ("k=4", 47.1, 5.9),
        ("k=8", 53.0, 3.8),
        ("k=16", 56.8, 2.2),
    ]:
        rows.append({"stage": stage, "seg": "pad", "v": pad})
        rows.append({"stage": stage, "seg": "gain", "v": gain})
    spec = {
        "version": 1,
        "data": {"wf": rows},
        "meta": _meta(),
        "series": [
            {
                "kind": "bar",
                "from": "wf",
                "x": "stage",
                "y": "v",
                "by": {"field": "seg", "order": ["pad", "gain"]},
                "stack": True,
                "width": 0.55,
                "connect": {"groups": ["gain"]},
            }
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    levels = sorted(ln.get_ydata()[0] for ln in ax.lines)
    check(
        "connect-stack-groups",
        len(ax.lines) == 4 and np.allclose(levels, [38.4, 47.1, 53.0, 56.8]),
        f"lines={len(ax.lines)} levels={levels}",
    )
    plt.close(fig)

    # 组过滤零命中 → axis-ignored
    spec["series"][0]["connect"] = {"groups": ["nope"]}
    expect_lint("connect-groups-miss", spec, "axis-ignored")

    # 单类别 → axis-ignored
    spec = {
        "version": 1,
        "data": {"d": [{"x": "a", "y": 1.0}]},
        "meta": _meta(),
        "series": [{"kind": "bar", "x": "x", "y": "y", "connect": True}],
    }
    expect_lint("connect-single-cat", spec, "axis-ignored")


def connect_errors():
    expect_error("connect-str", wf_spec(connect="yes"), "connect", "object")
    expect_error(
        "connect-key",
        wf_spec(connect={"bogus": 1}),
        "unknown keys",
        "bogus",
    )
    expect_error(
        "connect-groups-str",
        wf_spec(connect={"groups": "gain"}),
        "groups",
        "list",
    )


# -------------------------------------------------------------------- labels


def labels_modes():
    # delta：带符号增量、负值柱标值推外侧
    fig = render(wf_spec(bottom="base", labels={"mode": "delta"}))
    ax = fig.get_axes()[0]
    texts = [t.get_text() for t in ax.texts]
    check(
        "labels-delta-texts",
        texts == ["+38.4", "+8.7", "+5.9", "-3.8", "+9.8"],
        f"texts={texts}",
    )
    offs = {t.get_text(): t.xyann for t in ax.texts}
    check(
        "labels-delta-neg-outward",
        offs["-3.8"][1] < 0 and offs["+8.7"][1] > 0,
        f"offs={offs}",
    )
    plt.close(fig)

    # cum：标 bottom+v 远端边
    fig = render(wf_spec(bottom="base", labels={"mode": "cum", "fmt": "{:.4g}"}))
    ax = fig.get_axes()[0]
    texts = [t.get_text() for t in ax.texts]
    check(
        "labels-cum-texts",
        texts == ["38.4", "47.1", "53", "49.2", "59"],
        f"texts={texts}",
    )
    plt.close(fig)

    # value（默认）：既有行为不变——标 y 原值、无强制符号
    fig = render(wf_spec(bottom="base", labels={"fmt": "{:.4g}"}))
    ax = fig.get_axes()[0]
    texts = [t.get_text() for t in ax.texts]
    check(
        "labels-value-texts",
        texts == ["38.4", "8.7", "5.9", "-3.8", "9.8"],
        f"texts={texts}",
    )
    plt.close(fig)


def labels_groups():
    rows = []
    for stage, pad, gain in [
        ("k=1", 0, 38.4),
        ("k=2", 38.4, 8.7),
        ("k=4", 47.1, 5.9),
    ]:
        rows.append({"stage": stage, "seg": "pad", "v": pad})
        rows.append({"stage": stage, "seg": "gain", "v": gain})
    spec = {
        "version": 1,
        "data": {"wf": rows},
        "meta": _meta(),
        "series": [
            {
                "kind": "bar",
                "from": "wf",
                "x": "stage",
                "y": "v",
                "by": {"field": "seg", "order": ["pad", "gain"]},
                "stack": True,
                "labels": {"groups": ["gain"], "fmt": "{:.3g}"},
            }
        ],
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    texts = sorted(t.get_text() for t in ax.texts)
    check(
        "labels-groups-filter",
        texts == ["38.4", "5.9", "8.7"],
        f"texts={texts}",
    )
    plt.close(fig)

    # 零命中 → axis-ignored 且无标值
    spec["series"][0]["labels"] = {"groups": ["nope"]}
    fig = render(spec)
    ax = fig.get_axes()[0]
    hits = [w for w in warnings_of(fig) if w.startswith("axis-ignored")]
    check(
        "labels-groups-miss",
        bool(hits) and len(ax.texts) == 0,
        f"warnings={warnings_of(fig)} texts={len(ax.texts)}",
    )
    plt.close(fig)


def labels_errors():
    expect_error("labels-mode", wf_spec(labels={"mode": "bogus"}), "mode", "bogus")
    expect_error(
        "labels-groups-str",
        wf_spec(labels={"groups": "gain"}),
        "groups",
        "list",
    )


# ------------------------------------------------------------------ 端到端


def waterfall_e2e():
    spec = wf_spec(bottom="base", connect=True, labels={"mode": "delta"})
    spec["yaxis"] = {"label": "pass@k (%)", "lim": {"bottom": 0}}
    spec["xaxis"] = {"label": "samples $k$"}
    spec["grid"] = "y-only"
    fig = render(spec)
    probs = audit_of(fig)
    # 柱顶标签 headroom 由 fvspec 的 _reserve_label_headroom 实测补齐——
    # '+9.8' 越顶 / '-3.8' 触柱两条历史张力已修，无豁免
    check("waterfall-e2e-audit", not probs, f"audit={probs}")
    plt.close(fig)


def main() -> int:
    bottom_column()
    bottom_compat()
    bottom_errors()
    connect_basic()
    connect_groups()
    connect_errors()
    labels_modes()
    labels_groups()
    labels_errors()
    waterfall_e2e()
    print(f"--- waterfall: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
