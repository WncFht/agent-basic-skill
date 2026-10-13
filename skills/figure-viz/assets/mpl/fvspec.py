"""fvspec.py — 声明式图 spec（可 JSON 化 dict）-> matplotlib Figure。

``render(spec)`` 是 spec dict 与其引用 CSV 的纯函数：所有数值计算都
在上游（实验脚本 / 聚合辅助）；spec 只消费已聚合的行。校验要响亮
——未知键、缺必填字段、解析不出的颜色与歧义位置一律抛
:class:`SpecError`，绝不静默错画。

骨架（version 1）::

    {
      "version": 1,
      "theme": "paper",                  # paper|accent|mono
      "rc":    {"font": "serif", "base": 7.6},
      "size":  {"slot": "full", "height": 1.9},   # or "half" | [w, h]
      "colors": {"registries": {"arm": {"frozen": "vblue"}},
                 "ramps": {"top1": {"0.3": "#6BAED6"}},
                 "extend": {"ghost": "#6E7378"}},
      "data":   {"name": rows | {"columns": {...}} | {"csv": "rel/path.csv"}},
      "layout": {"kind": "grid", "shape": [1, 3], "cells": [["a", "b", "c"]],
                 "sharex": "col", "sharey": false, "tags": true},
                 # kind 'matrix': template x rows/cols 展开 + strips；
                 # kind 'spans': map {id: [r0,c0,r1,c1]} + bind 边际轴
                 "rows": {"ylabel": "..."}, "cols": {"xlabel": "..."}},
      "panels": {"a": {...}, ...},       # 省略 -> 面板字段写在顶层
      "legend":  {...},                  # 图级图例方案
      "arrange": {"engine": "tight", "rect": [0, 0.09, 1, 1]},
      "output":  {"path": "fig.png", "formats": ["png", "pdf"], "dpi": 300},
      "meta":    {"ledger": "语义/几何台账", "caption": "标识行",
                  "usermeta": {...}},
      "audit":   {"ignore": ["empty-series"]},
    }

spec lint 警告名（可被 audit.ignore / 面板 audit_ignore 抑制）：``empty-series``, ``empty-legend``, ``hex-literal``,
``pred-indistinct``, ``fill-ignored``, ``scale-ignored``,
``axis-ignored``, ``unknown-ignore``, ``ignore-unscoped``,
``dim-unresolved``, ``dead-cell``, ``missing-rows``,
``unknown-field``, ``where-field-missing``, ``empty-y2``,
``twin-axis-unlabeled``,
``missing-ledger``, ``missing-caption``, ``tight-bbox``,
``meta-key-dropped``, ``meta-key-reserved``, ``dodge-single-group``,
``markers-on-dense-line``, ``tick-density``,
``bar-count``, ``hist-bin-sanity``, ``violin-min-points``,
``kde-min-points``, ``heat-cell-text``, ``note-outside-axes``,
``sig-outside-axes``, ``occluded-by-heat``, ``log-tick-unlabeled``.

``render()`` 退出时恢复 ``plt.rcParams``（主题 rc 在
``plt.rc_context`` 下施加）——调用它不碰全局 matplotlib 状态。
中性 overlay artist（ref/span/note/band/pred、radar 填充、bar 柱顶
标签与 connect 图例幽灵、heat 格值注记、image 角标、contour
'fill+lines' 墨线与 clabel 文本、sig 括号及星号文本、全部 sankey
artist——缎带、节点段、标签与 stage 头、合成图例 handle）都打
``gid='fv-neutral'``，``fvstyle.audit`` 对它们豁免系列计数/覆盖规则。

layout 种类：``'grid'``（cells/shape）、``'matrix'``（``template``
面板按 ``rows`` x ``cols`` facet 值展开，``$row``/``$col`` 替换，
facet 字段注入 ``where``，strip 边距也由同一组值推出）、``'spans'``
（``map`` 给 gridspec 矩形 + ``bind`` 边际轴配对）。
``layout.rows``/``layout.cols`` 对每种 kind 承载边缘默认：
``rows.ylabel`` 落在左缘，``cols.xlabel`` 落在底缘。
"""

from __future__ import annotations

import math
import sys

import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from fvspec_data import _Ctx, _load_datasets, _sort_xy, _vals
from fvspec_kinds import (
    _ROW_FIELD_RE,
    DRAW,
    _angles_for,
    _consumer_cat_map,
    _owner_cat_map,
    _owns_cat_axis,
    _prepare_series,
)
from fvspec_layout import (
    _apply_axis,
    _apply_rc,
    _auto_tag,
    _draw_strips,
    _figsize,
    _figure_legend,
    _layout_cells,
    _lint_note_outside,
    _lint_occluded_by_heat,
    _lint_sig_outside,
    _panel_legend,
    _panels,
    _reserve_label_headroom,
    _resolve_raw,
    _resolve_theme,
    _save,
    _share_anchor,
    _share_key,
    _share_register,
    _tick_density,
)
from fvspec_schema import (
    _BIND_SIDE_IGNORES,
    _FIGURE_RULES,
    _IMG_PANEL_KINDS,
    _SANKEY_PANEL_KINDS,
    ARRANGE_KEYS,
    LINT_NAMES,
    PANEL_KEYS,
    PANEL_KINDS,
    SIZE_SLOTS,
    SPEC_VERSION,
    SpecError,
    _check_keys,
    _hint,
    _is_num,
    _norm_key,
    _obj,
)
from matplotlib.ticker import NullLocator


