#!/usr/bin/env python3
"""test_audit_rules.py — fvstyle.audit 新增/改动规则的隔离测试。

覆盖：child_axes 枚举（inset/secondary）、ignore_axes 孙轴豁免、missing-glyph、
cjk-in-mathtext、twin-axis-unlabeled、size-negative、same-field-xy、
text-too-small、low-contrast、annotation 文本框口径、cvd-clash、
palette-overflow 主题化容量、stacked bar 基线、twin 轴 facet 豁免、
severity lookup（problem_severity/format_audit_lines）。

每条规则造一张违规图（断言触发）+ 干净图（断言不触发）。fixture 都按
selftest 的"well-formed"惯例：轴标签齐全、留足边距、单无标系列要带
就地文字标注或 legend——否则别的规则会合法地报。

运行：uv run --with matplotlib --with numpy python scripts/test_audit_rules.py
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


def _base(figsize=(4.6, 3.2)):
    """一张 well-formed 单轴图：轴标签齐、右边距留白（twin 刻度不外溢）。"""
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(X, YS, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.subplots_adjust(left=0.16, right=0.8, top=0.9, bottom=0.16)
    return fig, ax


# --- fixture 构造 ------------------------------------------------------


def fig_inset_clipped():
    """inset 数据大面出限——child_axes 枚举后应被 data-clipped 抓到。"""
    fig, ax = _base()
    ins = ax.inset_axes([0.55, 0.5, 0.38, 0.38])
    ins.plot(X, YS * 10, color=fv.HUES["vorange"], label="zoom")
    ins.set_xlim(0, 2)
    ins.set_ylim(500, 800)
    ins.legend(fontsize=8)
    return fig, ins


def fig_inset_clean():
    """inset 数据都在自身限内——合法。"""
    fig, ax = _base()
    ins = ax.inset_axes([0.55, 0.5, 0.38, 0.38])
    ins.plot(X, YS, color=fv.HUES["vorange"], label="zoom")
    ins.legend(fontsize=8)
    return fig


def fig_glyph_missing():
    # DejaVu Sans 是 mpl 自带字体、确定不含 CJK——跨机器确定触发
    fig, ax = _base()
    ax.set_title("中文标题", fontfamily="DejaVu Sans")
    return fig


def fig_glyph_family_missing():
    # 整条 family 链落空 → 静默退回默认字体，属真问题
    fig, ax = _base()
    ax.set_title("hello", fontfamily="BogusFamilyXYZ123")
    return fig


def fig_glyph_clean():
    fig, ax = _base()
    ax.set_title("clean ascii")
    return fig


def fig_cjk_in_mathtext():
    # CJK 混进 $ 串 → 整条走 mathtext（stix 无 CJK 字形）→ tofu
    fig, ax = _base()
    ax.set_title("误差 $\\epsilon$ 对比")
    return fig


def fig_cjk_plain():
    # 纯 CJK 不进 mathtext——cjk-in-mathtext 不报（缺字形归 missing-glyph 管）
    fig, ax = _base()
    ax.set_title("误差对比")
    return fig


def fig_mathtext_only():
    fig, ax = _base()
    ax.set_title("$\\epsilon$ decay")
    return fig


def fig_cjk_lone_dollar():
    # 落单的 $ 按字面渲染、不进 mathtext——不报
    fig, ax = _base()
    ax.set_title("成本 $5 元")
    return fig


def fig_ann_arrow_over_data():
    # annotate 箭头跨线但文本框不压数据——文本框口径下不报
    fig, ax = _base()
    ax.set_ylim(48, 78)
    ax.annotate(
        "peak",
        xy=(3.5, 72),
        xytext=(4.6, 54),
        arrowprops=dict(arrowstyle="->", color=fv.NEUTRALS["vink"]),
    )
    return fig


def fig_ann_text_over_data():
    # annotate 文本框真压线——仍要报（箭头不是赦免牌）
    fig, ax = _base()
    ax.annotate(
        "oncurve",
        xy=(5, 74),
        xytext=(2, 61),
        va="center",
        arrowprops=dict(arrowstyle="->", color=fv.NEUTRALS["vink"]),
    )
    return fig


def fig_inset_grandchild():
    """inset 里再开 inset（孙轴），孙轴有 log<=0 数据。"""
    fig, ax = _base()
    ins = ax.inset_axes([0.55, 0.4, 0.38, 0.38])
    ins.plot(X, YS, color=fv.HUES["vorange"], label="zoom")
    ins.legend(fontsize=8)
    ins2 = ins.inset_axes([0.5, 0.5, 0.45, 0.45])
    ins2.plot(X, np.array([1, -2, 3, 4, 5, 6.0]), color=fv.HUES["vrose"])
    ins2.set_yscale("log")
    return fig, ins


def fig_twin_unlabeled():
    fig, ax = _base()
    ax2 = ax.twinx()
    ax2.plot(X, YS * 100, color=fv.HUES["vorange"], label="s2")
    return fig


def fig_twin_labeled():
    fig, ax = _base()
    ax2 = ax.twinx()
    ax2.plot(X, YS * 100, color=fv.HUES["vorange"], label="s2")
    ax2.set_ylabel("y2")
    return fig


def fig_secondary_unlabeled():
    fig, ax = _base()
    ax.secondary_yaxis("right")
    return fig


def fig_secondary_labeled():
    fig, ax = _base()
    sec = ax.secondary_yaxis("right")
    sec.set_ylabel("converted")
    return fig


def fig_size_negative():
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.scatter([1, 2, 3], [4, 5, 6], s=[10, -5, 20], color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.subplots_adjust(left=0.16, right=0.9, top=0.9, bottom=0.16)
    return fig


def fig_size_positive():
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.scatter([1, 2, 3], [4, 5, 6], s=[10, 15, 20], color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.subplots_adjust(left=0.16, right=0.9, top=0.9, bottom=0.16)
    return fig


def fig_same_field_xy():
    # 两列字段复制粘贴成同一数组——至少 2 个点才报
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.scatter([1, 2, 3], [1, 2, 3], s=20, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.subplots_adjust(left=0.16, right=0.9, top=0.9, bottom=0.16)
    return fig


def fig_distinct_xy():
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.scatter([1, 2, 3], [4, 5, 6], s=20, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.subplots_adjust(left=0.16, right=0.9, top=0.9, bottom=0.16)
    return fig


def fig_single_point_xy():
    # 单点 x==y 是巧合不报
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.scatter([2], [2], s=20, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.subplots_adjust(left=0.16, right=0.9, top=0.9, bottom=0.16)
    return fig


def fig_text_too_small():
    fig, ax = _base()
    ax.text(0.5, 0.5, "tiny note", transform=ax.transAxes, fontsize=4)
    return fig


def fig_text_ok():
    fig, ax = _base()
    ax.text(0.5, 0.5, "normal note", transform=ax.transAxes, fontsize=8)
    return fig


def fig_text_small_relative():
    # spec_bar 的先例：base 7.6 的小版面里 5.8pt 标签是刻意缩放，不报
    with plt.rc_context({"font.size": 7.6}):
        fig, ax = _base()
        ax.text(0.5, 0.5, "small note", transform=ax.transAxes, fontsize=5.8)
        probs = fv.audit(fig)
    return fig, probs


def fig_low_contrast():
    fig, ax = _base()
    t = ax.text(
        0.5,
        0.5,
        "washed out",
        transform=ax.transAxes,
        fontsize=10,
        color="#F2F3F4",
    )
    t.set_gid("fv-neutral")  # 只隔离 offpalette——颜色本就不是调色板色
    return fig


def fig_contrast_ok():
    fig, ax = _base()
    ax.text(0.5, 0.5, "readable", transform=ax.transAxes, fontsize=10)
    return fig


def fig_cvd_clash():
    # vrose-vgray 在 protanopia 模拟下 Δ≈0.007——调色板内的真冲突对
    fig, ax = _base()
    ax.plot(X, YS - 5, color=fv.HUES["vrose"], label="a")
    ax.plot(X, YS - 10, color=fv.HUES["vgray"], label="b")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    return fig


def fig_cvd_clean():
    fig, ax = _base()
    ax.plot(X, YS - 5, color=fv.HUES["vorange"], label="b")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    return fig


def fig_mono_overflow():
    fv.apply_rc("mono")
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    for i, c in enumerate(fv.series_colors("mono", 6)):
        ax.plot(X, YS - 3 * i, color=c, label=f"m{i}")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.subplots_adjust(right=0.76)
    return fig


def fig_paper_six():
    fv.apply_rc("paper")
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    for i, c in enumerate(fv.series_colors("paper", 6)):
        ax.plot(X, YS - 3 * i, color=c, label=f"m{i}")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.subplots_adjust(right=0.76)
    return fig


def fig_stacked_truncated():
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar([0, 1, 2], [55, 57, 59], color=fv.HUES["vteal"], label="a")
    ax.bar(
        [0, 1, 2],
        [2, 1, 2],
        bottom=[55, 57, 59],
        color=fv.HUES["vorange"],
        label="b",
    )
    ax.set_ylim(50, 65)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(right=0.76)
    return fig


def fig_stacked_clean():
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar([0, 1, 2], [3, 4, 5], color=fv.HUES["vteal"], label="a")
    ax.bar([0, 1, 2], [2, 1, 2], bottom=[3, 4, 5], color=fv.HUES["vorange"], label="b")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(right=0.76)
    return fig


def fig_diverging_stacked_truncated():
    # 正负两方向堆叠：公共锚边 0 在 ylim 外
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar([0, 1, 2], [3, 4, 5], color=fv.HUES["vteal"], label="up")
    ax.bar([0, 1, 2], [-1, -2, -1], color=fv.HUES["vcoral"], label="down")
    ax.set_ylim(0.5, 6)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(right=0.76)
    return fig


def fig_waterfall():
    # 瀑布柱（各 x 独立、无公共锚边）不是同基线柱组——不报
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar([0, 1, 2], [5, 3, 2], bottom=[0, 5, 8], color=fv.HUES["vteal"], label="wf")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(right=0.76)
    return fig


def fig_barh_stacked_truncated():
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.barh([0, 1, 2], [50, 55, 60], color=fv.HUES["vteal"], label="a")
    ax.barh(
        [0, 1, 2], [5, 4, 3], left=[50, 55, 60], color=fv.HUES["vorange"], label="b"
    )
    ax.set_xlim(40, 70)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(right=0.76)
    return fig


def fig_twin_facet_exempt():
    # 单宿主 + twinx：两轴合法地各有一把 y 尺，不得算 facet 失配
    fig, ax = _base()
    ax2 = ax.twinx()
    ax2.plot(X, YS * 100, color=fv.HUES["vorange"], label="s2")
    ax2.set_ylabel("y2")
    return fig


def fig_twin_drifted():
    # 宿主经手动 set_position 移位后等位判定失效，交叠判定仍须认出孪生
    fig, ax = _base()
    ax2 = ax.twinx()
    ax2.plot(X, YS * 100, color=fv.HUES["vorange"], label="s2")
    ax2.set_ylabel("y2")
    fig.canvas.draw()
    pos = ax.get_position()
    ax.set_position([pos.x0, pos.y0, pos.width - 0.04, pos.height])
    return fig


def fig_real_facet_mismatch():
    # 真 facet：同行两格共享量纲声明却不同刻度——仍须报
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    for ax, hi in zip(axs, (1.0, 100.0), strict=True):
        ax.plot(X, YS / 74 * hi, color=fv.HUES["vteal"], label="s")
        ax.set_ylabel("Score")
        ax.set_xlabel("x")
        ax.set_ylim(0, hi)
    fig.tight_layout()
    return fig


def fig_facet_with_secondary():
    # 宿主带 secondary 轴：secondary 无系列，但枚举后不得搅浑行比较
    fig, axs = plt.subplots(1, 2, figsize=(7, 3))
    for ax in axs:
        ax.plot(X, YS, color=fv.HUES["vteal"], label="s")
        ax.set_ylabel("Score")
        ax.set_xlabel("x")
    axs[1].secondary_yaxis("right").set_ylabel("conv")
    fig.tight_layout()
    return fig


# --- 断言辅助 --------------------------------------------------------------


def rules_of(probs):
    return {p.split(" ", 1)[0] for p in probs}


def check(name, fig, *, fire=None, clean_rules=(), close=True, **kw):
    """fire: 必须命中的规则名集合；clean_rules: 不得命中的规则名集合。"""
    probs = fv.audit(fig, **kw)
    got = rules_of(probs)
    bad = []
    for r in fire or ():
        if r not in got:
            bad.append(f"want {r}, got {sorted(got)}")
    for r in clean_rules:
        if r in got:
            bad.append(
                f"{r} should stay silent, got {[p for p in probs if p.startswith(r)]}"
            )
    if close:
        plt.close(fig)
    return name, bad, probs


def main() -> int:
    results = []

    # --- child_axes 枚举（inset 进审计面、扩展索引可用） --------------------
    fig, ins = fig_inset_clipped()
    results.append(
        check(
            "inset-clipped-seen",
            fig,
            fire={"data-clipped-outside-limits"},
            close=False,
        )
    )
    probs = fv.audit(fig, ignore_axes=[ins])
    bad = [
        p
        for p in probs
        if p.startswith("data-clipped-outside-limits") and "axes 1" in p
    ]
    results.append(("inset-ignored-by-obj", ["ignore_axes=[obj] miss"] if bad else []))
    probs = fv.audit(fig, ignore_axes=[1])  # child 追加在 fig axes 后 → 索引 1
    bad = [
        p
        for p in probs
        if p.startswith("data-clipped-outside-limits") and "axes 1" in p
    ]
    results.append(("inset-ignored-by-index", ["ignore_axes=[1] miss"] if bad else []))
    probs = fv.audit(fig, scoped_ignore={("data-clipped-outside-limits", 1)})
    bad = [
        p
        for p in probs
        if p.startswith("data-clipped-outside-limits") and "axes 1" in p
    ]
    results.append(("inset-scoped-ignore", ["scoped_ignore miss"] if bad else []))
    plt.close(fig)
    results.append(
        check(
            "inset-clean",
            fig_inset_clean(),
            clean_rules={"data-clipped-outside-limits"},
        )
    )
    # ignore_axes 豁免半径覆盖孙轴：inset 上再开的 inset（child_axes 的
    # child_axes）同样被豁免
    fig, ins = fig_inset_grandchild()
    results.append(
        check(
            "grandchild-seen",
            fig,
            fire={"log-nonpositive-data"},
            close=False,
        )
    )
    probs = fv.audit(fig, ignore_axes=[ins])
    results.append(
        (
            "grandchild-ignored",
            [p for p in probs if p.startswith("log-nonpositive-data")],
        )
    )
    plt.close(fig)
    # log-nonpositive-data 报错须指路 symlog 逃生舱（imperative
    # set_*scale('symlog', linthresh=…) / spec scale:'symlog'）
    fig, _ins = fig_inset_grandchild()
    probs = fv.audit(fig)
    plt.close(fig)
    fired = [p for p in probs if p.startswith("log-nonpositive-data")]
    results.append(
        (
            "log-nonpositive-symlog-hint",
            [] if fired and all("symlog" in p for p in fired) else [f"{fired}"],
        )
    )

    # --- missing-glyph（error：确定性探测，不依赖 draw 时序） ---------------
    results.append(check("glyph-missing", fig_glyph_missing(), fire={"missing-glyph"}))
    results.append(
        check(
            "glyph-family-missing", fig_glyph_family_missing(), fire={"missing-glyph"}
        )
    )
    results.append(
        check("glyph-clean", fig_glyph_clean(), clean_rules={"missing-glyph"})
    )
    # CJK 混进 $ 串 → 整条走 mathtext（stix 无 CJK）→ tofu；收割抓
    # 'does not have a glyph' 措辞，cjk-in-mathtext 做确定性兜底
    results.append(
        check("cjk-in-mathtext", fig_cjk_in_mathtext(), fire={"cjk-in-mathtext"})
    )
    results.append(
        check(
            "cjk-plain-no-mathtext",
            fig_cjk_plain(),
            clean_rules={"cjk-in-mathtext"},
        )
    )
    results.append(
        check(
            "mathtext-only-no-cjk",
            fig_mathtext_only(),
            clean_rules={"cjk-in-mathtext"},
        )
    )
    results.append(
        check(
            "cjk-lone-dollar",
            fig_cjk_lone_dollar(),
            clean_rules={"cjk-in-mathtext"},
        )
    )
    # 缺字形是 error 严重度——统一格式下必须进 ERR 行
    fig = fig_glyph_missing()
    lines = fv.format_audit_lines(fv.audit(fig, rules={"missing-glyph"}))
    plt.close(fig)
    results.append(
        (
            "glyph-is-error-severity",
            []
            if all(ln.startswith("ERR missing-glyph:") for ln in lines) and lines
            else [f"bad lines {lines}"],
        )
    )

    # --- twin-axis-unlabeled ----------------------------------------------
    results.append(
        check("twin-unlabeled", fig_twin_unlabeled(), fire={"twin-axis-unlabeled"})
    )
    results.append(
        check(
            "twin-labeled",
            fig_twin_labeled(),
            clean_rules={"twin-axis-unlabeled", "facet-ylim-mismatch"},
        )
    )
    results.append(
        check(
            "secondary-unlabeled",
            fig_secondary_unlabeled(),
            fire={"twin-axis-unlabeled"},
        )
    )
    results.append(
        check(
            "secondary-labeled",
            fig_secondary_labeled(),
            clean_rules={"twin-axis-unlabeled"},
        )
    )

    # --- scatter 数据完整性 ------------------------------------------------
    results.append(check("size-negative", fig_size_negative(), fire={"size-negative"}))
    results.append(
        check("size-positive", fig_size_positive(), clean_rules={"size-negative"})
    )
    results.append(check("same-field-xy", fig_same_field_xy(), fire={"same-field-xy"}))
    results.append(
        check("distinct-xy", fig_distinct_xy(), clean_rules={"same-field-xy"})
    )
    results.append(
        check(
            "single-point-xy",
            fig_single_point_xy(),
            clean_rules={"same-field-xy"},
        )
    )
    # scoped_ignore 对新规则生效
    fig = fig_size_negative()
    probs = fv.audit(fig, scoped_ignore={("size-negative", 0)})
    plt.close(fig)
    results.append(
        (
            "size-negative-scoped",
            [p for p in probs if p.startswith("size-negative")],
        )
    )

    # --- 文本可读性 --------------------------------------------------------
    results.append(
        check("text-too-small", fig_text_too_small(), fire={"text-too-small"})
    )
    results.append(check("text-ok", fig_text_ok(), clean_rules={"text-too-small"}))
    fig, probs = fig_text_small_relative()
    plt.close(fig)
    results.append(
        (
            "text-small-relative",
            [p for p in probs if p.startswith("text-too-small")],
        )
    )
    results.append(check("low-contrast", fig_low_contrast(), fire={"low-contrast"}))
    results.append(
        check("contrast-ok", fig_contrast_ok(), clean_rules={"low-contrast"})
    )

    # --- annotation 文本框口径 ----------------------------------------------
    # Annotation.get_window_extent 含箭头并集——箭头跨线不算文字压数据，
    # 文本框真压线仍要报
    results.append(
        check(
            "ann-arrow-over-data",
            fig_ann_arrow_over_data(),
            clean_rules={"text-overlaps-data"},
        )
    )
    results.append(
        check(
            "ann-text-over-data",
            fig_ann_text_over_data(),
            fire={"text-overlaps-data"},
        )
    )

    # --- cvd-clash ---------------------------------------------------------
    results.append(check("cvd-clash", fig_cvd_clash(), fire={"cvd-clash"}))
    results.append(check("cvd-clean", fig_cvd_clean(), clean_rules={"cvd-clash"}))

    # --- palette-overflow 主题化容量 ----------------------------------------
    probs = fv.audit(fig_mono_overflow())
    results.append(
        (
            "mono-overflow-6",
            []
            if any("palette-overflow" in p and "mono palette 5" in p for p in probs)
            else [f"missing themed cap: {probs}"],
        )
    )
    results.append(
        check(
            "paper-six-ok",
            fig_paper_six(),
            clean_rules={"palette-overflow"},
        )
    )
    # theme_name 显式覆盖：paper 图按 mono 容量审
    fig = fig_paper_six()
    probs = fv.audit(fig, theme_name="mono")
    plt.close(fig)
    results.append(
        (
            "theme-override",
            []
            if any(p.startswith("palette-overflow") for p in probs)
            else ["theme_name='mono' did not tighten cap"],
        )
    )

    # --- stacked bar 基线 ---------------------------------------------------
    results.append(
        check(
            "stacked-truncated",
            fig_stacked_truncated(),
            fire={"bar-baseline-truncated"},
        )
    )
    results.append(
        check(
            "stacked-clean",
            fig_stacked_clean(),
            clean_rules={"bar-baseline-truncated"},
        )
    )
    results.append(
        check(
            "diverging-stacked-truncated",
            fig_diverging_stacked_truncated(),
            fire={"bar-baseline-truncated"},
        )
    )
    results.append(
        check(
            "waterfall-not-bar",
            fig_waterfall(),
            clean_rules={"bar-baseline-truncated"},
        )
    )
    results.append(
        check(
            "barh-stacked-truncated",
            fig_barh_stacked_truncated(),
            fire={"bar-baseline-truncated"},
        )
    )

    # --- twin 轴 facet 豁免 -------------------------------------------------
    results.append(
        check(
            "twin-facet-exempt",
            fig_twin_facet_exempt(),
            clean_rules={"facet-ylim-mismatch"},
        )
    )
    results.append(
        check(
            "twin-drifted-exempt",
            fig_twin_drifted(),
            clean_rules={"facet-ylim-mismatch"},
        )
    )
    results.append(
        check(
            "real-facet-fires",
            fig_real_facet_mismatch(),
            fire={"facet-ylim-mismatch"},
        )
    )
    results.append(
        check(
            "facet-with-secondary",
            fig_facet_with_secondary(),
            clean_rules={"facet-ylim-mismatch", "twin-axis-unlabeled"},
        )
    )

    # --- severity 查表 ----------------------------------------------------
    bad = []
    if fv.problem_severity("collide text 'a' x 'b'") != "error":
        bad.append("collide should be error")
    if fv.problem_severity("data-clipped-outside-limits axes 0 's': 50%") != "warn":
        bad.append("data-clipped should be warn")
    if fv.problem_severity("missing-glyph x") != "error":
        bad.append("missing-glyph should be error")
    if fv.problem_severity("cvd-clash axes 0: a") != "warn":
        bad.append("cvd-clash should be warn")
    lines = fv.format_audit_lines(
        ["collide text 'a' x 'b'", "hue-budget 5 hue families: []"]
    )
    if lines != ["ERR collide: text 'a' x 'b'", "warn hue-budget: 5 hue families: []"]:
        bad.append(f"format_audit_lines wrong: {lines}")
    results.append(("severity-lookup", bad))

    # 新规则名可被 rules=/ignore= 接受（打错字才该炸）
    fig, _ax = _base()
    try:
        fv.audit(fig, rules={"missing-glyph", "cvd-clash", "twin-axis-unlabeled"})
        fv.audit(fig, ignore={"size-negative", "same-field-xy"})
    except ValueError as e:
        results.append(("rule-names-accepted", [str(e)]))
    else:
        results.append(("rule-names-accepted", []))
    plt.close(fig)

    fails = 0
    for name, bad, *rest in results:
        ok = not bad
        print(("PASS" if ok else "FAIL"), name, "" if ok else bad)
        fails += 0 if ok else 1
    print(f"--- {len(results)} cases, {fails} failed ---")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
