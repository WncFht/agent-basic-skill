#!/usr/bin/env python3
"""test_audit_mpl2.py — 审计盲区补规则的隔离测试（audit-blindspot 探针驱动）。

覆盖：text-overlaps-data（ax.texts/annotate 压线/压点/压柱）、collide 与
rb-text-collide 的旋转文本感知（AABB 虚警消除、真撞仍抓）、offpalette 的
cmap 化 artist 豁免（streamplot FancyArrowPatch）、mark_neutral、ramp_cmap、
legend-coverage 的 sharey 兄弟 ylabel 认定、ax.artists offsetbox 注入文本的
全链可见性（collide/text-overlaps-data/offpalette/missing-glyph）、
shared-axis-misaligned（sharex/sharey 组像素错位）、text-spills-axes
（锚点轴内、墨迹越框）。

fixture 按 test_audit_rules 的 well-formed 惯例：轴标签齐全、图例/就地标注
就位——只让被测规则有话可说。

运行：uv run --with matplotlib --with numpy python scripts/test_audit_mpl2.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check

mpl.use("Agg")

import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.artist import Artist
from matplotlib.offsetbox import AnchoredOffsetbox, AnchoredText, TextArea


def rules_of(probs):
    return {p.split(" ", 1)[0] for p in probs}


X = np.arange(8)
YS = np.array([50, 55, 61, 64, 70, 74, 80, 86])


def base(figsize=(4.6, 3.2)):
    """well-formed 单轴图：轴标签齐、图例外挂（不占轴内空间）。"""
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(X, YS, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(left=0.16, right=0.78, top=0.9, bottom=0.18)
    return fig, ax


def audit_rules(fig, **kw):
    probs = fv.audit(fig, **kw)
    plt.close(fig)
    return probs, rules_of(probs)


# --- 旋转文本的碰撞判定 ------------------------------------------------------


def rotated_ticks():
    """30° 旋转刻度标签：AABB 两两相交、真四边形分离——旧代码 ERR collide
    全中，新判定静默（audit-blindspot/m07 同款虚警）。"""
    fig, ax = base()
    ax.set_xticks(X, [f"item-{i:02d}" for i in range(8)], rotation=30)
    probs, rules = audit_rules(fig)
    check(
        "rot-ticks-no-collide",
        "collide" not in rules and "rb-text-collide" not in rules,
        f"{probs}",
    )


def rotated_real_collide():
    """两个同位 30° 文本：真四边形重叠——collide/rb-text-collide 仍抓。"""
    fig, ax = base()
    ax.text(4, 52, "AAAA", rotation=30, fontsize=14)
    ax.text(4, 52, "BBBB", rotation=30, fontsize=14)
    probs, rules = audit_rules(fig)
    check(
        "rot-real-collide",
        "collide" in rules and "rb-text-collide" in rules,
        f"{probs}",
    )


def unrotated_collide():
    """未旋转文本相交——collide 语义不变（quad 退化为 AABB）。"""
    fig, ax = base()
    ax.text(4, 52, "same place one")
    ax.text(4, 52, "same place two")
    probs, rules = audit_rules(fig)
    check("unrotated-collide", "collide" in rules, f"{probs}")


def text_quad_shape():
    """_text_quad 重建四边形的 AABB 必须等于实测 window extent。"""
    fig, ax = base()
    t = ax.text(4, 52, "rotated label", rotation=37)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    bb = t.get_window_extent(r)
    q = fv._text_quad(t, bb, r)
    plt.close(fig)
    got = [q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()]
    want = [bb.x0, bb.y0, bb.x1, bb.y1]
    check("text-quad-aabb", np.allclose(got, want, atol=0.5), f"{got} vs {want}")
    # 四边形面积必须严格小于 AABB（旋转才有意义）
    check(
        "text-quad-tighter",
        abs(fv._quad_area(q)) < bb.width * bb.height * 0.95,
        f"quad area {abs(fv._quad_area(q)):.1f} vs aabb {bb.width * bb.height:.1f}",
    )


# --- text-overlaps-data ------------------------------------------------------


def note_on_vertex():
    """note 正中压在折线顶点上——audit-blindspot (b) 原型。"""
    fig, ax = base()
    ax.text(3, YS[3], "checkpoint", ha="center", va="center")
    probs, rules = audit_rules(fig)
    check("note-on-vertex", "text-overlaps-data" in rules, f"{probs}")


def note_mid_segment():
    """两点长线段的非中点位置压线：顶点+段中点都在框外，靠段边穿越抓到。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.plot([0, 10], [0, 10], color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    ax.text(7, 7, "off-mid", ha="center", va="center")
    fig.subplots_adjust(left=0.16, right=0.78, top=0.9, bottom=0.18)
    probs, rules = audit_rules(fig)
    check("note-mid-segment", "text-overlaps-data" in rules, f"{probs}")


def note_on_marker():
    """note 盖住散点 marker 中心。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.scatter([2, 4, 6], [50, 60, 70], s=36, color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    ax.text(4, 60, "on point", ha="center", va="center")
    fig.subplots_adjust(left=0.16, right=0.78, top=0.9, bottom=0.18)
    probs, rules = audit_rules(fig)
    check("note-on-marker", "text-overlaps-data" in rules, f"{probs}")


def annotate_on_line():
    """ax.annotate 落进 ax.texts，同样受检。"""
    fig, ax = base()
    ax.annotate("hit", xy=(2, YS[2]), xytext=(2, YS[2]), ha="center", va="center")
    probs, rules = audit_rules(fig)
    check("annotate-on-line", "text-overlaps-data" in rules, f"{probs}")


def note_in_bar():
    """文字落在柱体内部——patch 墨水按较小框 20% 计。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar([0, 1, 2], [3, 4, 5], color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="upper left")
    ax.text(1, 2, "inside bar", ha="center", va="center")
    fig.subplots_adjust(right=0.85)
    probs, rules = audit_rules(fig)
    check("note-in-bar", "text-overlaps-data" in rules, f"{probs}")


def note_quiet():
    """空白区的 note 不报。"""
    fig, ax = base()
    ax.text(6, 51, "quiet corner", ha="center", va="center")
    probs, rules = audit_rules(fig)
    check("note-quiet", "text-overlaps-data" not in rules, f"{probs}")


def bar_label_above():
    """bar_label 顶标贴在柱外——patch 相交为零，不报。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar([0, 1, 2], [3, 4, 5], color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="upper left")
    ax.bar_label(ax.containers[0], padding=3)
    fig.subplots_adjust(right=0.85)
    probs, rules = audit_rules(fig)
    check("bar-label-above", "text-overlaps-data" not in rules, f"{probs}")


def heat_annotate():
    """heat 格内注记压在 QuadMesh 上——遮挡语义由色条承担，不报。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    z = np.arange(12).reshape(3, 4).astype(float)
    mesh = ax.pcolormesh(np.arange(5), np.arange(4), z, cmap=fv.ramp_cmap("seq"))
    for i in range(3):
        for j in range(4):
            ax.text(j + 0.5, i + 0.5, f"{z[i, j]:.0f}", ha="center", va="center")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.colorbar(mesh, ax=ax)
    probs, rules = audit_rules(fig)
    check("heat-annotate", "text-overlaps-data" not in rules, f"{probs}")


def legend_text_not_text_rule():
    """图例文字压数据归 legend-overlaps-data——不重复进 text-overlaps-data。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center")
    probs, rules = audit_rules(fig)
    check(
        "legend-cover-routing",
        "legend-overlaps-data" in rules and "text-overlaps-data" not in rules,
        f"{probs}",
    )


def text_ink_scoped_ignore():
    """scoped_ignore 对 text-overlaps-data 生效。"""
    fig, ax = base()
    ax.text(3, YS[3], "checkpoint", ha="center", va="center")
    probs = fv.audit(fig, scoped_ignore={("text-overlaps-data", 0)})
    plt.close(fig)
    check(
        "text-ink-scoped",
        not any(p.startswith("text-overlaps-data") for p in probs),
        f"{probs}",
    )


def text_ink_is_warn():
    check(
        "text-ink-warn",
        fv.problem_severity("text-overlaps-data axes 0 'a' x 's'") == "warn",
    )


# --- offpalette 的 cmap 化 artist 豁免 ----------------------------------------


def _stream_ax():
    x = np.linspace(-3, 3, 30)
    y = np.linspace(-3, 3, 30)
    xx, yy = np.meshgrid(x, y)
    speed = np.hypot(xx, yy)
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    ax.streamplot(xx, yy, -yy, xx, color=speed, cmap="viridis")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig, ax


def streamplot_cmap_exempt():
    """streamplot 箭头（FancyArrowPatch，无 get_array）的 viridis 色豁免。"""
    fig, ax = _stream_ax()
    probs, rules = audit_rules(fig)
    check("streamplot-cmap", "offpalette" not in rules, f"{probs}")


def rogue_in_cmap_axes():
    """cmap 轴上的非 cmap 色 patch 仍抓——豁免不放行任意色。"""
    fig, ax = _stream_ax()
    ax.add_patch(plt.Rectangle((-2, -2), 1, 1, color="#FF0000"))
    probs, rules = audit_rules(fig)
    check("rogue-in-cmap-axes", "offpalette" in rules, f"{probs}")


def rogue_plain_axes():
    fig, ax = base()
    ax.add_patch(plt.Rectangle((1, 51), 0.5, 3, color="#FF0000"))
    probs, rules = audit_rules(fig)
    check("rogue-plain-axes", "offpalette" in rules, f"{probs}")


# --- mark_neutral / ramp_cmap -------------------------------------------------


def mark_neutral_works():
    """中性 artist 不进 series 计数：无标 overlay 线标记后 coverage 静默。"""
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s")
    ln = ax.plot([0, 5], [0.2, 1.2], color=fv.HUES["vgray"])[0]
    fv.mark_neutral(ln)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(left=0.16, right=0.78, top=0.9, bottom=0.18)
    probs, rules = audit_rules(fig)
    check(
        "mark-neutral",
        ln.get_gid() == "fv-neutral" and "legend-coverage" not in rules,
        f"gid={ln.get_gid()!r} probs={probs}",
    )
    # 对照：不标则匿名系列必须被 coverage 抓到
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s")
    ax.plot([0, 5], [0.2, 1.2], color=fv.HUES["vgray"])
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.subplots_adjust(left=0.16, right=0.78, top=0.9, bottom=0.18)
    probs, rules = audit_rules(fig)
    check("unmarked-coverage", "legend-coverage" in rules, f"{probs}")


def ramp_cmap_works():
    seq = fv.ramp_cmap("seq")
    check(
        "ramp-seq-ends",
        np.allclose(seq(0.0)[:3], fv.to_rgba(fv.NEUTRALS["paper"])[:3])
        and np.allclose(seq(1.0)[:3], fv.to_rgba(fv.HUES["vteal"])[:3]),
        f"{seq(0.0)} {seq(1.0)}",
    )
    div = fv.ramp_cmap("div")
    # from_list 量化为 256 节点：端点精确，中点落在 LUT 相邻节点间（~0.997）。
    check(
        "ramp-div-ends",
        np.allclose(div(0.0)[:3], fv.to_rgba(fv.HUES["vcoral"])[:3])
        and np.allclose(div(0.5)[:3], fv.to_rgba(fv.NEUTRALS["paper"])[:3], atol=0.01)
        and np.allclose(div(1.0)[:3], fv.to_rgba(fv.HUES["vteal"])[:3]),
        f"{div(0.0)} {div(0.5)} {div(1.0)}",
    )
    check("ramp-registered", fv.ramp_cmap("viridis") is not None)
    seq.set_bad("#FF0000")
    check(
        "ramp-independent",
        tuple(fv.ramp_cmap("seq").get_bad()) != tuple(seq.get_bad()),
    )
    try:
        fv.ramp_cmap("bogus-name-xyz")
        check("ramp-unknown", False, "no raise")
    except ValueError:
        check("ramp-unknown", True)


# --- legend-coverage 的 sharey 认定 --------------------------------------------


def sharey_sibling_label():
    """sharey 组非首位成员：本轴 ylabel 被收起、兄弟轴标签即全组量纲——
    单无标系列不再被 ghost-cover 误伤。"""
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(7, 3), sharey=True)
    a0.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s0")
    a0.set_ylabel("Score")
    a0.set_xlabel("x")
    a0.legend(fontsize=8)
    a1.plot([0, 5], [0.5, 1.5], color=fv.HUES["vteal"])
    a1.set_xlabel("x")
    fig.subplots_adjust(wspace=0.05)
    probs = fv.audit(fig)
    plt.close(fig)
    check(
        "sharey-coverage",
        not any(p.startswith("legend-coverage") and "axes 1" in p for p in probs),
        f"{probs}",
    )


# --- offsetbox 注入文本（audit-blindspot 实证的 ax.artists 盲区） --------------


def ob_collide():
    """AnchoredOffsetbox/TextArea 注入的文本与 ax.text 同位——collide 必须看见。"""
    fig, ax = base()
    ax.text(0.5, 0.5, "center note", transform=ax.transAxes, ha="center", va="center")
    ax.add_artist(
        AnchoredOffsetbox(child=TextArea("ob text"), loc="center", frameon=False)
    )
    probs, rules = audit_rules(fig)
    check("ob-collide", "collide" in rules, f"{probs}")


def ob_overlaps_data():
    """offsetbox 文本压数据线——text-overlaps-data 链同样要看见。"""
    fig, ax = base()
    ax.add_artist(
        AnchoredOffsetbox(child=TextArea("ob on line"), loc="center", frameon=False)
    )
    probs, rules = audit_rules(fig)
    check("ob-overlaps-data", "text-overlaps-data" in rules, f"{probs}")


def ob_offpalette_glyph():
    """offpalette 与 missing-glyph 走同一收割通道，各造一例。"""
    fig, ax = base()
    ax.add_artist(
        AnchoredOffsetbox(
            child=TextArea("rogue", textprops=dict(color="#FF0000")),
            loc="lower right",
            frameon=False,
        )
    )
    probs, rules = audit_rules(fig)
    check("ob-offpalette", "offpalette" in rules, f"{probs}")

    fig, ax = base()
    ax.add_artist(
        AnchoredOffsetbox(
            child=TextArea("中文", textprops=dict(fontfamily="DejaVu Sans")),
            loc="lower right",
            frameon=False,
        )
    )
    probs, rules = audit_rules(fig)
    check("ob-missing-glyph", "missing-glyph" in rules, f"{probs}")


def ob_invisible_skipped():
    """不可见 offsetbox 子树不收割——子 transform 未定位会量出假框。"""
    fig, ax = base()
    aob = AnchoredOffsetbox(
        child=TextArea("ghost", textprops=dict(color="#FF0000")),
        loc="center",
        frameon=False,
    )
    aob.set_visible(False)
    ax.add_artist(aob)
    probs, rules = audit_rules(fig)
    check(
        "ob-invisible",
        "offpalette" not in rules and "collide" not in rules,
        f"{probs}",
    )


def ob_clean():
    """正常落位的 AnchoredText 不引入新报告。"""
    fig, ax = base()
    ax.add_artist(AnchoredText("corner", loc="upper left", frameon=False))
    probs, rules = audit_rules(fig)
    check(
        "ob-clean",
        "collide" not in rules and "text-overlaps-data" not in rules,
        f"{probs}",
    )


def ob_double_registered():
    """同一 Text 同时挂 ax.texts 与 ax.artists 容器树（mpl 版本差/自定义
    artist）——收割去重，不得让 collide 把它跟自己配对。"""

    class _Holder(Artist):
        def __init__(self, t):
            super().__init__()
            self._t = t

        def get_children(self):
            return [self._t]

        def draw(self, renderer):
            pass

    fig, ax = base()
    t = ax.text(0.5, 0.5, "registered twice", transform=ax.transAxes)
    ax.add_artist(_Holder(t))
    probs, rules = audit_rules(fig)
    check("ob-double-registered", "collide" not in rules, f"{probs}")


# --- shared-axis-misaligned -----------------------------------------------------


def sharex_aspect_misaligned():
    """aspect:'equal' + 竖排 sharex：主面板横向内缩、x 边与兄弟错位——
    diag-calibration 实锤的静默缺口。"""
    fig, axs = plt.subplots(2, 1, figsize=(5, 5), sharex=True)
    axs[0].plot([0, 1], [0, 5], color=fv.HUES["vteal"], label="s")
    axs[0].set_aspect("equal")
    axs[1].plot([0, 10], [0, 2], color=fv.HUES["vteal"], label="s")
    probs, rules = audit_rules(fig, rules={"shared-axis-misaligned"})
    check("sharex-aspect", "shared-axis-misaligned" in rules, f"{probs}")


def sharey_aspect_misaligned():
    """横排 sharey + aspect equal：宽 xrange 使面板纵向内缩、y 边错位——同样报。"""
    fig, axs = plt.subplots(1, 2, figsize=(6, 3), sharey=True)
    axs[0].plot([0, 20], [0, 10], color=fv.HUES["vteal"], label="s")
    axs[0].set_xlim(0, 20)
    axs[0].set_aspect("equal")
    axs[1].plot([0, 2], [0, 8], color=fv.HUES["vteal"], label="s")
    axs[1].set_ylim(0, 10)
    probs, rules = audit_rules(fig, rules={"shared-axis-misaligned"})
    check("sharey-aspect", "shared-axis-misaligned" in rules, f"{probs}")


def sharex_aligned_clean():
    """常规 sharex 竖排 x 边像素对齐——不报。"""
    fig, axs = plt.subplots(2, 1, figsize=(5, 4), sharex=True)
    for ax in axs:
        ax.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s")
    probs, rules = audit_rules(fig, rules={"shared-axis-misaligned"})
    check("sharex-aligned", "shared-axis-misaligned" not in rules, f"{probs}")


def sharex_scoped_exempt():
    """scoped_ignore 把成员移出比较组——剩单格不报。"""
    fig, axs = plt.subplots(2, 1, figsize=(5, 5), sharex=True)
    axs[0].plot([0, 1], [0, 5], color=fv.HUES["vteal"], label="s")
    axs[0].set_aspect("equal")
    axs[1].plot([0, 10], [0, 2], color=fv.HUES["vteal"], label="s")
    probs = fv.audit(fig, scoped_ignore={("shared-axis-misaligned", 0)})
    plt.close(fig)
    check(
        "sharex-scoped",
        not any(p.startswith("shared-axis-misaligned") for p in probs),
        f"{probs}",
    )


def sharey_two_rows_clean():
    """竖排 sharey 组跨 2 行：y 边差=行距是物理错位而非缺陷——成员按
    y 中心聚成两个单成员行带，无带内比较对象，不报（layout-facet 实锤
    的假阳性）。"""
    fig, axs = plt.subplots(2, 1, figsize=(5, 4), sharey=True)
    for ax in axs:
        ax.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s")
    probs, rules = audit_rules(fig, rules={"shared-axis-misaligned"})
    check("sharey-rows", "shared-axis-misaligned" not in rules, f"{probs}")


def sharex_col_inset_flagged():
    """3 行 1 列 sharex：中间成员 aspect:'equal' 横向内缩——x 中心仍在
    同列带内、x 边与上下兄弟错位，仍报。"""
    fig, axs = plt.subplots(3, 1, figsize=(5, 7), sharex=True)
    axs[0].plot([0, 10], [0, 2], color=fv.HUES["vteal"], label="s")
    axs[1].plot([0, 1], [0, 5], color=fv.HUES["vteal"], label="s")
    axs[1].set_aspect("equal")
    axs[2].plot([0, 10], [0, 2], color=fv.HUES["vteal"], label="s")
    probs, rules = audit_rules(fig, rules={"shared-axis-misaligned"})
    check("sharex-col-inset", "shared-axis-misaligned" in rules, f"{probs}")


def sharex_all_grid_clean():
    """sharex='all' + sharey='all' 的 2x2 网格：共享组跨 2 列/2 行——
    聚成 2 列带与 2 行带，各带内成员对齐，不报。"""
    fig, axs = plt.subplots(2, 2, figsize=(6, 5), sharex=True, sharey=True)
    for ax in axs.flat:
        ax.plot([0, 5], [0, 1], color=fv.HUES["vteal"], label="s")
    probs, rules = audit_rules(fig, rules={"shared-axis-misaligned"})
    check("sharex-all-grid", "shared-axis-misaligned" not in rules, f"{probs}")


# --- text-spills-axes ----------------------------------------------------------


def text_spills_right():
    """note 锚点在轴内、字盒越右 spine——diag-paired 实锤（表头越 26px）。"""
    fig, ax = base()
    ax.text(0.97, 0.5, "header cell spilling", transform=ax.transAxes, ha="left")
    probs, rules = audit_rules(fig)
    check("text-spills-right", "text-spills-axes" in rules, f"{probs}")


def text_spills_annotate():
    """annotate 的 xytext 锚点在轴内、墨迹越界——同规则抓。
    xy 须在数据限内：annotation_clip 默认把 xy 出界的注解整体吃掉不画。"""
    fig, ax = base()
    ax.annotate(
        "annotation header",
        xy=(3, YS[3]),
        xytext=(0.99, 0.9),
        textcoords="axes fraction",
        ha="left",
        arrowprops=dict(arrowstyle="->", color=fv.NEUTRALS["vink"]),
    )
    probs, rules = audit_rules(fig)
    check("text-spills-ann", "text-spills-axes" in rules, f"{probs}")


def text_inside_clean():
    """锚点与字盒都在轴内——不报。"""
    fig, ax = base()
    ax.text(0.5, 0.5, "inside", transform=ax.transAxes, ha="center", va="center")
    probs = fv.audit(fig, rules={"text-spills-axes"})
    plt.close(fig)
    check(
        "text-spills-clean",
        not any(p.startswith("text-spills-axes") for p in probs),
        f"{probs}",
    )


def text_anchor_outside():
    """锚点本就在轴外的文本不归本规则（note-outside-axes/clip 语义管）。"""
    fig, ax = base()
    ax.text(1.15, 0.5, "outside anchor", transform=ax.transAxes, ha="left")
    probs = fv.audit(fig, rules={"text-spills-axes"})
    plt.close(fig)
    check(
        "text-spills-anchor-out",
        not any(p.startswith("text-spills-axes") for p in probs),
        f"{probs}",
    )


def text_spills_scoped():
    """scoped_ignore 生效。"""
    fig, ax = base()
    ax.text(0.97, 0.5, "header cell spilling", transform=ax.transAxes, ha="left")
    probs = fv.audit(fig, scoped_ignore={("text-spills-axes", 0)})
    plt.close(fig)
    check(
        "text-spills-scoped",
        not any(p.startswith("text-spills-axes") for p in probs),
        f"{probs}",
    )


def main():
    rotated_ticks()
    rotated_real_collide()
    unrotated_collide()
    text_quad_shape()
    note_on_vertex()
    note_mid_segment()
    note_on_marker()
    annotate_on_line()
    note_in_bar()
    note_quiet()
    bar_label_above()
    heat_annotate()
    legend_text_not_text_rule()
    text_ink_scoped_ignore()
    text_ink_is_warn()
    streamplot_cmap_exempt()
    rogue_in_cmap_axes()
    rogue_plain_axes()
    mark_neutral_works()
    ramp_cmap_works()
    sharey_sibling_label()
    ob_collide()
    ob_overlaps_data()
    ob_offpalette_glyph()
    ob_invisible_skipped()
    ob_clean()
    ob_double_registered()
    sharex_aspect_misaligned()
    sharey_aspect_misaligned()
    sharex_aligned_clean()
    sharex_scoped_exempt()
    sharey_two_rows_clean()
    sharex_col_inset_flagged()
    sharex_all_grid_clean()
    text_spills_right()
    text_spills_annotate()
    text_inside_clean()
    text_anchor_outside()
    text_spills_scoped()
    print(f"--- done, {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