def render(spec, base_dir=None, *, outdir=None, dpi=None):
    """把 figure spec dict 渲染成 matplotlib Figure。

    ``base_dir`` 解析相对 CSV/输出路径（spec 文件所在目录）。
    ``outdir``/``dpi`` 是 CLI 覆盖项。返回的 Figure 带
    ``fvspec_report`` 属性：{warnings, saved, audit_kwargs, rc}。
    主题/``rc`` 改动在 ``plt.rc_context`` 内执行——退出时恢复全局
    rcParams，即使 spec 抛错也一样。文本尺寸仍在绘制时按环境 rcParams
    解析，因此审计或重画该图应在
    ``plt.rc_context(rc=fig.fvspec_report["rc"])`` 下进行——或直接调
    :func:`audit_fig`。
    """
    with plt.rc_context():
        # raw 钩子与数据集辅助函数从 spec 自身目录 import——渲染期间
        # 把它放上 sys.path
        if base_dir is not None:
            sys.path.insert(0, str(base_dir))
            try:
                return _render(spec, base_dir, outdir=outdir, dpi=dpi)
            finally:
                sys.path.remove(str(base_dir))
        return _render(spec, base_dir, outdir=outdir, dpi=dpi)


def audit_fig(fig, **overrides):
    """在图被渲染时的 rcParams 下跑 ``fv.audit``。

    字体/刻度文本在绘制时才惰性解析；``render`` 恢复 rcParams 后，
    环境上下文里的审计量到的是幻影布局。本助手重进渲染时的 rc
    （存在 ``fvspec_report['rc']``），让文本尺寸规则看到落盘产物的
    真实几何。``**overrides`` 覆盖单个 ``audit_kwargs`` 项。
    """
    rep = getattr(fig, "fvspec_report", {})
    kw = dict(rep.get("audit_kwargs", {}))
    kw.update(overrides)
    rc = rep.get("rc")
    with plt.rc_context(rc=rc):
        return fv.audit(fig, **kw)


