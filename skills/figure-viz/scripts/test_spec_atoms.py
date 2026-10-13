#!/usr/bin/env python3
"""test_spec_atoms.py — 探针驱动的 spec 原子补全与 lint 新面测试。

覆盖（与 references/charts/spec.md 同步）：
- scatter/donut 一等 `edgecolor` 走调色板 token（此前原样进 mpl 炸 ValueError）
- layout 命名死格 NullLocator——不再带 [0,1] 幻影刻度撞图例
- heat annotate 字色按格底 WCAG 双向对比取大（seq/div 最深格切白字）
- 新 lint：note-outside-axes / occluded-by-heat
- `output.bbox` 缺省统一 null（任何 `size` 形态都不再默认 tight 重裁）；显式 `bbox:'tight'` + `size` 才告警
- `xaxis`/`yaxis` 的 `tick_rotation` 与 `tick_stride`（类别轴样式出口）
- scatter 类别 y：非数值列 → 首见序槽位 + 自动刻度标签
- ref `dir:'diag'|'identity'` 对角线 + `dir` 枚举响亮校验
- note `at:{x,y}` 逐行扇出 + `{field}`/`{field:fmt}` 行内替换
- `errprops` 误差棒造型透传（capsize/elinewidth/capthick）
- band 无 `of` 独立填充（自带 x/lo/hi）
- panel `aspect:'equal'`
- bar 数值 x：柱落真实坐标（校准图分箱中心）

运行：uv run --with matplotlib --with numpy python scripts/test_spec_atoms.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.container import ErrorbarContainer
from matplotlib.ticker import FixedLocator

SKILL_DIR = Path(__file__).resolve().parents[1]


def render(spec, base_dir=None):
    return fvspec.render(spec, base_dir=base_dir or SKILL_DIR / "scripts" / "examples")


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


def _data_scatter(spec_extra=None, series_extra=None):
    spec = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
        "series": [{"kind": "scatter", "x": "x", "y": "y"}],
    }
    spec.update(spec_extra or {})
    spec["series"][0].update(series_extra or {})
    return spec


# -------------------------------------------------- edgecolor token


def edgecolor_tokens():
    """item 1：一等 edgecolor 过 token 解析；mpl 原生色名放行；坏串响亮报错。"""
    fig = render(_data_scatter(series_extra={"edgecolor": "vink"}))
    sc = next(c for c in fig.get_axes()[0].collections if c.get_gid() != "fv-neutral")
    got = sc.get_edgecolor()
    check(
        "edgecolor-token-scatter",
        len(got) and np.allclose(got[0][:3], mpl.colors.to_rgb(fv.NEUTRALS["vink"])),
        f"edge={got}",
    )
    plt.close(fig)
    fig = render(
        {
            "version": 1,
            "kind": "donut",
            "data": {"d": [{"x": "a", "y": 1}, {"x": "b", "y": 2}]},
            "series": [{"kind": "donut", "x": "x", "y": "y", "edgecolor": "vteal"}],
        }
    )
    w = fig.get_axes()[0].patches[0]
    check(
        "edgecolor-token-donut",
        np.allclose(
            np.asarray(w.get_edgecolor())[:3], mpl.colors.to_rgb(fv.HUES["vteal"])
        ),
        f"edge={w.get_edgecolor()}",
    )
    plt.close(fig)
    # mpl 原生名（white/none）放行——不是 token 也不该炸
    fig = render(_data_scatter(series_extra={"edgecolor": "none"}))
    plt.close(fig)
    expect_error(
        "edgecolor-bad-token",
        _data_scatter(series_extra={"edgecolor": "vinl"}),
        "edgecolor",
    )


# -------------------------------------------------- layout 死格


def dead_cells():
    """item 2：命名死格 NullLocator——无幻影刻度，legend 落格不再被撞。"""
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}]},
            "layout": {"cells": [["a", "corner"]]},
            "panels": {
                "a": {"series": [{"kind": "line", "x": "x", "y": "y", "label": "run"}]}
            },
            "legend": {"where": "cell", "cell": "corner", "loc": "center"},
        }
    )
    cell_ax = fig.get_axes()[-1]
    check(
        "dead-cell-hosts-legend",
        cell_ax.get_legend() is not None,
        "corner cell lost the legend",
    )
    check(
        "dead-cell-no-ticks",
        not cell_ax.xaxis.get_majorticklabels()
        and not cell_ax.yaxis.get_majorticklabels(),
        f"xticklabels={[t.get_text() for t in cell_ax.xaxis.get_majorticklabels()]}",
    )
    probs = audit_of(fig)
    check("dead-cell-no-collide", not any("collide" in p for p in probs), f"{probs}")
    plt.close(fig)


# -------------------------------------------------- heat annotate 对比度


def heat_annotate_ink():
    """item 3：最深 seq 格（vteal 端点）白字、最浅格 vink——双向 WCAG 取大。"""
    fig = render(
        {
            "version": 1,
            "series": [
                {
                    "kind": "heat",
                    "matrix": [[0.0, 1.0]],
                    "annotate": True,
                    "cbar": False,
                }
            ],
        }
    )
    colors = {t.get_text(): t.get_color() for t in fig.get_axes()[0].texts}
    check(
        "heat-ann-deep-white",
        colors.get("1") == "white",
        f"deep cell color {colors.get('1')}",
    )
    check(
        "heat-ann-light-ink",
        colors.get("0") == fv.NEUTRALS["vink"],
        f"light cell color {colors.get('0')}",
    )
    plt.close(fig)


# -------------------------------------------------- 新 lint


def note_outside_lint():
    """item 4：纯 data 坐标 note 落点出轴 → lint；混合坐标默认不 clip 不报。"""
    base = {
        "version": 1,
        "data": {"d": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    expect_lint(
        "note-outside",
        dict(
            base,
            series=base["series"]
            + [{"kind": "note", "at": [5.0, 5.0], "text": "gone"}],
        ),
        "note-outside-axes",
    )
    expect_lint(
        "note-inside",
        dict(
            base,
            series=base["series"]
            + [{"kind": "note", "at": [0.5, 0.5], "text": "here"}],
        ),
        "note-outside-axes",
        present=False,
    )
    expect_lint(
        "note-outside-mixed-units",
        dict(
            base,
            series=base["series"]
            + [
                {
                    "kind": "note",
                    "at": [1.0, 5.0],
                    "units": ["axes", "data"],
                    "text": "ok",
                }
            ],
        ),
        "note-outside-axes",
        present=False,
    )


def occluded_by_heat_lint():
    """item 5：span 画在 heat 前被不透明 pcolormesh 盖死 → lint；后置/提 zorder 不报。"""
    data = {"d": [{"x": "a", "y": "b", "z": 1.0}]}
    heat = {"kind": "heat", "x": "x", "y": "y", "z": "z", "cbar": False}
    span = {"kind": "span", "dir": "v", "at": [0, 1]}
    expect_lint(
        "span-before-heat",
        {"version": 1, "data": data, "series": [span, heat]},
        "occluded-by-heat",
    )
    expect_lint(
        "span-after-heat",
        {"version": 1, "data": data, "series": [heat, span]},
        "occluded-by-heat",
        present=False,
    )
    expect_lint(
        "span-high-zorder",
        {
            "version": 1,
            "data": data,
            "series": [dict(span, zorder=5), heat],
        },
        "occluded-by-heat",
        present=False,
    )


# -------------------------------------------------- size/bbox 默认


def bbox_defaults():
    """item 6：`bbox` 缺省统一 null（任何 size 形态不重裁）；显式 tight + size 维持 lint。"""
    with tempfile.TemporaryDirectory() as td:
        base = {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
            "output": {"path": "f.png"},
        }
        fig = render(dict(base, size={"slot": "half"}), base_dir=td)
        check(
            "bbox-dict-slot-default-null",
            not any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)
        fig = render(dict(base, size="half"), base_dir=td)
        check(
            "bbox-str-size-default-null",
            not any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)
        fig = render(
            dict(
                base,
                size={"slot": "half"},
                output={"path": "f.png", "bbox": "tight"},
            ),
            base_dir=td,
        )
        check(
            "bbox-explicit-tight-warns",
            any(w.startswith("tight-bbox") for w in warnings_of(fig)),
            f"{warnings_of(fig)}",
        )
        plt.close(fig)


# -------------------------------------------------- 类别轴样式出口


def tick_style_outlets():
    """item 7：tick_rotation（持久 labelrotation + x 轴右锚）/ tick_stride 隔显。"""
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"x": "alpha", "y": 1}, {"x": "beta", "y": 2}]},
            "series": [{"kind": "bar", "x": "x", "y": "y"}],
            "xaxis": {"tick_rotation": 45},
        }
    )
    ax = fig.get_axes()[0]
    t = ax.get_xticklabels()[0]
    check(
        "tick-rotation-cat",
        t.get_rotation() == 45.0 and t.get_ha() == "right",
        f"rot={t.get_rotation()} ha={t.get_ha()}",
    )
    plt.close(fig)
    fig = render(
        {
            "version": 1,
            "data": {
                "d": [
                    {"x": "a", "y": "p", "z": 1.0},
                    {"x": "b", "y": "p", "z": 2.0},
                    {"x": "c", "y": "p", "z": 3.0},
                ]
            },
            "series": [{"kind": "heat", "x": "x", "y": "y", "z": "z", "cbar": False}],
            "xaxis": {"tick_stride": 2},
        }
    )
    ax = fig.get_axes()[0]
    ax.figure.canvas.draw()
    labels = [t.get_text() for t in ax.xaxis.get_majorticklabels()]
    check("tick-stride-heat", labels == ["a", "", "c"], f"{labels}")
    plt.close(fig)
    expect_error(
        "tick-stride-bad",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
            "xaxis": {"tick_stride": 0},
        },
        "tick_stride",
    )
    expect_error(
        "tick-rotation-bad",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
            "xaxis": {"tick_rotation": "steep"},
        },
        "tick_rotation",
    )


# -------------------------------------------------- scatter 类别 y


def scatter_cat_y():
    """item 8：y 类别列 → 首见序槽位 + 自动刻度标签；yaxis 类别语义照旧。"""
    fig = render(
        {
            "version": 1,
            "data": {
                "d": [
                    {"x": 0.1, "y": "alpha", "e": 0.02},
                    {"x": 0.4, "y": "beta", "e": 0.05},
                ]
            },
            "series": [{"kind": "scatter", "x": "x", "y": "y", "xerr": "e"}],
        }
    )
    ax = fig.get_axes()[0]
    check(
        "caty-ticklabels",
        [t.get_text() for t in ax.get_yticklabels()] == ["alpha", "beta"],
        f"{[t.get_text() for t in ax.get_yticklabels()]}",
    )
    sc = next(c for c in ax.collections if c.get_gid() != "fv-neutral")
    off = sc.get_offsets()
    check("caty-positions", np.allclose(off[:, 1], [0.0, 1.0]), f"y={off[:, 1]}")
    plt.close(fig)
    # 类别 y 轴刻度归 kind 层——yaxis.ticks 照旧 lint 忽略
    expect_lint(
        "caty-axis-ignored",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": "a"}]},
            "series": [{"kind": "scatter", "x": "x", "y": "y"}],
            "yaxis": {"ticks": [0]},
        },
        "axis-ignored",
    )
    expect_error(
        "caty-radar",
        {
            "version": 1,
            "kind": "radar",
            "dims": ["a", "b"],
            "data": {"d": [{"dim": "a", "v": "cat"}, {"dim": "b", "v": "dog"}]},
            "series": [{"kind": "scatter", "x": "dim", "y": "v"}],
        },
        "radar",
        "numeric",
    )


# -------------------------------------------------- ref 对角线 + dir 校验


def ref_diag():
    """item 9：dir:'diag'/'identity' 画 y=x+b 对角线；dir 非法值响亮报错。"""
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
            "series": [
                {"kind": "scatter", "x": "x", "y": "y"},
                {"kind": "ref", "dir": "diag"},
            ],
            "xaxis": {"lim": [0, 1]},
            "yaxis": {"lim": [0, 1]},
        }
    )
    ax = fig.get_axes()[0]
    lines = [ln for ln in ax.lines if ln.get_gid() == "fv-neutral"]
    check("ref-diag-drawn", len(lines) == 1, f"{ax.lines}")
    if lines:
        # AxLine 的过点/斜率存在 _xy1/_slope——get_xydata() 是占位值
        check(
            "ref-diag-identity",
            tuple(lines[0]._xy1) == (0.0, 0.0) and lines[0]._slope == 1.0,
            f"xy1={lines[0]._xy1} slope={lines[0]._slope}",
        )
    plt.close(fig)
    # at = y 截距：b=0.5 → axline 过 (0, 0.5)
    fig = render(
        {
            "version": 1,
            "series": [{"kind": "ref", "dir": "identity", "at": 0.5}],
            "xaxis": {"lim": [0, 1]},
            "yaxis": {"lim": [0, 1]},
        }
    )
    ax = fig.get_axes()[0]
    lines = [ln for ln in ax.lines if ln.get_gid() == "fv-neutral"]
    check(
        "ref-diag-intercept",
        tuple(lines[0]._xy1) == (0.0, 0.5),
        f"xy1={lines[0]._xy1}",
    )
    plt.close(fig)
    expect_error(
        "ref-bad-dir",
        {"version": 1, "series": [{"kind": "ref", "dir": "diag2", "at": 1}]},
        "dir",
    )
    expect_error(
        "span-bad-dir",
        {"version": 1, "series": [{"kind": "span", "dir": "w", "at": [0, 1]}]},
        "dir",
    )
    expect_error(
        "bar-bad-dir",
        {
            "version": 1,
            "data": {"d": [{"x": "a", "y": 1}]},
            "series": [{"kind": "bar", "x": "x", "y": "y", "dir": "q"}],
        },
        "dir",
    )
    expect_error(
        "ref-diag-radar",
        {
            "version": 1,
            "kind": "radar",
            "dims": ["a", "b"],
            "series": [{"kind": "ref", "dir": "diag"}],
        },
        "radar",
    )


# -------------------------------------------------- note 逐行扇出


def note_fanout():
    """item 10：at:{x,y} 两列按行落位；{field}/{field:fmt} 行内替换；组色。"""
    fig = render(
        {
            "version": 1,
            "data": {
                "d": [
                    {"est": 0.3, "py": 0, "lab": "A"},
                    {"est": 0.6, "py": 1, "lab": "B"},
                    {"est": None, "py": 2, "lab": "C"},
                ]
            },
            "series": [
                {
                    "kind": "note",
                    "at": {"x": "est", "y": "py"},
                    "text": "{lab}={est:.2f}",
                }
            ],
        }
    )
    ax = fig.get_axes()[0]
    texts = sorted(t.get_text() for t in ax.texts)
    check("note-fanout-texts", texts == ["A=0.30", "B=0.60"], f"{texts}")
    check(
        "note-fanout-missing-rows",
        any(w.startswith("missing-rows") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)
    # 非行字段花括号原样保留
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"px": 0, "py": 0}]},
            "series": [
                {"kind": "note", "at": {"x": "px", "y": "py"}, "text": "lit{v}"}
            ],
        }
    )
    texts = [t.get_text() for t in fig.get_axes()[0].texts]
    check("note-fanout-literal-brace", texts == ["lit{v}"], f"{texts}")
    plt.close(fig)
    # by 扇出 → 组色
    fig = render(
        {
            "version": 1,
            "data": {
                "d": [
                    {"g": "t", "px": 0, "py": 0, "est": 1.0},
                    {"g": "c", "px": 1, "py": 1, "est": 2.0},
                ]
            },
            "series": [
                {
                    "kind": "note",
                    "at": {"x": "px", "y": "py"},
                    "text": "{est}",
                    "by": "g",
                }
            ],
        }
    )
    colors = {t.get_text(): t.get_color() for t in fig.get_axes()[0].texts}
    # 组序首见序 → palette[0]/palette[1]
    check(
        "note-fanout-group-color",
        colors.get("1.0") == fv.PALETTES["paper"][0]
        and colors.get("2.0") == fv.PALETTES["paper"][1],
        f"{colors}",
    )
    plt.close(fig)
    expect_error(
        "note-at-missing-y",
        {
            "version": 1,
            "data": {"d": [{"px": 0}]},
            "series": [{"kind": "note", "at": {"x": "px"}, "text": "t"}],
        },
        "'x' and 'y'",
    )
    expect_error(
        "note-at-extra-key",
        {
            "version": 1,
            "data": {"d": [{"px": 0, "py": 0}]},
            "series": [
                {
                    "kind": "note",
                    "at": {"x": "px", "y": "py", "z": 1},
                    "text": "t",
                }
            ],
        },
        "unknown keys",
    )
    expect_error(
        "note-at-nonnum",
        {
            "version": 1,
            "data": {"d": [{"px": "a", "py": 0}]},
            "series": [{"kind": "note", "at": {"x": "px", "y": "py"}, "text": "t"}],
        },
        "non-categorical",
    )


# -------------------------------------------------- errprops 透传


def errprops_passthrough():
    """item 11：errprops 进 errorbar 调用并盖过内置默认。"""
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1, "e": 0.2}, {"x": 1, "y": 2, "e": 0.3}]},
            "series": [
                {
                    "kind": "line",
                    "x": "x",
                    "y": "y",
                    "yerr": "e",
                    "errprops": {"elinewidth": 2.5, "capthick": 1.8},
                }
            ],
        }
    )
    ax = fig.get_axes()[0]
    conts = [c for c in ax.containers if isinstance(c, ErrorbarContainer)]
    check("errprops-container", len(conts) == 1, f"{len(conts)} containers")
    if conts:
        caplines, barcols = conts[0][1], conts[0][2]
        lw = float(barcols[0].get_linewidths()[0]) if barcols else None
        # mpl 把 capthick 落在 cap 线的 markeredgewidth 上
        cw = float(caplines[0].get_markeredgewidth()) if caplines else None
        check("errprops-elinewidth", lw == 2.5, f"elinewidth={lw}")
        check("errprops-capthick", cw == 1.8, f"capthick={cw}")
    plt.close(fig)


# -------------------------------------------------- band 无父


def band_parentless():
    """item 12：band 无 of + 自带 x/lo/hi → 独立 fill_between；pred 仍要 of。"""
    fig = render(
        {
            "version": 1,
            "data": {
                "d": [
                    {"x": 0, "lo": 0, "hi": 1},
                    {"x": 1, "lo": 0, "hi": 2},
                ]
            },
            "series": [{"kind": "band", "x": "x", "lo": "lo", "hi": "hi"}],
        }
    )
    from matplotlib.collections import PolyCollection

    polys = [c for c in fig.get_axes()[0].collections if isinstance(c, PolyCollection)]
    check("band-fill-only", len(polys) == 1, f"{polys}")
    plt.close(fig)
    expect_error(
        "band-no-of-no-x",
        {
            "version": 1,
            "data": {"d": [{"lo": 0, "hi": 1}]},
            "series": [{"kind": "band", "lo": "lo", "hi": "hi"}],
        },
        "band",
        "'x'",
    )
    expect_error(
        "pred-still-needs-of",
        {
            "version": 1,
            "data": {"d": [{"x": 0, "y": 1}]},
            "series": [{"kind": "pred", "x": "x", "y": "y"}],
        },
        "requires 'of'",
    )


# -------------------------------------------------- panel aspect


def panel_aspect():
    """item 13：xy 面板 aspect:'equal' → 1.0；非 xy/非法值响亮报错。"""
    fig = render(
        {
            "version": 1,
            "aspect": "equal",
            "data": {"d": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
        }
    )
    check(
        "aspect-equal",
        fig.get_axes()[0].get_aspect() == 1.0,
        f"{fig.get_axes()[0].get_aspect()}",
    )
    plt.close(fig)
    expect_error(
        "aspect-radar",
        {
            "version": 1,
            "kind": "radar",
            "dims": ["a", "b"],
            "aspect": "equal",
            "series": [{"kind": "line", "x": "a", "y": "a"}],
        },
        "aspect",
    )
    expect_error(
        "aspect-bad",
        {
            "version": 1,
            "aspect": "wide",
            "data": {"d": [{"x": 0, "y": 1}]},
            "series": [{"kind": "line", "x": "x", "y": "y"}],
        },
        "aspect",
    )


# -------------------------------------------------- bar 数值 x


def bar_numeric_x():
    """item 14：x 全数值 → 柱心落真实坐标、宽按最小间距、x 轴数值刻度。"""
    fig = render(
        {
            "version": 1,
            "data": {
                "d": [
                    {"x": 0.05, "y": 0.10, "e": 0.02},
                    {"x": 0.15, "y": 0.20, "e": 0.03},
                    {"x": 0.25, "y": 0.30, "e": 0.02},
                ]
            },
            "series": [{"kind": "bar", "x": "x", "y": "y", "xerr": "e"}],
        }
    )
    ax = fig.get_axes()[0]
    centers = sorted(p.get_x() + p.get_width() / 2 for p in ax.patches)
    check(
        "bar-numx-positions",
        np.allclose(centers, [0.05, 0.15, 0.25]),
        f"{centers}",
    )
    check(
        "bar-numx-width",
        np.isclose(ax.patches[0].get_width(), 0.08),
        f"{ax.patches[0].get_width()}",
    )
    check(
        "bar-numx-auto-ticks",
        not isinstance(ax.xaxis.get_major_locator(), FixedLocator),
        f"{ax.xaxis.get_major_locator()}",
    )
    conts = [c for c in ax.containers if isinstance(c, ErrorbarContainer)]
    check("bar-numx-xerr", len(conts) == 1, f"{len(conts)} containers")
    plt.close(fig)
    # 数值 x 轴归用户：ticks/tick_labels 不再 axis-ignored
    expect_lint(
        "bar-numx-ticks-ok",
        {
            "version": 1,
            "data": {"d": [{"x": 0.05, "y": 1}, {"x": 0.15, "y": 2}]},
            "series": [{"kind": "bar", "x": "x", "y": "y"}],
            "xaxis": {"ticks": [0.05, 0.15], "tick_labels": ["lo", "hi"]},
        },
        "axis-ignored",
        present=False,
    )
    # 数值 x 不报 bar-count（柱墙语义只适用类别槽位）
    expect_lint(
        "bar-numx-no-count-lint",
        {
            "version": 1,
            "data": {"d": [{"x": i * 0.05, "y": 1} for i in range(15)]},
            "series": [{"kind": "bar", "x": "x", "y": "y"}],
        },
        "bar-count",
        present=False,
    )
    # 混入非数值 → 维持类别槽位
    fig = render(
        {
            "version": 1,
            "data": {"d": [{"x": 0.05, "y": 1}, {"x": "b", "y": 2}]},
            "series": [{"kind": "bar", "x": "x", "y": "y"}],
        }
    )
    check(
        "bar-mixed-stays-cat",
        isinstance(fig.get_axes()[0].xaxis.get_major_locator(), FixedLocator),
        f"{fig.get_axes()[0].xaxis.get_major_locator()}",
    )
    plt.close(fig)


def main() -> int:
    edgecolor_tokens()
    dead_cells()
    heat_annotate_ink()
    note_outside_lint()
    occluded_by_heat_lint()
    bbox_defaults()
    tick_style_outlets()
    scatter_cat_y()
    ref_diag()
    note_fanout()
    errprops_passthrough()
    band_parentless()
    panel_aspect()
    bar_numeric_x()
    print(f"--- spec-atoms: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
