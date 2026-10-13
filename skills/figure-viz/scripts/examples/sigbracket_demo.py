"""显著性 bracket 模板：分组柱 + 面板内/跨面板显著性括号（draw_event 惰性定位）。

语义台账：每根柱 = (benchmark, method) 的聚合 score；每条 bracket = 一次
两两检验（p 由上游统计脚本随聚合行一起交付，本脚本不算 p）；星号 = p 的
显示映射。几何台账：x 名义单位 = 一个 benchmark 槽位（宽 1），柱宽 0.36、
dodge ±0.18；面板内 bracket 的 pad/tick 以 data 单位计，锚点为柱顶与值
标签顶的较高者；跨面板 bracket 的 pad/tick 以 figure fraction 计。

两个惯用法对应 spec 侧查明的两处缺口：
  * 括号与星号一体生成——星号 y 与 bracket y 同源，不存在 spec raw 路线
    「note.at 与 helper 输出手工同步」的 split-brain；
  * 全部 bracket artist 先以空壳创建、fv.mark_neutral 上注释层身份（gid
    'fv-neutral'，不算系列、不进 legend-coverage），几何在 draw_event 里
    惰性重算——spec panels.*.raw 与本文件的等价位置都在 tight_layout
    之前，fig-fraction 与 label-aware 锚点只有 draw 时刻才有真值；渲染
    管线在 audit/savefig 前必 draw，坐标随每次 draw 重算、布局不挪位。

运行：uv run --with matplotlib --with numpy python sigbracket_demo.py
"""
# ruff: noqa: E402  —— fvlocate.ensure() 之后的 import 是刻意的路径门控

import sys
from pathlib import Path

# fvlocate.py 在本仓 scripts/；vendored 用法把它拷到脚本旁，此行可省
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fvlocate

fvlocate.ensure()  # assets/mpl 加入 sys.path

import fvstyle as fv
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

THEME = "paper"
BASE = 7.6
FIGW_FULL = 5.5  # 整版宽 slot（spec size.slot:"full"）：按放置尺寸绘制

METHODS = ["ours", "base"]
METHOD_LABEL = {"ours": "proposed", "base": "baseline"}
BAR_W = 0.36
YLIM = (0, 105)

# 每 panel 一组 by=method dodge 柱 + 面板内 sig 行：l/r 为按柱心排序的
# 全局柱序号（task 主序、method 次序），p 由上游随聚合行交付
PANELS = [
    {
        "title": "(a) reasoning",
        "tasks": ["AIME", "GPQA"],
        "scores": {"ours": [71, 74], "base": [62, 66]},
        "sig": [{"l": 0, "r": 1, "p": 0.004}, {"l": 2, "r": 3, "p": 0.0004}],
    },
    {
        "title": "(b) knowledge",
        "tasks": ["LiveC", "MATH"],
        "scores": {"ours": [73, 78], "base": [64, 69]},
        "sig": [{"l": 0, "r": 1, "p": 0.031}],
    },
]
# 跨面板 bracket：首面板第 l 根柱 ↔ 末面板第 r 根柱（fig-fraction 几何）
XSIG = {"l": 0, "r": 2, "p": 0.08}

PAD, TICK, STAR_DY = 3.0, 1.4, 0.8  # 面板内几何：data 单位
XPAD, XTICK, XSTAR_DY = 0.10, 0.028, 0.012  # 跨面板几何：figure fraction


def pstars(p: float) -> str:
    """p → 星号惯例：``***`` p<.001、``**`` p<.01、``*`` p<.05，否则 ``n.s.``。"""
    for cut, s in ((0.001, "***"), (0.01, "**"), (0.05, "*")):
        if p < cut:
            return s
    return "n.s."


def star_fs(text: str) -> float:
    """星号正体、n.s. 弱化的字号对。"""
    return 6.2 if text == "n.s." else 7.0


def _cx(rect) -> float:
    return rect.get_x() + rect.get_width() / 2


def _panel_bars(ax, spec, colors):
    """by=method dodge 柱 + 柱顶值标签；返回按柱心排序的 (rects, labels)。

    柱几何一律从 ax.patches 实测反推——dodge 偏移是实现细节，调用方不
    该手算 ±0.18；值标签走 annotate offset points（spec labels.dy 同款），
    标 fv-neutral 后不算系列墨水。
    """
    x = list(range(len(spec["tasks"])))
    for j, m in enumerate(METHODS):
        off = (j - (len(METHODS) - 1) / 2) * BAR_W
        ax.bar(
            [xi + off for xi in x],
            spec["scores"][m],
            width=BAR_W,
            color=colors[m],
            edgecolor="white",
            linewidth=0.6,
            label=METHOD_LABEL[m],
        )
    rects = sorted(ax.patches, key=_cx)
    labels = [
        ax.annotate(
            f"{r.get_height():.0f}",
            (_cx(r), r.get_y() + r.get_height()),
            xytext=(0, 1.5),
            textcoords="offset points",
            ha="center",
            fontsize=5.8,
            color=fv.NEUTRALS["vink"],
        )
        for r in rects
    ]
    fv.mark_neutral(*labels)
    ax.set_xticks(x, spec["tasks"])
    ax.set_xlabel("benchmark")
    ax.set_ylim(*YLIM)
    ax.set_title(spec["title"])
    fv.apply_frame(ax, "closed")
    fv.apply_grid(ax, "y-only")
    return rects, labels