def _render(spec, base_dir=None, *, outdir=None, dpi=None):
    if not isinstance(spec, dict):
        raise SpecError("spec must be a dict")
    spec = dict(spec)  # _panels 可能规整扁平式图例
    ver = spec.get("version", SPEC_VERSION)
    if ver != SPEC_VERSION:
        raise SpecError(
            f"spec version {ver!r} unsupported (this renderer speaks "
            f"{SPEC_VERSION}); unknown majors are rejected loudly"
        )
    theme_name = _resolve_theme(spec)
    fv.apply_rc(theme_name)
    _apply_rc(spec)
    ctx = _Ctx(spec, theme_name, base_dir)
    panels = _panels(spec)
    plan = _layout_cells(spec, panels, ctx)
    layout = plan.layout
    panels = plan.panels
    nrows = plan.nrows

    kinds = {}
    for pid, p in panels.items():
        if not isinstance(p, dict):
            raise SpecError(f"panel {pid}: must be an object")
        _check_keys(p, PANEL_KEYS, f"panel {pid}")
        kinds[pid] = p.get("kind", "xy")
        if kinds[pid] not in PANEL_KINDS:
            raise SpecError(
                f"panel {pid}: unknown kind {kinds[pid]!r} "
                f"(valid: {sorted(PANEL_KINDS)})"
            )
        ctx.polar[pid] = kinds[pid] == "radar"
        if kinds[pid] != "xy" and p.get("y2") is not None:
            raise SpecError(f"panel {pid}: 'y2' only applies to kind 'xy'")
        if kinds[pid] != "radar" and "dims" in p:
            raise SpecError(f"panel {pid}: 'dims' only applies to kind 'radar'")
        if kinds[pid] != "radar" and "theta" in p:
            raise SpecError(f"panel {pid}: 'theta' only applies to kind 'radar'")
        if "aspect" in p:
            if kinds[pid] != "xy":
                raise SpecError(f"panel {pid}: 'aspect' only applies to kind 'xy'")
            a = p["aspect"]
            if not (a in ("equal", "auto") or _is_num(a)):
                raise SpecError(
                    f"panel {pid}: aspect must be 'equal'|'auto'|a number, got {a!r}"
                )

    arrange = spec.get("arrange") or {}
    _check_keys(arrange, ARRANGE_KEYS, "arrange")
    engine = arrange.get("engine", "tight")
    if engine not in ("tight", "constrained", "none"):
        raise SpecError(f"arrange.engine {engine!r} unknown")

    w, h = _figsize(spec, nrows)
    fig = plt.figure(
        figsize=(w, h),
        layout="constrained" if engine == "constrained" else None,
    )
    gs = fig.add_gridspec(
        plan.gs_rows,
        plan.gs_cols,
        width_ratios=plan.width_ratios(),
        height_ratios=plan.height_ratios(),
    )

    sharex, sharey = plan.sharex, plan.sharey
    anchors_x, anchors_y = {}, {}
    axes, cell_axes = {}, {}
    rects, share_key_x, share_key_y = {}, {}, {}
    top_off = plan.top_off
    for pid, r0, c0, r1, c1 in plan.placements:
        sl = (slice(r0 + top_off, r1 + top_off), slice(c0, c1))
        if pid not in panels:
            ax = fig.add_subplot(gs[sl])
            ax.axis("off")
            # axis('off') 只停绘制——默认 [0,1] 刻度标签仍带真实 bbox，
            # collide/rb 审计会当成幻影文本；NullLocator 清空刻度对象
            ax.xaxis.set_major_locator(NullLocator())
            ax.yaxis.set_major_locator(NullLocator())
            cell_axes[pid] = ax
            continue
        kw = {}
        if ctx.polar[pid]:
            kw["projection"] = "polar"
        elif kinds[pid] == "xy":
            sx = _share_anchor(sharex, anchors_x, r0, c0)
            sy = _share_anchor(sharey, anchors_y, r0, c0)
            if sx is not None:
                kw["sharex"] = sx
            if sy is not None:
                kw["sharey"] = sy
        ax = fig.add_subplot(gs[sl], **kw)
        axes[pid] = ax
        rects[pid] = (r0, c0, r1, c1)
        if kinds[pid] == "xy":
            _share_register(sharex, anchors_x, r0, c0, ax)
            _share_register(sharey, anchors_y, r0, c0, ax)
            if sharex not in (None, False, "none"):
                share_key_x[pid] = _share_key(sharex, r0, c0)
            if sharey not in (None, False, "none"):
                share_key_y[pid] = _share_key(sharey, r0, c0)
    _draw_strips(fig, gs, plan, ctx)
    # bind：边际轴配对（clustermap 侧条/joint 边际）——side 轴并入 main
    # 的共享组（lim 联动），side 的绑定轴刻度标签与轴标签隐藏
    for side, (main, axname) in plan.bind.items():
        sax = axes[side]
        getattr(sax, f"share{axname}")(axes[main])
        cfg = panels[side].get("xaxis" if axname == "x" else "yaxis") or {}
        if cfg.get("label"):
            ctx.lint(
                "axis-ignored",
                f"panel {side}: {axname}axis.label is hidden by "
                f"layout.bind (bound to {main!r})",
            )
        if axname == "x":
            sax.tick_params(axis="x", labelbottom=False)
            sax.xaxis.label.set_visible(False)
        else:
            sax.tick_params(axis="y", labelleft=False)
            sax.yaxis.label.set_visible(False)

    panels_meta = []
    auto_idx = 0
    for pid, ax in axes.items():
        pspec = panels[pid]
        ai = pspec.get("audit_ignore") or []
        if not isinstance(ai, list):
            raise SpecError(f"panel {pid}: audit_ignore must be a list, got {ai!r}")
        ctx.panel_ignores[pid] = set(ai) | (
            _BIND_SIDE_IGNORES if pid in plan.bind else set()
        )
        kind = kinds[pid]
        # y2 按「声明存在」建 twin：{} 也算声明（此前被 falsy 静默吞掉）
        y2cfg = pspec.get("y2")
        ax2 = None
        if kind == "xy" and y2cfg is not None and y2cfg is not False:
            if not isinstance(y2cfg, dict):
                raise SpecError(f"panel {pid}: 'y2' must be an object, got {y2cfg!r}")
            if not y2cfg:
                ctx.lint(
                    "empty-y2",
                    f"panel {pid}: 'y2' is an empty config — twin axis "
                    f"created with defaults",
                    pid,
                )
            ax2 = ax.twinx()
            if not y2cfg.get("label"):
                ctx.lint(
                    "twin-axis-unlabeled",
                    f"panel {pid}: twin y axis lacks a 'label' — the "
                    f"second unit is unreadable",
                    pid,
                )
        ser = pspec.get("series") or []
        if not isinstance(ser, list):
            raise SpecError(f"panel {pid}: 'series' must be a list, got {ser!r}")
        for s in ser:
            if not isinstance(s, dict):
                raise SpecError(
                    f"panel {pid}: series entries must be objects, got {s!r}"
                )
        recs = [
            _prepare_series(s, pspec, pid, ctx, auto_idx + i) for i, s in enumerate(ser)
        ]
        auto_idx += len(recs)
        if kind == "xy" and any(r.kind == "sankey" for r in recs):
            # sankey 面板：坐标系是流量单位不是数据轴——一张 sankey 独占
            # panel，只允许中性 overlay，双轴无意义
            bad = sorted({r.kind for r in recs} - _SANKEY_PANEL_KINDS)
            if bad:
                raise SpecError(
                    f"panel {pid}: sankey cannot share a panel with "
                    f"{bad} — only neutral overlays (ref/span/note) allowed"
                )
            if sum(r.kind == "sankey" for r in recs) > 1:
                raise SpecError(
                    f"panel {pid}: multiple sankey series in one panel — "
                    f"one sankey draws the whole figure; split into panels"
                )
            if ax2 is not None:
                raise SpecError(
                    f"panel {pid}: 'y2' with sankey is meaningless — "
                    f"sankey axes carry flow units, not data"
                )
        if kind == "radar":
            # theta 一等字段：首维方位（offset，度数）与旋向（direction）
            # ——「12 点起 + 顺时针」这类最常见雷达版式不再走 raw helper；
            # rlabel 与 dim 角坐标是数据角，offset/direction 翻转后语义
            # 保持一致
            th = pspec.get("theta")
            if th is not None:
                th = _obj(th, f"panel {pid} theta")
                _check_keys(th, {"offset", "direction"}, f"panel {pid} theta")
                off = th.get("offset")
                if off is not None:
                    if not _is_num(off):
                        raise SpecError(
                            f"panel {pid} theta: 'offset' must be a degrees "
                            f"number, got {off!r}"
                        )
                    ax.set_theta_offset(np.deg2rad(float(off)))
                d = th.get("direction")
                if d is not None:
                    if d not in ("cw", "ccw"):
                        raise SpecError(
                            f"panel {pid} theta: 'direction' must be "
                            f"'cw'|'ccw', got {d!r}"
                        )
                    ax.set_theta_direction(-1 if d == "cw" else 1)
            amap = _angles_for(pspec, recs, ctx, pid)
            ax.set_xticks(list(amap.values()), [str(d) for d in amap])
            rl = pspec.get("rlabel")
            if rl is None and len(amap) > 1:
                # mpl 的 -22.5° 默认在很多维度数下正压辐条；
                # 改为把径向标签停进最大角隙
                degs = sorted(math.degrees(a) % 360 for a in amap.values())
                n = len(degs)
                gaps = [(degs[(i + 1) % n] - degs[i]) % 360 for i in range(n)]
                i = n - 1 - gaps[::-1].index(max(gaps))
                rl = (degs[i] + gaps[i] / 2) % 360
            if rl is not None:
                ax.set_rlabel_position(rl)
        ctx.panel_recs[pid] = recs  # sig 的类别挂点表要查同面板兄弟系列
        for rec in recs:
            target = ax2 if (rec.merged.get("axis") == "y2" and ax2) else ax
            DRAW[rec.kind](target, rec, ctx, pid)
            if rec.kind in ("line", "pred"):
                for g in rec.groups:
                    xs = _vals(g.rows, rec.merged.get("x"), "x", rec.id)
                    ys = _vals(g.rows, rec.merged.get("y"), "y", rec.id)
                    g.xs, _ = _sort_xy(g, xs, ys, rec.merged.get("sort_x", True))
        lint = ctx.lint_proxy(pid)
        img_panel = False
        has_sankey = False
        if kind == "xy":
            # 类别轴建立者按轴向分流：dir:'h' 的 bar/box/violin 类别落
            # y 轴（与 _owner_cat_map 的 on_axis 同口径）——原先一律喂
            # cat_x，横置面板错标 x 为类别轴、漏标 y
            cat_own_x = any(_owns_cat_axis(r, "x") for r in recs)
            cat_own_y = any(_owns_cat_axis(r, "y") for r in recs)
            # heat 面板双轴都是类别轴（刻度归 _draw_heat 所有），且默认不
            # 需要网格线——网格会跟 cell 白边视觉打架；场族（contour 全域、
            # quiver 的 stream 网格）同理默认关网格，但坐标轴仍是数值轴
            has_heat = any(r.kind == "heat" for r in recs)
            has_field = any(
                r.kind == "contour"
                or (r.kind == "quiver" and r.merged.get("mode") == "stream")
                for r in recs
            )
            # 图版 cell（image + 只许中性 overlay）：像素图没有可读轴——
            # 刻度默认收掉、网格默认关、框默认闭合（spine 当 cell 边线用）
            img_panel = (
                bool(recs)
                and any(r.kind == "image" for r in recs)
                and all(r.kind in _IMG_PANEL_KINDS for r in recs)
            )
            # sankey 面板双轴都归 kind 层（流量单位，无数据刻度语义）——
            # 与 heat 同口径走 categorical 通道：scale/ticks lint 忽略、
            # lim/label 照用
            has_sankey = any(r.kind == "sankey" for r in recs)
            # 无结构所有者时消费型 kind（scatter/line）按数据首见序自建
            # 槽位——同样是类别轴：计入 cat_x/cat_y、刻度由面板层补画
            con = {}
            if not has_sankey:
                for a in ("x", "y"):
                    if _owner_cat_map(recs, a)[0]:
                        continue
                    cm, cd = _consumer_cat_map(recs, a)
                    if cm:
                        con[a] = (cm, cd)
            # contour matrix 的类别 xlabels 同理——刻度归 kind 层
            cat_x = (
                cat_own_x
                or has_heat
                or has_sankey
                or any(r.cat_x for r in recs)
                or "x" in con
            )
            cat_y = (
                cat_own_y
                or has_heat
                or has_sankey
                or any(r.cat_y for r in recs)
                or "y" in con
            )
            _apply_axis(
                ax,
                "x",
                pspec.get("xaxis"),
                f"panel {pid} xaxis",
                cat_x,
                lint,
                ctx=ctx,
                recs=recs,
            )
            _apply_axis(
                ax,
                "y",
                pspec.get("yaxis"),
                f"panel {pid} yaxis",
                cat_y,
                lint,
                ctx=ctx,
                recs=recs,
            )
            if ax2 is not None:
                _apply_axis(
                    ax2,
                    "y",
                    pspec.get("y2"),
                    f"panel {pid} y2",
                    lint=lint,
                    ctx=ctx,
                )
            if img_panel:
                # 显式 xaxis/yaxis.ticks 仍可钉回——默认只是「收掉」
                if not (pspec.get("xaxis") or {}).get("ticks"):
                    ax.set_xticks([])
                if not (pspec.get("yaxis") or {}).get("ticks"):
                    ax.set_yticks([])
            # 消费型自建槽位的类别刻度归面板层（所有者轴的刻度 kind
            # 层在 draw 时已写好）
            if "x" in con:
                cm, cd = con["x"]
                ax.set_xticks([cm[_norm_key(c)] for c in cd], [str(c) for c in cd])
            if "y" in con:
                cm, cd = con["y"]
                ax.set_yticks([cm[_norm_key(c)] for c in cd], [str(c) for c in cd])
            _tick_density(ax, pspec, pid, cat_x, lint, cat_y=cat_y)
            if "aspect" in pspec:
                ax.set_aspect(pspec["aspect"])
            _lint_occluded_by_heat(recs, lint)
            _lint_note_outside(ax, ax2, recs, lint)
            _lint_sig_outside(ax, ax2, recs, lint)
        elif kind == "radar":
            _apply_axis(
                ax,
                "y",
                pspec.get("yaxis"),
                f"panel {pid} yaxis",
                lint=lint,
                ctx=ctx,
            )
        fv.apply_frame(
            ax,
            pspec.get(
                "frame",
                (
                    "minimal"
                    if has_sankey
                    else "closed"
                    if img_panel
                    else ctx.theme.frame
                ),
            ),
        )
        if kind != "donut":
            fv.apply_grid(
                ax,
                pspec.get(
                    "grid",
                    (
                        "none"
                        if (
                            kind == "xy"
                            and (has_heat or has_field or img_panel or has_sankey)
                        )
                        else ctx.theme.grid
                    ),
                ),
                pspec.get("grid_axis", "y"),
            )
        tag = pspec.get("tag", ...)
        if tag is ...:
            # 单面板图惯例不打 tag
            tag = (
                _auto_tag(pid, plan.order)
                if layout.get("tags", True) and len(panels) > 1
                else None
            )
        title = pspec.get("title")
        if title:
            ax.set_title(f"({tag}) {title}" if tag else title)
        elif tag:
            ax.set_title(f"({tag})")
        own_legend = (
            isinstance(pspec.get("legend"), dict) or pspec.get("legend") is True
        )
        donut_handles = None
        if kind == "donut" and recs:
            donut_handles = [h for r in recs for h in (r.handles or [])]
            want_leg = any(r.merged.get("labels") == "legend" for r in recs)
            # 切片 handle 改由图级图例收——此时自动开面板图例
            # 会让 own_legend 跳过它
            fig_leg = spec.get("legend")
            has_fig_leg = fig_leg is not None and fig_leg is not False
            if want_leg and pspec.get("legend") is None and not has_fig_leg:
                pspec = dict(pspec)
                pspec["legend"] = True
                own_legend = True
            elif want_leg and pspec.get("legend") is False and not has_fig_leg:
                lint(
                    "empty-legend",
                    "donut labels='legend' but no legend is shown; "
                    "slice labels are dropped",
                )
        panels_meta.append(
            {
                "id": pid,
                "ax": ax,
                "ax2": ax2,
                "spec": pspec,
                "recs": recs,
                "own_legend": own_legend,
                "handles": donut_handles,
            }
        )
        _panel_legend(
            ax,
            recs,
            pspec.get("legend"),
            ctx,
            pid,
            donut_handles=donut_handles,
            ax2=ax2,
        )
        # connect.label 的幽灵句柄只在有图例收它时可见——面板与图级图例
        # 都没有时响亮提示（否则 label 静默蒸发）
        fig_leg = spec.get("legend")
        if fig_leg is None or fig_leg is False:
            for rec in recs:
                if rec.conn_label is not None and not own_legend:
                    ctx.lint(
                        "empty-legend",
                        f"series {rec.id}: connect.label {rec.conn_label!r} "
                        f"is declared but no legend collects it — enable a "
                        f"panel or figure legend",
                        pid,
                    )
        # raw 逃生舱压轴：spec 化的 axis/frame/grid/title/panel-legend 全部
        # 落位之后才调——raw 对该面板 axes 有最终发言权（隐藏 spine、改刻度
        # 等不会被后续 apply_* 覆盖）。跨面板收口（共享轴 label_outer、
        # figure legend、layout）仍在其后，属图级职责。
        if pspec.get("raw"):
            _resolve_raw(pspec["raw"])(
                ax,
                {
                    "spec": spec,
                    "panel": pspec,
                    "data": ctx.data,
                    "theme": ctx.theme,
                    "fv": fv,
                    "ax": ax,
                    "ax2": ax2,
                    "fig": fig,
                    "colors": ctx.colors,
                    # 面板 id -> Axes 稳定映射（快照，axes 已全建好）——
                    # 跨面板辅助不必再按 position.x0 猜 fig.get_axes() 顺序
                    "panel_axes": dict(axes),
                },
            )

    # 共享轴：刻度标签与轴标签只挂外缘
    # (mpl label_outer semantics, driven by our share groups; spans 面板按
    # rect 的底/左缘参与比较)
    gx, gy = {}, {}
    for pid in axes:
        if pid in share_key_x:
            gx.setdefault(share_key_x[pid], []).append(pid)
        if pid in share_key_y:
            gy.setdefault(share_key_y[pid], []).append(pid)
    for members in gx.values():
        bmax = max(rects[p][2] - 1 for p in members)
        for p in members:
            if rects[p][2] - 1 < bmax:
                axes[p].tick_params(axis="x", labelbottom=False)
                axes[p].xaxis.label.set_visible(False)
    for members in gy.values():
        lmin = min(rects[p][1] for p in members)
        for p in members:
            if rects[p][1] > lmin:
                axes[p].tick_params(axis="y", labelleft=False)
                axes[p].yaxis.label.set_visible(False)

    # meta.caption：画布内底部居中一行中性灰标识（放在画布外会触发
    # text-outside-figure；在下沿留白内落位，below-图例与 tight rect
    # 经 cap_frac 让位）
    caption = ctx.meta.get("caption")
    caption = caption.strip() if isinstance(caption, str) else None
    cap_frac = 0.0
    if caption:
        base = (spec.get("rc") or {}).get("base", 7.6)
        # ~scriptsize 但始终高于 audit 的 text-too-small 下限
        # （floor = min(6pt, 0.7*base)，两项分别覆盖 base≷8.6 两支）
        fs = max(base - 2.2, 0.72 * base)
        cap_frac = 0.004 + (fs * 1.4) / (h * 72.0) + 0.006
        fig.text(
            0.5,
            0.004,
            caption,
            ha="center",
            va="bottom",
            fontsize=fs,
            color=fv.HUES["vgray"],
        )

    _figure_legend(fig, cell_axes, ctx, panels_meta, cap_frac)
    leg = ctx.spec.get("legend")
    legcell = (
        leg.get("cell")
        if isinstance(leg, dict) and leg.get("where") == "cell"
        else None
    )
    cell_src = {
        "grid": "layout.cells",
        "matrix": "layout.overrides",
        "spans": "layout.map",
    }.get(layout.get("kind", "grid"), "layout.cells")
    for cid in cell_axes:
        if cid != legcell:
            ctx.lint(
                "dead-cell",
                f"{cell_src}: {cid!r} is neither a panel nor the "
                f"legend cell{_hint(cid, panels)}",
            )
    if engine == "tight":
        rect = arrange.get("rect")
        fig_leg = spec.get("legend")
        if (
            rect is None
            and isinstance(fig_leg, dict)
            and fig_leg.get("where") == "below"
        ):
            n = len(fig_leg.get("entries") or [1])
            ncol = fig_leg.get("ncol") or min(n, 4)
            rows_needed = max(1, math.ceil(n / ncol))
            rect = [
                0,
                min(0.4, cap_frac + 0.05 + 0.05 * rows_needed),
                1,
                1,
            ]
        elif rect is None and cap_frac:
            rect = [0, cap_frac, 1, 1]
        fig.tight_layout(
            rect=rect,
            w_pad=arrange.get("w_pad"),
            h_pad=arrange.get("h_pad"),
        )

    _reserve_label_headroom(fig)
    saved = _save(fig, spec, ctx, base_dir, outdir, dpi)

    # audit 接线：图级 ignore 喂 audit(ignore=...)；面板的
    # audit_ignore 映射成 scoped_ignore 的 (rule, axes-index) 对，
    # 只对轴域级规则生效——text/color 规则是图全局的，改发 lint 提示。
    render_rules = set(getattr(fv, "RENDER_RULES", {}))
    axes_scoped = render_rules - _FIGURE_RULES
    for n in sorted(ctx.fig_ignores - render_rules - LINT_NAMES):
        ctx.lint("unknown-ignore", f"audit.ignore: unknown check {n!r}")
    scoped = []
    seen_scoped = set()
    for m in panels_meta:
        # inset/secondary 等 child_axes 不进 fig.get_axes()，只能以 axes
        # 对象身份传给 fv.audit —— 面板轴 + twin + 全部后代轴（BFS：
        # inset 上再 twinx 的孙轴也在豁免半径内，与 fvstyle 同口径）
        m_axes = [m["ax"]]
        if m.get("ax2") is not None:
            m_axes.append(m["ax2"])
        i = 0
        while i < len(m_axes):
            for ch in getattr(m_axes[i], "child_axes", ()):
                if ch not in m_axes:
                    m_axes.append(ch)
            i += 1
        for n in sorted(ctx.panel_ignores.get(m["id"], ())):
            if n in axes_scoped:
                for a in m_axes:
                    if (n, id(a)) not in seen_scoped:
                        seen_scoped.add((n, id(a)))
                        scoped.append((n, a))
            elif n in render_rules:
                ctx.lint(
                    "ignore-unscoped",
                    f"panel {m['id']}: {n!r} is figure-level; "
                    f"use audit.ignore to suppress",
                )
            elif n not in LINT_NAMES:
                ctx.lint(
                    "unknown-ignore",
                    f"panel {m['id']}: unknown check {n!r}",
                )
    fig.fvspec_report = {
        "warnings": ctx.warnings,
        "saved": saved,
        "audit_kwargs": {
            "ignore": {n for n in ctx.fig_ignores if n in render_rules},
            "scoped_ignore": scoped,
            "extra_palette": sorted(ctx.colors.palette_ext),
        },
        # 渲染时 rcParams 快照（剔 backend 键）：审计或重画在
        # plt.rc_context(rc=...) 下进行——见 audit_fig
        "rc": {k: v for k, v in plt.rcParams.items() if not k.startswith("backend")},
    }
    return fig


