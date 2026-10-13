#!/usr/bin/env python3
"""selftest.py — figure-viz mpl 轨自检。

每条 audit 规则造一个带对应违规的图，断言该规则触发；每个图型造一张
干净图，断言 audit 返回 []。全部 PASS 退出 0，任一 FAIL 退出 1。

运行：uv run --with matplotlib --with numpy python scripts/selftest.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl

mpl.use("Agg")

import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np

X = np.arange(6)
YS = np.array([50, 55, 61, 64, 70, 74])


def _gutter_legend(ax):
    """legend 放到 axes 外、figure 内的槽位（图内不遮数据、不越界）。"""
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))


def _style_series(ax, labels, color, marker="o"):
    for lab in labels:
        ax.plot(X, YS + len(lab), color=color, marker=marker, linestyle="-", label=lab)


# --- 每条规则一个违规图 ----------------------------------------------------


def fig_collide():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"])
    ax.text(0.5, 0.5, "AAAA", transform=ax.transAxes, fontsize=20)
    ax.text(0.5, 0.5, "BBBB", transform=ax.transAxes, fontsize=20)
    return fig


def fig_offpalette():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color="#FF1234")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig


def fig_log_nonpositive():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, np.array([1.0, -2.0, 3.0, 4.0, 5.0, 6.0]), color=fv.HUES["vteal"])
    ax.set_yscale("log")
    return fig


def fig_bar_baseline():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar([0, 1, 2], [55, 57, 59], color=fv.HUES["vteal"])
    ax.set_ylim(50, 60)
    return fig


def fig_data_clipped():
    fig, ax = plt.subplots(figsize=(4, 3))
    ys = np.concatenate([np.full(10, 0.5), np.full(10, 5.0)])
    ax.plot(np.arange(20), ys, color=fv.HUES["vteal"], label="s")
    ax.set_ylim(0, 1)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig


def fig_facet_ylim():
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    for ax, hi in zip(axs, (1.0, 100.0), strict=True):
        ax.plot(X, YS / 74 * hi, color=fv.HUES["vteal"], label="s")
        ax.set_ylabel("Score")
        ax.set_xlabel("x")
        ax.set_ylim(0, hi)
    return fig


def fig_facet_ylim_mixed():
    # labelouter 网格：仅左格带 ylabel，整行可比较却刻度不同
    fig, axs = plt.subplots(1, 2, figsize=(7, 3), sharey=False)
    axs[0].plot(X, YS / 74, color=fv.HUES["vteal"], label="s")
    axs[0].set_ylabel("Score")
    axs[0].set_xlabel("x")
    axs[1].plot(X, YS, color=fv.HUES["vorange"], label="s")
    axs[1].set_xlabel("x")
    axs[1].set_ylim(0, 100)
    fig.tight_layout()
    return fig


def fig_missing_axis_label():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"])
    return fig


def fig_label_color_inconsistent():
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    for ax, c in zip(axs, (fv.HUES["vteal"], fv.HUES["vorange"]), strict=True):
        ax.plot(X, YS, color=c, marker="o", label="method")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    return fig


def fig_label_marker_inconsistent():
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    for ax, mk in zip(axs, ("o", "s"), strict=True):
        ax.plot(X, YS, color=fv.HUES["vteal"], marker=mk, label="method")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    return fig


def fig_legend_overlaps_data():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar([0, 1, 2], [0.95, 0.95, 0.95], color=fv.HUES["vteal"], label="s")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper center")
    return fig


def fig_text_outside_figure():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"])
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.text(0.5, -0.05, "caption below the figure")
    return fig


def fig_legend_coverage():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="a")
    ax.plot(X, YS - 5, color=fv.HUES["vorange"], label="b")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig


def fig_legend_coverage_unlabeled():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="a")
    ax.plot(X, YS - 5, color=fv.HUES["vorange"])  # 异色无标，任何 legend 都不覆盖
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend()
    return fig


def fig_duplicate_legend_label():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="same")
    ax.plot(X, YS - 5, color=fv.HUES["vorange"], label="same")
    ax.legend()
    return fig


def fig_tag_sequence():
    fig, axs = plt.subplots(1, 3, figsize=(9, 3))
    for ax, tag in zip(axs, ("(a)", "(a)", "(c)"), strict=True):
        ax.plot(X, YS, color=fv.HUES["vteal"])
        ax.set_title(f"{tag} panel")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    return fig


def fig_hue_budget():
    fig, ax = plt.subplots(figsize=(4, 3))
    fams = ["vteal", "vorange", "vcoral", "vviolet", "vgreen"]
    for i, f in enumerate(fams):
        ax.plot(X, YS - i, color=fv.HUES[f])
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig


def fig_palette_overflow():
    fig, ax = plt.subplots(figsize=(4, 3))
    _style_series(ax, ["a", "b"], fv.HUES["vteal"])
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend()
    return fig


def fig_palette_overflow_unclaimed():
    # 6 条无标 pred 用未被有标系列认领的调色板色——是真系列，照算名额
    fig, ax = plt.subplots(figsize=(4, 3))
    colors = fv.series_colors("paper", 4)
    spare = [fv.HUES[k] for k in ("vgreen", "vgold", "vblue", "vrose", "vgray")]
    spare += [fv.EDGE["vteal_edge"]]
    for i in range(4):
        ax.plot(X, YS - 4 * i, color=colors[i], label=f"m{i}")
    for i, c in enumerate(spare):
        ax.plot(X, YS - 4 * i + 2, color=c, ls=":")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend()
    return fig


def fig_lone_unlabeled():
    # 零识别：无 label、无 ylabel、无就地文字、无 legend——legend-coverage 必报
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"])
    ax.set_xlabel("x")
    return fig


def fig_lone_dead_label():
    # 死 label：label 存在但全图无 legend 收它（m08 逃逸回补）——xlabel
    # 不识别系列身份，必须报
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    return fig


def fig_lone_ylabel():
    # 单无标系列 + ylabel = 已识别，不该报（m09：此前误报 not ghost-covered）
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.plot(X, YS, color=fv.HUES["vteal"])
    ax.set_xlabel("x")
    ax.set_ylabel("loss")
    fig.subplots_adjust(left=0.16, right=0.9, top=0.9, bottom=0.16)
    return fig


def fig_missing_label_peraxes():
    # 一格带标签不再豁免全图——axs[1] 缺 xlabel/ylabel 必须逐格报
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    axs[0].plot(X, YS, color=fv.HUES["vteal"])
    axs[0].set_xlabel("x")
    axs[0].set_ylabel("y")
    axs[1].plot(X, YS - 5, color=fv.HUES["vorange"])
    return fig


def fig_bar_mixed_truncated():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar([0, 1, 2], [3, -2, 4], color=fv.HUES["vteal"], label="v")
    ax.set_ylim(1, 5)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend()
    return fig


def fig_rb_collide():
    # 部分重叠（~半框）：collide（error，任何相交）与 rb-text-collide
    # （warn，>20% 较小框）都应报——rb 是渲染后回读层的同款检查
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"])
    ax.text(0.40, 0.5, "AAAA", transform=ax.transAxes, fontsize=20)
    ax.text(0.46, 0.52, "BBBB", transform=ax.transAxes, fontsize=20)
    return fig


def fig_print_fit():
    # 宽图注定要缩进 5.5in full 槽：交付宽按 tightbbox 计约 6.6in，
    # x~0.83 降采样后 6pt 注释字 <5.5pt
    fv.apply_rc("paper")
    fig, ax = plt.subplots(figsize=(8.0, 3.0))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="m")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.text(0.5, 0.88, "tiny note", transform=ax.transAxes, fontsize=6)
    ax.legend()
    fig.subplots_adjust(bottom=0.22)
    return fig


# --- 每图型一张干净图 ------------------------------------------------------


def fig_clean_bar():
    theme = fv.apply_rc("paper")
    labels = ["A", "B", "C", "D"]
    data = {"Method": [71, 74, 73, 78], "Baseline": [62, 66, 64, 69]}
    colors = fv.series_colors("paper", len(data))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    x = np.arange(len(labels))
    for i, (name, vals) in enumerate(data.items()):
        ax.bar(x + (i - 0.5) * 0.36, vals, width=0.36, label=name, color=colors[i])
    ax.set_xticks(x, labels)
    ax.set_xlabel("Group")
    ax.set_ylabel("Score")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_line():
    theme = fv.apply_rc("paper")
    data = {"Focal": YS + 2, "Reference": YS - 1}
    colors = fv.series_colors("paper", len(data))
    marks = fv.series_markers("paper", len(data))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for i, (name, vals) in enumerate(data.items()):
        ax.plot(X, vals, color=colors[i], marker=marks[i], label=name)
    ax.axhline(58, color=fv.NEUTRALS["baseline"], linestyle="--", label="Baseline")
    ax.set_xlabel("Step")
    ax.set_ylabel("Score")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_scatter():
    theme = fv.apply_rc("paper")
    rng = np.random.default_rng(7)
    clusters = {
        "method-a": (0.3, 0.7),
        "method-b": (0.6, 0.4),
        "baseline": (0.45, 0.55),
    }
    colors = fv.series_colors("paper", len(clusters))
    marks = fv.series_markers("paper", len(clusters))
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    for i, (name, (cx, cy)) in enumerate(clusters.items()):
        pts = rng.normal([cx, cy], 0.05, size=(30, 2))
        ax.scatter(
            pts[:, 0], pts[:, 1], s=24, color=colors[i], marker=marks[i], label=name
        )
    ax.set_xlim(0, 0.9)
    ax.set_ylim(0.15, 0.95)
    ax.set_xticks([0, 0.3, 0.6, 0.9])
    ax.set_xlabel("Throughput")
    ax.set_ylabel("Quality")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, "full-dotted")
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.72)
    return fig


def fig_clean_donut():
    fv.apply_rc("paper")
    shares = {"pretrain": 46, "sft": 22, "rlvr": 18, "eval": 14}
    colors = fv.series_colors("paper", len(shares))
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.pie(
        shares.values(),
        labels=shares.keys(),
        colors=colors,
        autopct="%1.0f%%",
        pctdistance=0.78,
        startangle=100,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.2},
        textprops={"fontsize": 10},
    )
    ax.set_title("Compute share by stage")
    return fig


def fig_clean_radar():
    theme = fv.apply_rc("paper")
    dims = ["math", "code", "reason", "knowledge", "long-ctx"]
    profiles = {
        "method": [0.82, 0.74, 0.79, 0.66, 0.71],
        "baseline": [0.70, 0.68, 0.62, 0.63, 0.58],
    }
    colors = fv.series_colors("paper", len(profiles))
    angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(5.6, 5.2), subplot_kw={"polar": True})
    for i, (name, vals) in enumerate(profiles.items()):
        v = vals + vals[:1]
        ax.plot(angles, v, color=colors[i], linewidth=1.8, label=name)
        ax.fill(angles, v, color=colors[i], alpha=0.12)
    ax.set_xticks(angles[:-1], dims)
    ax.set_ylim(0, 1)
    ax.legend(loc="center left", bbox_to_anchor=(1.15, 0.5))
    fv.apply_grid(ax, theme.grid)
    fig.subplots_adjust(right=0.68)
    return fig


def fig_clean_multipanel():
    fv.apply_rc("paper")
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, (name, c) in zip(
        axs, {"m1": fv.HUES["vteal"], "m2": fv.HUES["vorange"]}.items(), strict=True
    ):
        ax.plot(X, YS, color=c, marker="o", label=name)
        ax.set_xlabel("Step")
        ax.set_ylabel("Score")
        ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def fig_clean_attached_overlays():
    # 4 有标系列 + 同色 band + 同色无标 pred——依附 overlay 不占调色板名额
    theme = fv.apply_rc("paper")
    colors = fv.series_colors("paper", 4)
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for i in range(4):
        ax.plot(X, YS - 3 * i, color=colors[i], label=f"m{i}")
        ax.fill_between(X, YS - 3 * i - 2, YS - 3 * i + 2, color=colors[i], alpha=0.15)
        ax.plot(X, YS - 3 * i + 4, color=colors[i], ls="--")
    ax.set_xlabel("Step")
    ax.set_ylabel("Score")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_fv_neutral():
    # 同 fig_palette_overflow_unclaimed，但 pred 带 gid 'fv-neutral' → 不算系列
    theme = fv.apply_rc("paper")
    colors = fv.series_colors("paper", 4)
    spare = [fv.HUES[k] for k in ("vgreen", "vgold", "vblue", "vrose", "vgray")]
    spare += [fv.EDGE["vteal_edge"]]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for i in range(4):
        ax.plot(X, YS - 4 * i, color=colors[i], label=f"m{i}")
    for i, c in enumerate(spare):
        pred = ax.plot(X, YS - 4 * i + 2, color=c, ls=":")[0]
        pred.set_gid("fv-neutral")
    ax.set_xlabel("Step")
    ax.set_ylabel("Score")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_polar_neutral():
    # polar 上 axvline/axvspan 是结构元素：无标不算系列、不算图例义务
    fv.apply_rc("paper")
    th = np.linspace(0, 2 * np.pi, 5, endpoint=False).tolist()
    v = [0.8, 0.7, 0.75, 0.6, 0.65]
    fig = plt.figure(figsize=(5.6, 5.2))
    ax = fig.add_subplot(111, polar=True)
    ax.plot(th + th[:1], v + v[:1], color=fv.HUES["vteal"], label="m")
    ax.axvline(0.5, color=fv.NEUTRALS["baseline"], ls="--")
    ax.axvspan(1.0, 1.5, color=fv.HUES["vgold"], alpha=0.1)
    ax.set_ylim(0, 1)
    ax.legend(loc="center left", bbox_to_anchor=(1.15, 0.5))
    fig.subplots_adjust(right=0.68)
    return fig


def fig_clean_radar_seam():
    # 组缺首维时闭合缝落在首角 +2π——极轴 theta 越界是回绕不是裁剪
    fv.apply_rc("paper")
    th = np.linspace(0, 2 * np.pi, 5, endpoint=False)[1:]
    v = [0.7, 0.75, 0.6, 0.65]
    xs = [*th, th[0] + 2 * np.pi]
    fig = plt.figure(figsize=(5.6, 5.2))
    ax = fig.add_subplot(111, polar=True)
    ax.plot(xs, v + v[:1], color=fv.HUES["vteal"], lw=1.8, label="m")
    ax.fill(xs, v + v[:1], color=fv.HUES["vteal"], alpha=0.12)
    ax.set_xticks(list(th), ["d2", "d3", "d4", "d5"])
    ax.set_ylim(0, 1)
    ax.legend(loc="center left", bbox_to_anchor=(1.15, 0.5))
    fig.subplots_adjust(right=0.68)
    return fig


def fig_clean_categorical_x():
    # 字符串类别 x：顶点退化为位置索引不崩；类别刻度自带语义豁免 xlabel
    theme = fv.apply_rc("paper")
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(
        ["a", "b", "c", "d", "e", "f"],
        YS,
        color=fv.HUES["vteal"],
        marker="o",
        label="m",
    )
    ax.set_ylabel("Score")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_bar_categories():
    # 类别刻度轴自描述：无 xlabel 合法
    theme = fv.apply_rc("paper")
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.bar(["A", "B", "C"], [3, 5, 2], color=fv.HUES["vteal"], label="v")
    ax.set_ylabel("Score")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_sharex_sibling():
    # sharex 组底格带 xlabel → 顶格豁免；就地文字标注豁免 lone-unlabeled
    fv.apply_rc("paper")
    fig, axs = plt.subplots(2, 1, figsize=(5.6, 4.4), sharex=True)
    axs[0].plot(X, YS, color=fv.HUES["vteal"])
    axs[1].plot(X, YS - 5, color=fv.HUES["vorange"])
    axs[0].text(0.03, 0.86, "method", transform=axs[0].transAxes, fontsize=8)
    axs[1].text(0.03, 0.86, "baseline", transform=axs[1].transAxes, fontsize=8)
    axs[1].set_xlabel("Step")
    axs[0].set_ylabel("m1")
    axs[1].set_ylabel("m2")
    fig.tight_layout()
    return fig


def fig_clean_bar_mixed():
    # 混合符号柱组 baseline 0 落在 ylim 内——合法
    theme = fv.apply_rc("paper")
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.bar([0, 1, 2], [3, -2, 4], color=fv.HUES["vteal"], label="v")
    ax.set_ylim(-3, 5)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fv.apply_frame(ax, theme.frame)
    fv.apply_grid(ax, theme.grid)
    _gutter_legend(ax)
    fig.subplots_adjust(right=0.78)
    return fig


def fig_clean_tag_prose():
    # "(r) reward curve" 是行文标题不是面板 tag——(a)(b) 序列仍合法
    fv.apply_rc("paper")
    titles = ("(a) loss", "(b) acc", "(r) reward curve")
    hues = (fv.HUES["vteal"], fv.HUES["vorange"], fv.HUES["vcoral"])
    fig, axs = plt.subplots(1, 3, figsize=(9, 3))
    for ax, t, c in zip(axs, titles, hues, strict=True):
        ax.plot(X, YS, color=c)
        ax.set_title(t)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.text(0.03, 0.86, "note", transform=ax.transAxes, fontsize=10)
    fig.tight_layout()
    return fig


CASES = [
    # (名称，builder, 期望命中的规则名；None = 断言干净 [])
    ("collide", fig_collide, "collide"),
    ("offpalette", fig_offpalette, "offpalette"),
    ("log-nonpositive-data", fig_log_nonpositive, "log-nonpositive-data"),
    ("bar-baseline-truncated", fig_bar_baseline, "bar-baseline-truncated"),
    ("data-clipped-outside-limits", fig_data_clipped, "data-clipped-outside-limits"),
    ("facet-ylim-mismatch", fig_facet_ylim, "facet-ylim-mismatch"),
    ("facet-ylim-mixed", fig_facet_ylim_mixed, "facet-ylim-mismatch"),
    ("missing-axis-label", fig_missing_axis_label, "missing-axis-label"),
    (
        "label-color-inconsistent",
        fig_label_color_inconsistent,
        "label-color-inconsistent",
    ),
    (
        "label-marker-inconsistent",
        fig_label_marker_inconsistent,
        "label-marker-inconsistent",
    ),
    ("legend-overlaps-data", fig_legend_overlaps_data, "legend-overlaps-data"),
    ("text-outside-figure", fig_text_outside_figure, "text-outside-figure"),
    ("legend-coverage", fig_legend_coverage, "legend-coverage"),
    ("legend-coverage-unlabeled", fig_legend_coverage_unlabeled, "legend-coverage"),
    ("duplicate-legend-label", fig_duplicate_legend_label, "duplicate-legend-label"),
    ("tag-sequence", fig_tag_sequence, "tag-sequence"),
    ("hue-budget", fig_hue_budget, "hue-budget"),
    ("palette-overflow", fig_palette_overflow, "palette-overflow"),
    (
        "palette-overflow-unclaimed",
        fig_palette_overflow_unclaimed,
        "palette-overflow",
    ),
    ("legend-coverage-lone", fig_lone_unlabeled, "legend-coverage"),
    ("legend-coverage-dead-label", fig_lone_dead_label, "legend-coverage"),
    ("clean-lone-ylabel", fig_lone_ylabel, None),
    (
        "missing-axis-label-peraxes",
        fig_missing_label_peraxes,
        "missing-axis-label",
    ),
    ("bar-baseline-mixed", fig_bar_mixed_truncated, "bar-baseline-truncated"),
    ("rb-text-collide", fig_rb_collide, "rb-text-collide"),
    ("print-fit", fig_print_fit, "print-fit"),
    ("clean-bar", fig_clean_bar, None),
    ("clean-line", fig_clean_line, None),
    ("clean-scatter", fig_clean_scatter, None),
    ("clean-donut", fig_clean_donut, None),
    ("clean-radar", fig_clean_radar, None),
    ("clean-multipanel", fig_clean_multipanel, None),
    ("clean-attached-overlays", fig_clean_attached_overlays, None),
    ("clean-fv-neutral", fig_clean_fv_neutral, None),
    ("clean-polar-neutral", fig_clean_polar_neutral, None),
    ("clean-radar-seam", fig_clean_radar_seam, None),
    ("clean-categorical-x", fig_clean_categorical_x, None),
    ("clean-bar-categories", fig_clean_bar_categories, None),
    ("clean-sharex-sibling", fig_clean_sharex_sibling, None),
    ("clean-bar-mixed", fig_clean_bar_mixed, None),
    ("clean-tag-prose", fig_clean_tag_prose, None),
]


def check_knobs() -> list[str]:
    """rules / ignore / scoped_ignore / ignore_axes / extra_palette 参数生效。"""
    bad = []
    fig = fig_offpalette()
    if any(p.startswith("offpalette") for p in fv.audit(fig, ignore={"offpalette"})):
        bad.append("ignore={'offpalette'} did not suppress")
    if any(
        p.startswith("offpalette")
        for p in fv.audit(fig_offpalette(), rules={"collide"})
    ):
        bad.append("rules={'collide'} still ran offpalette")
    # 未知名必须抛 ValueError——打错字不该静默关掉检查
    try:
        fv.audit(fig_offpalette(), rules={"collde"})
        bad.append("rules typo did not raise ValueError")
    except ValueError:
        pass
    try:
        fv.audit(fig_offpalette(), scoped_ignore={("collde", 0)})
        bad.append("scoped_ignore typo did not raise ValueError")
    except ValueError:
        pass
    if not any(
        p.startswith("bar-baseline-truncated") for p in fv.audit(fig_bar_baseline())
    ):
        bad.append("bar-baseline seed did not fire")
    probs = fv.audit(fig_bar_baseline(), ignore_axes=[0])
    if any(p.startswith("bar-baseline-truncated") for p in probs):
        bad.append("ignore_axes did not exempt axes 0")
    probs = fv.audit(fig_offpalette(), extra_palette=["#FF1234"])
    if any(p.startswith("offpalette") for p in probs):
        bad.append("extra_palette did not whitelist #FF1234")

    # scoped_ignore 只豁免指定 axes 上的指定规则
    fig2, axs2 = plt.subplots(1, 2, figsize=(7, 3))
    for ax in axs2:
        ax.plot(X, np.array([1.0, -2.0, 3, 4, 5, 6]), color=fv.HUES["vteal"])
        ax.set_yscale("log")
    probs = fv.audit(fig2, scoped_ignore={("log-nonpositive-data", 1)})
    logs = [p for p in probs if p.startswith("log-nonpositive-data")]
    if any("axes 1" in p for p in logs):
        bad.append("scoped_ignore did not suppress axes 1")
    if not any("axes 0" in p for p in logs):
        bad.append("scoped_ignore wrongly suppressed axes 0")
    plt.close(fig2)

    # 关系型规则：被豁免 axes 移出比较组——剩 2 格仍查，剩 1 格停查
    fig3, axs3 = plt.subplots(1, 3, figsize=(9, 3))
    for ax, hi in zip(axs3, (1.0, 50.0, 100.0), strict=True):
        ax.plot(X, YS / 74 * hi, color=fv.HUES["vteal"], label="s")
        ax.set_ylim(0, hi)
    probs = fv.audit(fig3, scoped_ignore={("facet-ylim-mismatch", 1)})
    if not any(p.startswith("facet-ylim-mismatch") for p in probs):
        bad.append("facet-ylim still-mismatched pair went silent")
    probs = fv.audit(
        fig3,
        scoped_ignore={("facet-ylim-mismatch", 1), ("facet-ylim-mismatch", 2)},
    )
    if any(p.startswith("facet-ylim-mismatch") for p in probs):
        bad.append("facet-ylim singleton left but still fired")
    plt.close(fig3)
    return bad


def check_readback() -> list[str]:
    """rb-* 回读层：几何两条 imperative 直跑；label-diff 需 declared 才启用。"""
    bad = []

    # rb-text-collide 反例：相邻但不相交的文本（含 ncol=2 的横排图例——
    # 天然贴近的行不能算相交）
    fv.apply_rc("paper")
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="m1")
    ax.plot(X, YS - 4, color=fv.HUES["vorange"], label="m2")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.text(0.02, 0.92, "left note", transform=ax.transAxes, fontsize=8)
    ax.text(0.30, 0.92, "right note", transform=ax.transAxes, fontsize=8)
    ax.legend(loc="lower center", ncol=2)
    probs = fv.audit(fig)
    plt.close(fig)
    rb = [p for p in probs if p.startswith("rb-text-collide")]
    if rb:
        bad.append(f"rb-text-collide fired on adjacent texts: {rb}")

    # rb-text-outside 与 error 级 text-outside-figure 同源——同一违规图两路都报
    fig = fig_text_outside_figure()
    probs = fv.audit(fig)
    plt.close(fig)
    if not any(p.startswith("rb-text-outside") for p in probs):
        bad.append("rb-text-outside did not fire on caption below canvas")

    # rb-label-diff：imperative 侧 declared=None 时整条规则跳过
    fig = fig_clean_line()
    probs = fv.audit(fig)
    if any(p.startswith("rb-label-diff") for p in probs):
        bad.append("rb-label-diff ran without declared")
    # declared 与渲染一致 → 干净
    probs = fv.audit(fig, declared={"Focal", "Reference", "Baseline"})
    if any(p.startswith("rb-label-diff") for p in probs):
        bad.append(
            "rb-label-diff false positive: "
            f"{[p for p in probs if p.startswith('rb-label-diff')]}"
        )
    # 声明了没渲染 → missing
    probs = fv.audit(fig, declared={"Focal", "Reference", "Baseline", "ghost-series"})
    plt.close(fig)
    if not any(p.startswith("rb-label-diff missing 'ghost-series'") for p in probs):
        bad.append(f"rb-label-diff missing did not fire: {probs}")

    # 渲染出未声明的 identity 文本（残留标题）→ extra；系列 label 会被
    # artist label 自动并入 declared，extra 只能由标题/图例身份层触发
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(X, YS, color=fv.HUES["vteal"], label="m")
    ax.set_title("stale")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend()
    probs = fv.audit(fig, declared={"m"})
    plt.close(fig)
    if not any(p.startswith("rb-label-diff extra 'stale'") for p in probs):
        bad.append(f"rb-label-diff extra did not fire: {probs}")

    # spec 侧：fvspec.render + fvspec.declared_texts——被图例条目过滤
    # 掉的系列 label（m07 同款静默丢弃）必须报 missing
    import fvspec

    spec = {
        "version": 1,
        "theme": "paper",
        "size": "half",
        "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 3}]},
        "series": [
            {"kind": "line", "x": "x", "y": "y", "label": "shown"},
            {"kind": "line", "x": "x", "y": "y", "label": "hidden"},
        ],
        "legend": {"entries": [{"series": "as0"}]},
        "xaxis": {"label": "step"},
        "yaxis": {"label": "v"},
        "meta": {"ledger": "x=step; y=v", "caption": "cap"},
    }
    fig = fvspec.render(spec)
    probs = fvspec.audit_fig(fig, declared=fvspec.declared_texts(spec))
    plt.close(fig)
    if not any(p.startswith("rb-label-diff missing 'hidden'") for p in probs):
        bad.append(
            "rb-label-diff spec-side missing did not fire: "
            f"{[p for p in probs if p.startswith('rb-')] or probs}"
        )
    return bad


def main() -> int:
    fails = 0
    for name, builder, rule in CASES:
        fig = builder()
        probs = fv.audit(fig)
        plt.close(fig)
        if rule is None:
            ok = not probs
            detail = "" if ok else f"unexpected: {probs}"
        else:
            ok = any(p.startswith(rule) for p in probs)
            detail = "" if ok else f"want '{rule}', got: {probs}"
        print(("PASS" if ok else "FAIL"), name, detail)
        fails += 0 if ok else 1

    checks = (("audit-knobs", check_knobs), ("readback", check_readback))
    for label, fn in checks:
        bad = fn()
        ok = not bad
        print(("PASS" if ok else "FAIL"), label, "" if ok else bad)
        fails += 0 if ok else 1

    print(f"--- {len(CASES) + len(checks)} cases, {fails} failed ---")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