def _anchor_top(ax, rect, label, renderer):
    """bracket 锚点（data 坐标）：柱顶与其值标签顶的较高者。"""
    top = rect.get_y() + rect.get_height()
    if label is not None:
        bb = label.get_window_extent(renderer)
        lab_top = ax.transData.inverted().transform((bb.x0, bb.y1))[1]
        top = max(top, lab_top)
    return top


def install_sig_brackets(fig, axes, bars, xsig):
    """空壳 artist + 一次 draw_event 惰性定位；tight_layout 之前调用。

    bars：每轴 _panel_bars 的 (rects, labels)；xsig=None 时只画面板内
    bracket（单面板图复用入口）。面板内 bracket 走各轴 data 坐标；跨面板
    bracket 是 fig-fraction Line2D + fig.text——两轴各自
    transData → display → transFigure⁻¹ 换算，依赖定稿后的 axes bbox，
    故只能在 draw 时取真值。
    """
    ink = fv.NEUTRALS["vink"]
    jobs = []  # (ax, rects, labels, line, star, l, r)
    for ax, (rects, labels), spec in zip(axes, bars, PANELS):
        for row in spec.get("sig", ()):
            (ln,) = ax.plot(
                [], [], color=ink, lw=0.7, solid_capstyle="butt", clip_on=False
            )
            text = pstars(row["p"])
            star = ax.text(
                0,
                0,
                text,
                ha="center",
                va="bottom",
                fontsize=star_fs(text),
                color=ink,
            )
            fv.mark_neutral(ln, star)
            jobs.append((ax, rects, labels, ln, star, int(row["l"]), int(row["r"])))

    xln = xstar = None
    if xsig is not None:
        (ax_l, ax_r) = axes[0], axes[-1]
        rects_l, labs_l = bars[0]
        rects_r, labs_r = bars[-1]
        xtext = pstars(xsig["p"])
        xln = Line2D([], [], transform=fig.transFigure, color=ink, lw=0.7)
        fig.lines.append(xln)
        xstar = fig.text(
            0, 0, xtext, ha="center", va="bottom", fontsize=star_fs(xtext), color=ink
        )
        fv.mark_neutral(xln, xstar)

    def _frac_top(ax, rect, label, inv, renderer):
        top = _anchor_top(ax, rect, label, renderer)
        return inv.transform(ax.transData.transform((_cx(rect), top)))

    def _place(evt):
        # layout 已定稿：label 高度、fig-fraction 全部取当次 draw 的真值
        for ax, rects, labels, ln, star, li, ri in jobs:
            y = (
                max(
                    _anchor_top(ax, rects[li], labels[li], evt.renderer),
                    _anchor_top(ax, rects[ri], labels[ri], evt.renderer),
                )
                + PAD
            )
            x0, x1 = _cx(rects[li]), _cx(rects[ri])
            ln.set_data([x0, x0, x1, x1], [y - TICK, y, y, y - TICK])
            star.set_position(((x0 + x1) / 2, y + STAR_DY))
        if xln is None:
            return
        inv = fig.transFigure.inverted()
        li, ri = int(xsig["l"]), int(xsig["r"])
        fa = _frac_top(ax_l, rects_l[li], labs_l[li], inv, evt.renderer)
        fb = _frac_top(ax_r, rects_r[ri], labs_r[ri], inv, evt.renderer)
        y = max(fa[1], fb[1]) + XPAD
        xln.set_data([fa[0], fa[0], fb[0], fb[0]], [y - XTICK, y, y, y - XTICK])
        xstar.set_position(((fa[0] + fb[0]) / 2, y + XSTAR_DY))

    fig.canvas.mpl_connect("draw_event", _place)


def make_figure():
    colors = dict(zip(METHODS, fv.series_colors(THEME, len(METHODS))))  # 一法一色
    fig, axes = plt.subplots(1, len(PANELS), sharey=True, figsize=(FIGW_FULL, 2.1))
    bars = [_panel_bars(ax, spec, colors) for ax, spec in zip(axes, PANELS)]
    axes[0].set_ylabel("score")

    install_sig_brackets(fig, axes, bars, XSIG)
    # ↑ spec panels.*.raw 的等价位置：layout 之前挂惰性定位，draw 时才取真值

    handles = [
        Patch(facecolor=colors[m], edgecolor="white", label=METHOD_LABEL[m])
        for m in METHODS
    ] + [
        # ghost：bracket 是 fv-neutral 无图例义务，此条纯为读者注明线型含义
        Line2D([], [], color=fv.NEUTRALS["vink"], lw=0.7, label="sig. bracket")
    ]
    fig.legend(
        handles=handles,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.055),
        fontsize=6.4,
        columnspacing=0.8,
        handletextpad=0.4,
    )
    fig.tight_layout(rect=[0, 0.15, 1, 1])  # 给共享 legend + 标识行让位
    fig.text(
        0.5,
        0.004,
        r"grouped bars; brackets mark $*p<.05$, $**p<.01$, $***p<.001$",
        ha="center",
        va="bottom",
        fontsize=max(BASE - 2.2, 0.72 * BASE),
        color=fv.HUES["vgray"],
    )
    return fig


def main() -> int:
    fv.apply_rc(THEME, fontsize=BASE)
    plt.rcParams.update(
        {
            "xtick.labelsize": BASE - 1.2,
            "ytick.labelsize": BASE - 1.2,
            "axes.linewidth": 0.6,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
        }
    )
    fig = make_figure()
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "sigbracket-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