# ---------------------------------------------------------------- 回读
# spec 侧声明的标识文本集（rb-label-diff 的 declared 输入）。系列 label
# 模板（"{v}"/"{n}"/"{field}"）这里不展开——渲染出的 artist label 已经是
# 展开结果，由 fv.audit 自己并入；declared_texts 只补 spec 里声明了、但
# 不会落在 artist label 上的那些：title/axis label/legend title/entry
# label/meta.caption/note.text，以及经 legend 条目渲染的数据身份
# （donut 切片名、{group} 条目的 by 组键、{series} 条目兜底显示的系列
# id）。数据集与面板归一化直接复用 _load_datasets/_panels——declared
# 口径必须和渲染器看到的是同一份行（CSV 强制转型一致性靠这个保证）；两
# 者是校验式实现、坏 spec 会抛 SpecError，advisory 侧捕获后按空集继续，
# 不阻断审计。


def declared_texts(spec, base_dir=None) -> set:
    """spec 声明的标识文本集合（见上注释）；fv.audit(declared=...) 的输入。"""
    out = set()
    try:
        datasets = _load_datasets(spec, base_dir)
    except SpecError:
        datasets = {}

    def rows_of(name):
        if name is None:
            if len(datasets) != 1:
                return []
            name = next(iter(datasets))
        return datasets.get(name) or []

    def add(v):
        # 字面字段：title/axis label/note/caption 等原样渲染——mathtext
        # 里的 '{…}'（如 $N=10^{3}$）是字面文本，不能当模板跳过
        if isinstance(v, str) and v.strip():
            out.add(v.strip())

    def add_tpl(v, ph=("{v}", "{n}")):
        # 经 _fmt_label/行字段模板展开的字段（series.label、扇出
        # note.text）：只含真实占位符（series label 的 {v}/{n}/{by_field}、
        # note text 的 {field}/{field:fmt}）的才是未展开模板——展开结果
        # 由 artist label 侧覆盖，跳过声明；其余花括号（mathtext 的
        # $x_{i}$、{_fmt_label 不展开的占位）原样上纸，照常声明
        if isinstance(v, str) and v.strip():
            s = v.strip()
            if not any(p in s for p in ph):
                out.add(s)

    try:
        panels = _panels(dict(spec))
    except SpecError:
        panels = {"a": spec}
    # 系列 id 与渲染同口径：显式 id 或 f"{pid}s{全局序号}"
    # （JSON dict 保序，与渲染时的面板/系列遍历顺序一致）
    series_by_id = {}
    auto = 0
    for pid, p in panels.items():
        if not isinstance(p, dict):
            continue
        for s in p.get("series") or []:
            if isinstance(s, dict):
                series_by_id[s.get("id") or f"{pid}s{auto}"] = (pid, s)
                auto += 1

    def legend_block(leg):
        if not isinstance(leg, dict):
            return
        add(leg.get("title"))
        entries = leg.get("entries")
        if not isinstance(entries, list):
            return
        for e in entries:
            if not isinstance(e, dict):
                continue
            h = e.get("handle")
            if isinstance(h, dict):
                # 幽灵句柄条目：_entry_handle 里 handle 分支先返回，渲染
                # 文字就是 handle.label，series/group 键被忽略
                add(h.get("label"))
                continue
            if e.get("label"):
                # {series}/handle 条目经 _entry_handle 原样渲染——字面字段。
                # {group} 条目的 label 走 _fmt_label：只展开 {v}/{n}/
                # {by_field}，其余花括号（mathtext、未知占位）原样上纸——
                # 不含真占位符的字面 label 照样声明
                lab = e["label"]
                if isinstance(lab, str) and "group" in e and "series" not in e:
                    hit = series_by_id.get(e["group"])
                    bf = None
                    if hit is not None:
                        by = hit[1].get("by")
                        bf = by.get("field") if isinstance(by, dict) else by
                    ph = ["{v}", "{n}"]
                    if isinstance(bf, str):
                        ph.append("{" + bf + "}")
                    if not any(p in lab for p in ph):
                        add(lab)
                else:
                    add(lab)
                continue
            # 无显式 label 的条目渲染 g.label（artist 侧已覆盖）或兜底值：
            # {series} 落 sid、{group} 落 by 组键——仅当系列自己没给 label
            sid = e.get("series") or e.get("group")
            hit = series_by_id.get(sid)
            if hit is None:
                continue
            pid, s = hit
            if s.get("label") is not None:
                continue
            if "series" in e:
                add(sid)
            else:
                by = s.get("by")
                bfield = by.get("field") if isinstance(by, dict) else by
                if not isinstance(bfield, str):
                    continue
                panel = panels.get(pid) or {}
                rows = rows_of(s.get("from") or panel.get("from"))
                for r in rows:
                    add(str(r.get(bfield, "")))

    for pid, p in panels.items():
        if not isinstance(p, dict):
            continue
        add(p.get("title"))
        for ak in ("xaxis", "yaxis", "y2"):
            cfg = p.get(ak)
            if isinstance(cfg, dict):
                add(cfg.get("label"))
        legend_block(p.get("legend"))
        for s in p.get("series") or []:
            if not isinstance(s, dict):
                continue
            lab = s.get("label")
            if isinstance(lab, (str, dict)):
                by = s.get("by")
                bf = by.get("field") if isinstance(by, dict) else by
                ph = ["{v}", "{n}"]
                if isinstance(bf, str):
                    ph.append("{" + bf + "}")
                if isinstance(lab, str):
                    add_tpl(lab, ph)
                else:
                    for v in lab.values():
                        add_tpl(str(v), ph)
            if s.get("kind") == "note":
                t = s.get("text")
                if isinstance(s.get("at"), dict):
                    # at:{x,y} 逐行扇出：text 是 {field}/{field:fmt} 行模
                    # 板，只有命中行字段的占位才展开（_row_text 对非字段占
                    # 位原样保留）——无真占位的字面串照常声明；空数据沿用
                    # 「含 { 就跳过」的保守口径（无行即无渲染，声明反成
                    # missing 误报）
                    if isinstance(t, str) and t.strip():
                        rows = rows_of(s.get("from") or p.get("from"))
                        fields = {k for r in rows for k in r}
                        live = any(
                            m.group(1) in fields for m in _ROW_FIELD_RE.finditer(t)
                        )
                        if not live and (rows or "{" not in t):
                            out.add(t.strip())
                else:
                    add(t)
            if s.get("kind") == "donut" and s.get("labels", True) is not False:
                # 切片名来自数据 x 列，渲染成饼内文字或图例条目
                rows = rows_of(s.get("from") or p.get("from"))
                xcol = s.get("x")
                if isinstance(xcol, str):
                    for r in rows:
                        add(str(r.get(xcol, "")))

    legend_block(spec.get("legend"))
    meta = spec.get("meta")
    if isinstance(meta, dict):
        add(meta.get("caption"))
    return out


__all__ = [
    "SIZE_SLOTS",
    "SPEC_VERSION",
    "SpecError",
    "audit_fig",
    "declared_texts",
    "render",
]
