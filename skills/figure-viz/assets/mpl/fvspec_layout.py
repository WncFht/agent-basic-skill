"""fvspec_layout.py — 轴/图例应用、布局引擎（grid/matrix/spans）与保存。"""

from __future__ import annotations

import importlib
import math
import re
from pathlib import Path

import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from fvspec_data import _Group, _legend_label, _resolve_props
from fvspec_kinds import _cat_lookup, _cat_map, _fmt_label
from fvspec_schema import (
    _IMG_PANEL_KINDS,
    _KIND_ZORDER,
    _LEGEND_WHERE,
    _META_KEYS_PDF,
    _META_KEYS_SVG,
    _NEUTRAL_GID,
    _NEUTRAL_KINDS,
    AXIS_KEYS,
    LAYOUT_KEYS,
    LEGEND_KEYS,
    MAX_GRID_CELLS,
    MAX_GRID_DIM,
    MAX_MATRIX_CELLS,
    MAX_MATRIX_DIM,
    MAX_PLATE_CELLS,
    MAX_PLATE_DIM,
    MAX_SPANS_DIM,
    OUTPUT_KEYS,
    PANEL_KEYS,
    RC_KEYS,
    ROW_HEIGHT,
    SIZE_SLOTS,
    TOP_KEYS,
    SpecError,
    _check_keys,
    _hint,
    _is_num,
    _mark,
    _norm_key,
    _obj,
)
from matplotlib.collections import PathCollection
from matplotlib.container import BarContainer
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, NullLocator

# -------------------------------------------------------------------- 轴


def _apply_axis(
    ax, axis_name, cfg, where, categorical=False, lint=None, ctx=None, recs=None
):
    """categorical = 该轴刻度由 kind 层所有（bar/box/violin 的 x、heat 的
    双轴）：scale/ticks/tick_labels 一律 lint 忽略，lim/label/minor 照用。"""
    if cfg is None:
        return
    cfg = _obj(cfg, where)
    _check_keys(cfg, AXIS_KEYS, where)
    axis = ax.xaxis if axis_name == "x" else ax.yaxis
    props = _resolve_props(cfg.get("props"), ctx, lint)
    cat = categorical
    scale = cfg.get("scale")
    if scale:
        if cat:
            if lint:
                lint(
                    "scale-ignored",
                    f"{where}: scale {scale!r} on categorical {axis_name}",
                )
        elif scale == "symlog":
            getattr(ax, f"set_{axis_name}scale")(
                "symlog", linthresh=props.get("linthresh", 1)
            )
        else:
            getattr(ax, f"set_{axis_name}scale")(scale)
    # lim 对类别轴也生效：类别轴按序号定限，可裁掉尾部类别；lim 元素收
    # 类别名——经同面板 _cat_map 落槽位（数值直过，未知名/非类别轴响亮
    # 报错——原先透给 mpl 崩 TypeError）
    lim = cfg.get("lim")
    if lim is not None:
        vals = (
            lim.values()
            if isinstance(lim, dict)
            else lim
            if isinstance(lim, (list, tuple))
            else ()
        )
        if (
            ctx is not None
            and recs is not None
            and any(isinstance(v, str) for v in vals)
        ):
            cm, cd = _cat_map(recs, axis_name)

            def _limval(v):
                return _cat_lookup(v, cm, cd, axis_name, where, "lim")

            if isinstance(lim, dict):
                lim = {k: _limval(v) for k, v in lim.items()}
            else:
                lim = [_limval(v) for v in lim]
        if isinstance(lim, dict):
            if axis_name == "x":
                ax.set_xlim(**{k: lim[k] for k in ("left", "right") if k in lim})
            else:
                ax.set_ylim(**{k: lim[k] for k in ("bottom", "top") if k in lim})
        else:
            getattr(ax, f"set_{axis_name}lim")(lim)
        # 显式定限的边记为 pinned——_reserve_label_headroom 只补未钉侧
        # 的 headroom（单侧 lim 如 {bottom:0} 照样会关 autoscale，但顶部
        # 余量仍该由渲染器补）
        pinned = getattr(ax, "_fv_lim_pinned", None)
        if pinned is None:
            pinned = {"x": set(), "y": set()}
            ax._fv_lim_pinned = pinned
        sides = ("left", "right") if axis_name == "x" else ("bottom", "top")
        if isinstance(lim, dict):
            pinned[axis_name] |= set(lim) & set(sides)
        else:
            pinned[axis_name] |= set(sides)
    ticks = cfg.get("ticks")
    tl = cfg.get("tick_labels")
    if cat and (ticks is not None or tl):
        # kind 层已用类别名写了刻度标签——在这里改会错位，告警不静默
        if lint:
            lint(
                "axis-ignored",
                f"{where}: ticks/tick_labels on categorical {axis_name} "
                f"are owned by the series layer — ignored",
            )
    elif ticks is not None:
        axis.set_ticks(ticks)
        if tl == "ticks":
            axis.set_ticklabels([str(t) for t in ticks])
        elif tl:
            axis.set_ticklabels(tl)
        elif scale == "log" and lint:
            # LogFormatterMathtext(labelOnlyBase) 只给 10 幂写标签——非幂
            # 主刻度画出 tick mark 但标签是空串，图面「有刻度无数字」
            bad = [
                t
                for t in ticks
                if _is_num(t)
                and t > 0
                and abs(math.log10(t) - round(math.log10(t))) > 1e-9
            ]
            if bad:
                lint(
                    "log-tick-unlabeled",
                    f"{where}: log-scale ticks {bad} are not powers of 10 "
                    f"and render without labels — give 'tick_labels' or "
                    f"use powers of 10",
                )
    elif tl and lint:
        # 没有 ticks 锚点，tick_labels 无的放矢——此前被静默吞掉
        lint(
            "axis-ignored",
            f"{where}: tick_labels without ticks is ignored",
        )
    if cfg.get("minor") == "off":
        axis.set_minor_locator(NullLocator())
    if cfg.get("label") is not None:
        axis.set_label_text(cfg["label"])
    stride = cfg.get("tick_stride")
    if stride is not None:
        if not (_is_num(stride) and float(stride).is_integer() and stride >= 1):
            raise SpecError(
                f"{where}: tick_stride must be a positive integer, got {stride!r}"
            )
        stride = int(stride)
        if stride > 1:
            # 包一层 formatter 遮掉非整除位文本——刻度/网格位置保留，
            # 类别轴与数值轴同口径
            inner = axis.get_major_formatter()
            axis.set_major_formatter(
                FuncFormatter(
                    lambda v, p, _f=inner: (
                        _f(v, p) if p is None or p % stride == 0 else ""
                    )
                )
            )
    rot = cfg.get("tick_rotation")
    if rot is not None:
        if not _is_num(rot):
            raise SpecError(
                f"{where}: tick_rotation must be degrees number, got {rot!r}"
            )
        # labelrotation 存进 _major_tick_kw——draw 时重建的刻度同样生效；
        # 已物化的类别刻度再 setp 一遍补 anchor/对齐（mpl 不自动改 ha）
        axis.set_tick_params(which="major", labelrotation=float(rot))
        kw = {"rotation": float(rot), "rotation_mode": "anchor"}
        if axis_name == "x" and rot % 360:
            kw["ha"] = "right"
        plt.setp(axis.get_majorticklabels(), **kw)


def _ticks_in_view(ax, axis_name):
    """可视窗口内的主刻度个数（含 lim 裁剪——裁掉的不算挤）。

    `get_majorticklocs` 读的是已物化的 Tick 对象，render 中若有过早
    canvas draw（如 tight_layout 测量），刻度会固化在旧 lim 下；直接
    调用 locator 按当前 view interval 现算，FixedLocator 同样适用。
    """
    axis = ax.xaxis if axis_name == "x" else ax.yaxis
    lo, hi = sorted(getattr(ax, f"get_{axis_name}lim")())
    tol = (hi - lo) * 1e-6 or 1e-12
    try:
        locs = np.asarray(axis.get_major_locator()(), dtype=float)
    except Exception:
        locs = np.asarray(axis.get_majorticklocs(), dtype=float)
    return int(((locs >= lo - tol) & (locs <= hi + tol)).sum())


def _tick_density(ax, pspec, pid, categorical, lint, cat_y=False):
    """tick-density lint：数值轴自动刻度 >8 / 类别轴 >12 报 warn。

    显式 `ticks` 的数值轴视为用户已自控疏密；类别轴刻度归 kind 层
    所有（bar/box/violin 的 x、heat 的双轴写死位置），靠数据聚合/lim
    裁剪减类别。`cat_y` 覆盖 y 也是类别轴的面板（heat）。
    """
    xcfg = pspec.get("xaxis")
    if categorical:
        n = _ticks_in_view(ax, "x")
        if n > 12:
            lint(
                "tick-density",
                f"panel {pid}: {n} category ticks on x (>12) — labels "
                f"collide; aggregate or filter the data",
            )
    elif not (isinstance(xcfg, dict) and "ticks" in xcfg):
        n = _ticks_in_view(ax, "x")
        if n > 8:
            lint(
                "tick-density",
                f"panel {pid}: {n} x ticks (>8) — thin them via xaxis.ticks",
            )
    ycfg = pspec.get("yaxis")
    if cat_y:
        n = _ticks_in_view(ax, "y")
        if n > 12:
            lint(
                "tick-density",
                f"panel {pid}: {n} category ticks on y (>12) — labels "
                f"collide; aggregate or filter the data",
            )
    elif not (isinstance(ycfg, dict) and "ticks" in ycfg):
        n = _ticks_in_view(ax, "y")
        if n > 8:
            lint(
                "tick-density",
                f"panel {pid}: {n} y ticks (>8) — thin them via yaxis.ticks",
            )


def _lint_occluded_by_heat(recs, lint):
    """occluded-by-heat：pcolormesh/contourf 默认不透明——同面板里 zorder
    追不上它且画在它之前的对象被静默盖死。"""
    for hi, hr in enumerate(recs):
        covering = hr.kind == "heat" or (
            hr.kind == "contour" and hr.merged.get("mode", "fill") != "lines"
        )
        if not covering:
            continue
        hz = hr.merged.get("zorder")
        if hz is None:
            hz = _KIND_ZORDER.get(hr.kind, 1)
        what = "pcolormesh" if hr.kind == "heat" else "contourf"
        for ri, r in enumerate(recs):
            if ri == hi:
                continue
            z = r.merged.get("zorder")
            if z is None:
                z = _KIND_ZORDER.get(r.kind, 1)
            if z < hz or (z == hz and ri < hi):
                # image 垫在覆盖面下：覆盖面半透明时是刻意的 underlay
                # （heat 叠图配方），不透明才真盖死
                cov_alpha = (hr.merged.get("props") or {}).get(
                    "alpha", hr.merged.get("alpha", 1.0)
                )
                if r.kind == "image" and _is_num(cov_alpha) and cov_alpha < 1:
                    continue
                lint(
                    "occluded-by-heat",
                    f"series {r.id} ({r.kind}) at zorder {z} is covered by "
                    f"{hr.kind} {hr.id} (zorder {hz}) — the opaque {what} "
                    f"hides it; reorder the series or raise 'zorder'",
                )


def _lint_note_outside(ax, ax2, recs, lint):
    """note-outside-axes：annotation_clip 默认只 clip 纯 'data' 坐标——
    xy 落出轴窗的注释被静默吞掉（装饰消失的审计盲区）。混合坐标按分量
    判；figure fraction 要等布局定型，不作判定以免误报。"""
    for rec in recs:
        if rec.kind != "note" or not rec.note_annots:
            continue
        target = ax2 if (rec.merged.get("axis") == "y2" and ax2 is not None) else ax
        target.relim()
        target.autoscale_view()
        xlim, ylim = sorted(target.get_xlim()), sorted(target.get_ylim())
        for ann in rec.note_annots:
            clip = ann.get_annotation_clip()
            if clip is False:
                continue
            xc = ann.xycoords
            if clip is None and xc != "data":
                continue  # mpl 默认 clip 只作用纯 'data' xycoords
            pair = xc if isinstance(xc, tuple) else (xc, xc)
            outside = False
            for v, coord, lim in (
                (ann.xy[0], pair[0], xlim),
                (ann.xy[1], pair[1], ylim),
            ):
                if coord == "data":
                    outside = outside or not (lim[0] <= v <= lim[1])
                elif coord == "axes fraction":
                    outside = outside or not (0.0 <= v <= 1.0)
            if outside:
                lint(
                    "note-outside-axes",
                    f"series {rec.id}: note at {tuple(ann.xy)!r} falls outside "
                    f"the axes — annotation_clip drops it silently (use "
                    f"mixed 'units' or widen the lim)",
                )
                break  # 同一 note 系列报一次就够


def _lint_sig_outside(ax, ax2, recs, lint):
    """sig-outside-axes：括号横梁贴着或超出 y 窗沿——pad + 一行星号字高
    没有余量时文本压框线/画出画布（clip_on=False 的括号不哑火，只是越界）。
    在 _apply_axis 之后跑：用户 lim 与 autoscale 结果都是终态。"""
    for rec in recs:
        if rec.kind != "sig" or not rec.sig_spans:
            continue
        target = ax2 if (rec.merged.get("axis") == "y2" and ax2 is not None) else ax
        target.relim()
        target.autoscale_view()
        y0, y1 = sorted(target.get_ylim())
        yr = y1 - y0
        fig = target.figure
        h_in = (
            target.bbox.height / fig.dpi if target.bbox.height else fig.get_figheight()
        )
        for y, pad, fs in rec.sig_spans:
            # 星号/文本顶沿：字高 ×1.3 行距换算 pt → inch → data
            txt_top = y + pad + (fs * 1.3 / 72.0) / max(h_in, 0.1) * yr
            if not (y0 <= y <= y1):
                lint(
                    "sig-outside-axes",
                    f"series {rec.id}: bracket beam at y={y:g} falls outside "
                    f"the y window [{y0:g}, {y1:g}]",
                )
                break
            if txt_top > y1:
                lint(
                    "sig-outside-axes",
                    f"series {rec.id}: bracket at y={y:g} leaves no headroom "
                    f"for its label (top ≈{txt_top:g} > ylim {y1:g}) — "
                    f"raise yaxis.lim or lower 'y'",
                )
                break


# ------------------------------------------------------------------ 图例


def _art_color(art):
    """所画 artist 首个可解析的 face/edge/line 颜色；都没有则 None。"""
    for attr in ("get_facecolor", "get_edgecolor", "get_color"):
        fn = getattr(art, attr, None)
        if fn is None:
            continue
        arr = np.asarray(fn(), dtype=float)
        if arr.ndim == 2 and len(arr):
            return tuple(arr[0])
        if arr.ndim == 1 and arr.size in (3, 4):
            return tuple(arr)
    return None


def _series_handle(rec, g, label):
    """克隆本组所画 artist 的图例句柄替身。"""
    art = g.artist
    hd = None
    if isinstance(art, Line2D):
        hd = Line2D(
            [],
            [],
            color=art.get_color(),
            linestyle=art.get_linestyle(),
            marker=art.get_marker(),
            linewidth=art.get_linewidth(),
            markersize=art.get_markersize(),
            label=label,
        )
    elif isinstance(art, BarContainer):
        p = art.patches[0] if art.patches else None
        hd = Patch(
            facecolor=p.get_facecolor() if p is not None else fv.HUES["vgray"],
            edgecolor=p.get_edgecolor() if p is not None else "white",
            hatch=p.get_hatch() if p is not None else None,
            label=label,
        )
    elif isinstance(art, PathCollection):  # scatter：marker、无线
        hd = Line2D(
            [],
            [],
            linestyle="None",
            marker=g.marker or "o",
            color=_art_color(art) or fv.HUES["vgray"],
            markersize=5,
            label=label,
        )
    elif rec.kind == "contour" or (
        rec.kind == "quiver" and rec.merged.get("m") is not None
    ):
        # cmap 映射艺术家：首个 facecolor 常是低值浅带，swatch 取色带
        # 中上段更接近"这个场"的视觉签名
        get_cmap = getattr(art, "get_cmap", None)
        hd = Patch(
            facecolor=get_cmap()(0.65) if get_cmap else fv.HUES["vgray"],
            edgecolor="none",
            label=label,
        )
    elif art is not None and hasattr(art, "get_facecolor"):
        # band PolyCollection / span Patch——取所画填充的色样
        hd = Patch(
            facecolor=_art_color(art) or fv.HUES["vgray"], edgecolor="none", label=label
        )
    if hd is None:
        merged = rec.merged
        if rec.kind == "donut" and rec.handles:
            hd = Patch(
                facecolor=rec.handles[0].get_facecolor(), edgecolor="white", label=label
            )
        elif rec.kind in ("bar", "donut", "band", "span", "hist", "box", "violin"):
            hd = Patch(
                facecolor=g.color or fv.HUES["vgray"], edgecolor="white", label=label
            )
        else:
            hd = Line2D(
                [],
                [],
                color=g.color or fv.HUES["vgray"],
                linestyle=merged.get("ls") or ("--" if rec.kind == "pred" else "-"),
                marker=g.marker or merged.get("marker"),
                linewidth=merged.get("lw", 1.2),
                markersize=merged.get("ms", 3.5),
                label=label,
            )
    _mark(hd)
    return hd


def _entry_handle(entry, ctx):
    if "handle" in entry:
        h = _obj(entry["handle"], "legend entry handle")
        h = dict(h)
        _check_keys(
            h, {"label", "color", "ls", "marker", "lw", "ms"}, "legend entry handle"
        )
        label = h.pop("label", None)
        color = ctx.colors.token(h.pop("color", "vink"), ctx.lint_proxy(None))
        hd = Line2D(
            [],
            [],
            color=color,
            label=label,
            linestyle=h.pop("ls", "-"),
            marker=h.pop("marker", None),
            linewidth=h.pop("lw", 1.2),
            markersize=h.pop("ms", 3.5),
        )
        _mark(hd)
        return hd
    sid = entry.get("series") or entry.get("group")
    if sid is None:
        raise SpecError(f"legend entry needs 'series', 'group' or 'handle': {entry!r}")
    rec = ctx.records.get(sid)
    if rec is None:
        raise SpecError(f"legend entry refers to unknown series {sid!r}")
    g = rec.groups[0] if rec.groups else _Group(None, None, [])
    label = entry.get("label") or g.label or sid
    return _series_handle(rec, g, label)


def _legend_entries(entries, ctx):
    if not isinstance(entries, list):
        raise SpecError(f"legend entries must be a list, got {entries!r}")
    handles = []
    for e in entries:
        _check_keys(
            _obj(e, "legend entry"),
            {"series", "group", "label", "handle"},
            "legend entry",
        )
        if "group" in e and "series" not in e:
            rec = ctx.records.get(e["group"])
            if rec is None:
                raise SpecError(
                    f"legend group entry refers to unknown series {e['group']!r}"
                )
            template = e.get("label")
            for g in rec.groups:
                lbl = (
                    _fmt_label(template, rec, g)
                    if template
                    else (g.label or str(g.raw))
                )
                handles.append(_series_handle(rec, g, lbl))
        else:
            handles.append(_entry_handle(e, ctx))
    return handles


def _legend_kwargs(leg, ctx=None, lint=None):
    kw = {}
    for k in (
        "loc",
        "ncol",
        "fontsize",
        "title",
        "columnspacing",
        "handletextpad",
        "labelspacing",
    ):
        if leg.get(k) is not None:
            kw[k] = leg[k]
    kw.update(_resolve_props(leg.get("props"), ctx, lint))
    return kw


def _ordered_handles(ax, recs, ax2=None):
    """自动图例句柄按 spec 系列声明序重排：mpl 的收集序按 artist 类型
    分组（scatter 的 PathCollection 排在 BarContainer 前），与声明序
    脱钩。各 (rec,group) 按图例标签认领首个未用同名句柄；认领剩的
    （connect 幽灵句柄等）保持 mpl 序殿后。ax2 给定时合并双轴句柄。"""
    h, labels = ax.get_legend_handles_labels()
    if ax2 is not None:
        h2, l2 = ax2.get_legend_handles_labels()
        h, labels = h + h2, labels + l2
    pairs = [(a, lb) for a, lb in zip(h, labels) if lb]
    used = [False] * len(pairs)
    out = []
    for rec in recs:
        for g in rec.groups:
            lab = _legend_label(rec, g)
            if lab is None:
                continue
            for i, (_a, lb) in enumerate(pairs):
                if not used[i] and lb == lab:
                    used[i] = True
                    out.append(pairs[i][0])
                    break
    out.extend(a for i, (a, _lb) in enumerate(pairs) if not used[i])
    return out


def _panel_legend(ax, recs, leg, ctx, pid, donut_handles=None, ax2=None):
    if leg is None or leg is False:
        return
    if leg is True:
        leg = {}
    leg = _obj(leg, f"panel {pid} legend")
    _check_keys(leg, LEGEND_KEYS, f"panel {pid} legend")
    if leg.keys() & {"where", "cell", "from"}:
        raise SpecError(
            f"panel {pid} legend: 'where'/'cell'/'from' are figure-level "
            f"keys — move them to the top-level 'legend' block"
        )
    kw = _legend_kwargs(leg, ctx, ctx.lint_proxy(pid))
    entries = leg.get("entries")
    if entries is not None and entries != "auto":
        ax.legend(handles=_legend_entries(entries, ctx), **kw)
    elif donut_handles:
        ax.legend(handles=donut_handles, **kw)
    else:
        # twin 面板的自动图例必须合并两轴句柄——ax.legend() 只收宿主轴，
        # y2 上的 series 会被静默丢掉（与 _figure_legend 同款收集法）；
        # 无标签时回落裸 legend() 保留 mpl 的 no-artists 警告
        handles = _ordered_handles(ax, recs, ax2)
        if handles:
            ax.legend(handles=handles, **kw)
        else:
            ax.legend(**kw)


def _figure_legend(fig, cell_axes, ctx, panels_meta, caption_frac=0.0):
    leg = ctx.spec.get("legend")
    if leg is None or leg is False:
        return
    if leg is True:
        leg = {}
    leg = _obj(leg, "legend")
    _check_keys(leg, LEGEND_KEYS, "legend")
    where = leg.get("where", "below")
    if where not in _LEGEND_WHERE:
        raise SpecError(
            f"legend.where {where!r} unknown{_hint(where, _LEGEND_WHERE)}"
            f" (valid: {sorted(_LEGEND_WHERE)})"
        )
    kw = _legend_kwargs(leg, ctx)
    entries = leg.get("entries")
    if entries is not None and entries != "auto":
        handles = _legend_entries(entries, ctx)
    else:
        want = leg.get("from")
        if want is not None:
            if not isinstance(want, list):
                raise SpecError(
                    f"legend.from must be a list of panel ids, got {want!r}"
                )
            known = {m["id"] for m in panels_meta}
            bad = [p for p in want if p not in known]
            if bad:
                raise SpecError(
                    f"legend.from refers to unknown panels {bad} (have {sorted(known)})"
                )
        handles, labels = [], []
        for m in panels_meta:
            if want is not None and m["id"] not in want:
                continue
            if want is None and m["own_legend"]:
                continue
            hh = m.get("handles")
            if hh is not None:
                for h in hh:
                    if h.get_label() not in labels:
                        handles.append(h)
                        labels.append(h.get_label())
                continue
            for h in _ordered_handles(m["ax"], m["recs"], m.get("ax2")):
                lb = h.get_label()
                if lb and lb not in labels:
                    handles.append(h)
                    labels.append(lb)
        if not handles:
            ctx.lint(
                "empty-legend",
                "figure legend collected no handles — no series carries a "
                "label; by-fanout groups need `label` (e.g. '{v}' = group "
                "key) to be collected",
            )
            return
    kw.setdefault("ncol", min(len(handles), 4))
    if where == "cell":
        cell_ax = cell_axes.get(leg.get("cell"))
        if cell_ax is None:
            raise SpecError(
                f"legend.where='cell' needs a named empty cell "
                f"{leg.get('cell')!r} in layout.cells"
            )
        kw.setdefault("loc", "center")
        cell_ax.legend(handles=handles, **kw)
    else:
        kw.setdefault("loc", "lower center")
        if caption_frac:
            # 底部 meta.caption 占了画布最下沿——图例整体上移让位
            kw.setdefault("bbox_to_anchor", (0.5, caption_frac))
        fig.legend(handles=handles, **kw)


# -------------------------------------------------------------------- 规格


def _resolve_theme(spec):
    name = spec.get("theme", "paper")
    if name not in fv.THEMES:
        raise SpecError(
            f"unknown theme {name!r}{_hint(name, fv.THEMES)}; "
            f"valid: {sorted(fv.THEMES)}"
        )
    return name


def _apply_rc(spec):
    rc = _obj(spec.get("rc"), "rc")
    _check_keys(rc, RC_KEYS, "rc")
    base = rc.get("base", 7.6)
    plt.rcParams.update(fv.font_rc(rc.get("font", "serif")))
    plt.rcParams.update(
        {
            "font.size": base,
            "axes.titlesize": base,
            "axes.labelsize": base,
            "xtick.labelsize": base - 1.2,
            "ytick.labelsize": base - 1.2,
            "legend.fontsize": base - 1.2,
            "axes.linewidth": 0.6,
            "axes.labelpad": 1.8,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 2.2,
            "ytick.major.size": 2.2,
            "xtick.major.pad": 1.8,
            "ytick.major.pad": 1.8,
            "grid.linewidth": 0.5,
            "legend.handlelength": 1.5,
            "legend.handletextpad": 0.5,
            "legend.columnspacing": 0.9,
            "legend.borderaxespad": 0.2,
            "lines.linewidth": 1.1,
            "lines.markersize": 3.2,
        }
    )


def _figsize(spec, nrows):
    slots = dict(SIZE_SLOTS)
    slots.update(_obj(spec.get("size_slots"), "size_slots"))
    size = spec.get("size", "half")
    if isinstance(size, str):
        if size not in slots:
            raise SpecError(f"size slot {size!r} unknown (have {sorted(slots)})")
        return slots[size], ROW_HEIGHT * nrows
    if isinstance(size, dict):
        _check_keys(size, {"slot", "height"}, "size")
        slot = size.get("slot", "half")
        if slot not in slots:
            raise SpecError(f"size.slot {slot!r} unknown (have {sorted(slots)})")
        return slots[slot], size.get("height", ROW_HEIGHT * nrows)
    if isinstance(size, (list, tuple)) and len(size) == 2:
        return float(size[0]), float(size[1])
    raise SpecError("size must be a slot name, {slot,height} or [w,h]")


def _panels(spec):
    if "panels" in spec:
        _check_keys(spec, TOP_KEYS, "spec")
        panels = spec["panels"]
        if not isinstance(panels, dict) or not panels:
            raise SpecError("panels must be a non-empty object")
        return dict(panels)
    _check_keys(spec, TOP_KEYS | PANEL_KEYS, "spec")
    panel = {k: spec[k] for k in PANEL_KEYS if k in spec}
    if panel:
        # flat 形式：带 figure 专有键（where/cell/from）的 'legend' dict
        # 是 figure 图例计划；其他一律按面板图例处理，必须对
        # _figure_legend 隐藏。调用方传的是 spec 副本。
        # 空 flat 面板（matrix 的模板还没展开）不动 legend——顶层 legend
        # 在那里只有 figure 语义。
        leg = spec.get("legend")
        if isinstance(leg, dict) and leg.keys() & {"where", "cell", "from"}:
            panel.pop("legend", None)
        elif "legend" in spec:
            spec.pop("legend")
    return {"a": panel}


class _Plan:
    """layout 归一化产物：逻辑网格 + 每面板 rect + strip margin + bind。

    ``cells`` 是逻辑格（行主序、null=空格、非面板 id=命名格，grid/matrix
    用）；``placements`` 是全部占位 ``(pid, r0, c0, r1, c1)``——grid 与
    matrix 恒单位格，spans 可跨格。``strip_top``/``strip_right`` 是 margin
    格计划（gridspec 顶部加一行/右侧加一列，逻辑坐标不受影响）；
    ``bind`` 是 ``{side_pid: (main_pid, 'x'|'y')}`` 边际轴配对。
    """

    __slots__ = (
        "bind",
        "cells",
        "edge",
        "layout",
        "ncols",
        "nrows",
        "order",
        "panels",
        "placements",
        "sharex",
        "sharey",
        "strip_right",
        "strip_top",
    )

    def __init__(self, layout, panels):
        self.layout = layout
        self.panels = panels
        self.cells = []
        self.placements = []
        self.order = []  # panel ids in position order (tag 序)
        self.nrows = self.ncols = 0
        self.sharex = layout.get("sharex")
        self.sharey = layout.get("sharey")
        self.strip_top = self.strip_right = None
        self.bind = {}
        self.edge = {"rows": None, "cols": None}  # 归一化 rows/cols cfg

    @property
    def gs_rows(self):
        return self.nrows + (1 if self.strip_top else 0)

    @property
    def gs_cols(self):
        return self.ncols + (1 if self.strip_right else 0)

    @property
    def top_off(self):
        return 1 if self.strip_top else 0

    def width_ratios(self):
        r = _ratio_list(self.layout.get("width_ratios"), self.ncols, "width_ratios")
        if self.strip_right:
            r.append(self.strip_right["size"])
        return r

    def height_ratios(self):
        r = _ratio_list(self.layout.get("height_ratios"), self.nrows, "height_ratios")
        if self.strip_top:
            r.insert(0, self.strip_top["size"])
        return r


def _ratio_list(v, n, name):
    if v is None:
        return [1.0] * n
    if not (
        isinstance(v, (list, tuple))
        and len(v) == n
        and all(_is_num(x) and x > 0 for x in v)
    ):
        raise SpecError(f"layout.{name} must be {n} positive numbers, got {v!r}")
    return list(v)


def _layout_cells(spec, panels, ctx):
    layout = _obj(spec.get("layout"), "layout")
    _check_keys(layout, LAYOUT_KEYS, "layout")
    kind = layout.get("kind", "grid")
    if kind == "matrix":
        plan = _layout_matrix(spec, layout, ctx)
    elif kind == "spans":
        plan = _layout_spans(spec, layout, panels)
    elif kind == "grid":
        plan = _layout_grid(spec, layout, panels)
    else:
        raise SpecError(
            f"layout.kind {kind!r} unknown; implemented: 'grid'|'matrix'|'spans'"
        )
    _layout_bind(plan, layout)
    _layout_edge_labels(plan)
    return plan


def _layout_grid(spec, layout, panels):
    for k in ("template", "overrides", "map", "strips"):
        if k in layout:
            raise SpecError(
                f"layout.{k} has no meaning for kind 'grid' "
                f"('template'/'overrides'/'strips' → 'matrix', "
                f"'map' → 'spans')"
            )
    cells = layout.get("cells")
    ids = list(panels)
    if cells is None:
        shape = layout.get("shape", [1, len(ids)])
        if not (
            isinstance(shape, (list, tuple))
            and len(shape) == 2
            and all(isinstance(v, int) and v >= 1 for v in shape)
        ):
            raise SpecError(
                f"layout.shape must be [rows, cols] of positive ints, got {shape!r}"
            )
        ncols = shape[1]
        cells = [ids[i : i + ncols] for i in range(0, len(ids), ncols)]
    elif not (
        isinstance(cells, list) and cells and all(isinstance(r, list) for r in cells)
    ):
        raise SpecError(f"layout.cells must be a non-empty list of rows, got {cells!r}")
    for r in cells:
        for c in r:
            if c is not None and not isinstance(c, str):
                raise SpecError(
                    f"layout.cells: cell ids must be strings or null, got {c!r}"
                )
    nrows = len(cells)
    ncols = max(len(r) for r in cells)
    # 图版放宽：全部面板都是 image cell（含 image、其余只许中性 overlay）
    # → 方法×样本展示墙的 64 格/边 16；普通网格守 8 格/边 4 密度纪律
    plate = bool(ids) and all(_plate_cell(panels[i]) for i in ids)
    max_cells, max_dim = (
        (MAX_PLATE_CELLS, MAX_PLATE_DIM) if plate else (MAX_GRID_CELLS, MAX_GRID_DIM)
    )
    if ncols < 1 or nrows > max_dim or ncols > max_dim or nrows * ncols > max_cells:
        raise SpecError(
            f"layout grid {nrows}x{ncols} exceeds {max_cells} cells "
            f"(max dim {max_dim}) or is empty"
            + (
                ""
                if plate
                else " — a grid whose panels all draw 'image' series "
                "(image-plate: rows=methods, cols=samples) gets the "
                "relaxed 64/16 cap"
            )
        )
    seen = set()
    for row in cells:
        for c in row:
            if c is None:
                continue
            if c in seen:
                raise SpecError(f"layout.cells: cell {c!r} placed twice")
            seen.add(c)
    missing = [i for i in ids if i not in seen]
    if missing:
        raise SpecError(f"layout.cells: panels {missing} not placed")
    plan = _Plan(layout, panels)
    plan.cells = cells
    plan.nrows, plan.ncols = nrows, ncols
    plan.placements = [
        (pid, r, c, r + 1, c + 1)
        for r, row in enumerate(cells)
        for c, pid in enumerate(row)
        if pid is not None
    ]
    plan.order = [c for row in cells for c in row if c in panels]
    plan.edge = {
        "rows": _edge_cfg(layout.get("rows"), "layout.rows", "ylabel", False),
        "cols": _edge_cfg(layout.get("cols"), "layout.cols", "xlabel", False),
    }
    return plan


def _layout_spans(spec, layout, panels):
    for k in ("cells", "template", "overrides", "strips"):
        if k in layout:
            raise SpecError(
                f"layout.{k} has no meaning for kind 'spans' — position "
                f"panels via 'map' ('cells' → 'grid', "
                f"'template'/'overrides'/'strips' → 'matrix')"
            )
    m = layout.get("map")
    if not isinstance(m, dict) or not m:
        raise SpecError(
            "layout.kind='spans' needs a non-empty 'map' object "
            "{panel-or-cell-id: [r0, c0, r1, c1]} (half-open rect)"
        )
    rects = {}
    for cid, rect in m.items():
        if not (
            isinstance(rect, (list, tuple))
            and len(rect) == 4
            and all(isinstance(v, int) and not isinstance(v, bool) for v in rect)
        ):
            raise SpecError(
                f"layout.map {cid!r}: must be [r0, c0, r1, c1] ints, got {rect!r}"
            )
        r0, c0, r1, c1 = rect
        if r0 < 0 or c0 < 0 or r1 <= r0 or c1 <= c0:
            raise SpecError(
                f"layout.map {cid!r}: bad rect {rect!r} — need r1>r0, "
                f"c1>c0, non-negative"
            )
        rects[cid] = (r0, c0, r1, c1)
    nrows = max(r[2] for r in rects.values())
    ncols = max(r[3] for r in rects.values())
    shape = layout.get("shape")
    if shape is not None:
        if not (
            isinstance(shape, (list, tuple))
            and len(shape) == 2
            and all(isinstance(v, int) and v >= 1 for v in shape)
        ):
            raise SpecError(
                f"layout.shape must be [rows, cols] of positive ints, got {shape!r}"
            )
        if shape[0] < nrows or shape[1] < ncols:
            raise SpecError(
                f"layout.shape {shape} does not contain the map rects "
                f"(needs at least [{nrows}, {ncols}])"
            )
        nrows, ncols = shape
    ids = list(rects)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if _rect_overlap(rects[ids[i]], rects[ids[j]]):
                raise SpecError(
                    f"layout.map: {ids[i]!r} and {ids[j]!r} overlap — "
                    f"gridspec cells are exclusive"
                )
    missing = [p for p in panels if p not in rects]
    if missing:
        raise SpecError(f"layout.map: panels {missing} not placed")
    plate = bool(panels) and all(_plate_cell(p) for p in panels.values())
    max_panels, max_dim = (
        (MAX_PLATE_CELLS, MAX_PLATE_DIM) if plate else (MAX_GRID_CELLS, MAX_SPANS_DIM)
    )
    # 面板数只计真实面板——命名空格（axis-off 格、legend.where 目标）是
    # 占格不是面板，不占用 8 面板纪律名额；网格边长仍按 max_dim 收
    npan = sum(1 for cid in rects if cid in panels)
    if ncols < 1 or nrows > max_dim or ncols > max_dim or npan > max_panels:
        raise SpecError(
            f"layout spans {nrows}x{ncols} with {npan} panels "
            f"exceeds {max_panels} panels or max grid dim {max_dim} "
            f"(named axis-off cells do not count toward the panel cap)"
        )
    plan = _Plan(layout, panels)
    plan.nrows, plan.ncols = nrows, ncols
    plan.placements = [(pid, *rects[pid]) for pid in rects]
    plan.order = [
        pid
        for pid, *_ in sorted(plan.placements, key=lambda p: (p[1], p[2]))
        if pid in panels
    ]
    plan.edge = {
        "rows": _edge_cfg(layout.get("rows"), "layout.rows", "ylabel", False),
        "cols": _edge_cfg(layout.get("cols"), "layout.cols", "xlabel", False),
    }
    return plan


def _rect_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# ------------------------------------------------------------ kind 'matrix'


def _layout_matrix(spec, layout, ctx):
    """template × rows/cols facet 展开：每格代入 $row/$col、注入 facet
    where、派生 strip 文本，产 panels + cells + strip margins。"""
    for k in ("shape", "cells", "map"):
        if k in layout:
            raise SpecError(
                f"layout.{k} has no meaning for kind 'matrix' — the grid "
                f"is derived from rows x cols"
            )
    # 顶层 'legend' 放行——panels 形态下同位，只有 figure-legend 语义；
    # 面板级 legend 走 template/overrides
    if "panels" in spec or any(k in spec for k in PANEL_KEYS - {"legend"}):
        raise SpecError(
            "layout.kind='matrix' expands layout.template into panels — "
            "top-level 'panels' and panel fields are not allowed "
            "(per-cell patches go to layout.overrides)"
        )
    tpl = _obj(layout.get("template"), "layout.template")
    if not tpl:
        raise SpecError("layout.kind='matrix' needs a non-empty 'template' panel")
    _check_keys(tpl, PANEL_KEYS, "layout.template")
    rows = _edge_cfg(layout.get("rows"), "layout.rows", "ylabel", True)
    cols = _edge_cfg(layout.get("cols"), "layout.cols", "xlabel", True)
    has_rows = rows["values"] is not None or rows["field"] is not None
    has_cols = cols["values"] is not None or cols["field"] is not None
    if not has_rows and not has_cols:
        raise SpecError(
            "layout.kind='matrix' needs facet values: layout.rows and/or "
            "layout.cols (a value list, or {'field': f} to derive them "
            "from the template's dataset)"
        )
    used_ph = _facet_placeholders(tpl)
    if "$row" in used_ph and not has_rows:
        raise SpecError("layout.template uses '$row' but layout.rows is absent")
    if "$col" in used_ph and not has_cols:
        raise SpecError("layout.template uses '$col' but layout.cols is absent")
    rvals = _facet_values(rows, "rows", tpl, ctx) or [None]
    cvals = _facet_values(cols, "cols", tpl, ctx) or [None]
    plan = _Plan(layout, {})
    plan.nrows, plan.ncols = len(rvals), len(cvals)
    plan.cells = []
    used_ids = set()
    for ri, rv in enumerate(rvals):
        line = []
        for ci, cv in enumerate(cvals):
            pid = _matrix_pid(rv, cv, ri, ci, used_ids)
            p = _facet_subst(tpl, rv, cv)
            _facet_inject(p, pid, rows["field"], rv, cols["field"], cv)
            plan.panels[pid] = p
            line.append(pid)
        plan.cells.append(line)
    pos_of = {
        pid: (ri, ci) for ri, row in enumerate(plan.cells) for ci, pid in enumerate(row)
    }
    for key, patch in _obj(layout.get("overrides"), "layout.overrides").items():
        ri, ci = _matrix_pos(key, pos_of, plan.nrows, plan.ncols)
        pid = plan.cells[ri][ci]
        if patch is None or patch is False:
            plan.cells[ri][ci] = None
            plan.panels.pop(pid, None)
        elif isinstance(patch, str):
            # 命名空格：跟 grid.cells 的命名格同语义——图例格/占格
            plan.cells[ri][ci] = patch
            plan.panels.pop(pid, None)
        elif isinstance(patch, dict):
            _check_keys(patch, PANEL_KEYS, f"layout.overrides {key!r}")
            merged = _merge_panel(plan.panels[pid], patch)
            # 补丁整体替换 series 时 facet 注入要重跑——不然这格会静默
            # 画全量数据（漂移）；矛盾 where 同样响亮拒
            _facet_inject(
                merged, pid, rows["field"], rvals[ri], cols["field"], cvals[ci]
            )
            plan.panels[pid] = merged
        else:
            raise SpecError(
                f"layout.overrides {key!r}: must be null | a cell name | "
                f"a panel patch object, got {patch!r}"
            )
    # 模板/补丁里的显式 series id 逐格加面板前缀（'of' 引用同步改写）——
    # 统一在 overrides 之后做一遍，补丁引入的 id 与模板 id 同口径处理
    for pid, p in plan.panels.items():
        _matrix_series_ids(p, pid)
    plan.placements = [
        (pid, ri, ci, ri + 1, ci + 1)
        for ri, row in enumerate(plan.cells)
        for ci, pid in enumerate(row)
        if pid is not None
    ]
    plan.order = [pid for pid, *_ in plan.placements if pid in plan.panels]
    ids = plan.order
    plate = bool(ids) and all(_plate_cell(plan.panels[i]) for i in ids)
    max_cells, max_dim = (
        (MAX_PLATE_CELLS, MAX_PLATE_DIM)
        if plate
        else (MAX_MATRIX_CELLS, MAX_MATRIX_DIM)
    )
    if (
        plan.ncols < 1
        or plan.nrows > max_dim
        or plan.ncols > max_dim
        or plan.nrows * plan.ncols > max_cells
    ):
        raise SpecError(
            f"matrix {plan.nrows}x{plan.ncols} exceeds {max_cells} cells "
            f"(max dim {max_dim}) — split the figure"
        )
    # strips：facet margin 位置——'top'（列条）|'right'（行条）|'both'
    # （默认，现状）|'none'；单边关闭用于贴边排版或自绘表头场景
    strips = layout.get("strips", "both")
    if strips not in ("top", "right", "both", "none"):
        raise SpecError(
            f"layout.strips must be 'top'|'right'|'both'|'none', got {strips!r}"
        )
    plan.strip_top = (
        _strip_plan(cols, None if cvals == [None] else cvals, "layout.cols")
        if strips in ("top", "both")
        else None
    )
    plan.strip_right = (
        _strip_plan(rows, None if rvals == [None] else rvals, "layout.rows")
        if strips in ("right", "both")
        else None
    )
    # facet 默认共享轴：同列同 x、同行同 y（显式 false 可关）
    plan.sharex = layout.get("sharex", "col")
    plan.sharey = layout.get("sharey", "row")
    plan.edge = {"rows": rows, "cols": cols}
    return plan


def _edge_cfg(v, where, label_key, matrix):
    """rows/cols 配置归一。非 matrix 只收边默认 {label_key}；matrix 额外
    收 facet 形 {field, values, labels, strip} 与裸 values 列表。"""
    out = {"field": None, "values": None, "labels": {}, "strip": True}
    out["edge_label"] = None
    if v is None:
        return out
    if isinstance(v, (list, tuple)):
        if not matrix:
            raise SpecError(
                f"{where}: a bare value list is matrix-only — for "
                f"'grid'/'spans' give {{'{label_key}': ...}}"
            )
        if not v:
            raise SpecError(f"{where}: facet values must be a non-empty list")
        out["values"] = list(v)
        return out
    if not isinstance(v, dict):
        raise SpecError(f"{where} must be a list or object, got {v!r}")
    allowed = {label_key}
    if matrix:
        allowed |= {"field", "values", "labels", "strip"}
    _check_keys(v, allowed, where)
    ek = v.get(label_key)
    if ek is not None and not isinstance(ek, str):
        raise SpecError(f"{where}.{label_key} must be a string, got {ek!r}")
    out["edge_label"] = ek
    if not matrix:
        return out
    if v.get("field") is not None and not isinstance(v["field"], str):
        raise SpecError(f"{where}.field must be a string, got {v['field']!r}")
    out["field"] = v.get("field")
    vals = v.get("values")
    if vals is not None:
        if not isinstance(vals, (list, tuple)) or not vals:
            raise SpecError(f"{where}.values must be a non-empty list")
        out["values"] = list(vals)
    labs = v.get("labels")
    if labs is not None:
        if not isinstance(labs, dict):
            raise SpecError(f"{where}.labels must be an object, got {labs!r}")
        out["labels"] = {_norm_key(k): t for k, t in labs.items()}
    out["strip"] = v.get("strip", True)
    return out


def _facet_values(cfg, edge, tpl, ctx):
    """facet 值：显式 values；缺省且给了 field → 从模板数据集的列派生
    （数值可排则排序，否则首见序——strip 与 where 同源，天然不漂移）。"""
    vals = cfg["values"]
    if vals is not None:
        return list(vals)
    if cfg["field"] is None:
        return None
    ds = tpl.get("from")
    if ds is None:
        if len(ctx.data) == 1:
            ds = next(iter(ctx.data))
        else:
            raise SpecError(
                f"layout.{edge}: 'values' omitted — derivation needs an "
                f"unambiguous dataset (set template.from or give 'values')"
            )
    if ds not in ctx.data:
        raise SpecError(
            f"layout.{edge}: template.from {ds!r} is not a dataset "
            f"(have {sorted(ctx.data)})"
        )
    seen = []
    for r in ctx.data[ds]:
        v = r.get(cfg["field"])
        if v is not None and v not in seen:
            seen.append(v)
    if not seen:
        raise SpecError(
            f"layout.{edge}: field {cfg['field']!r} produced no values "
            f"in dataset {ds!r}"
        )
    if all(_is_num(v) for v in seen):
        seen.sort()
    return seen


def _facet_str(v):
    return "" if v is None else str(v)


def _facet_slug(v):
    if v is None:
        return ""
    return re.sub(r"[^0-9A-Za-z]+", "-", str(v)).strip("-")


def _matrix_pid(rv, cv, ri, ci, used):
    base = "-".join(s for s in (_facet_slug(rv), _facet_slug(cv)) if s)
    if not base:
        base = f"cell-{ri}-{ci}"
    pid, k = base, 2
    while pid in used:
        pid = f"{base}~{k}"
        k += 1
    used.add(pid)
    return pid


def _matrix_pos(key, pos_of, nrows, ncols):
    if key in pos_of:
        return pos_of[key]
    m = re.fullmatch(r"(\d+),(\d+)", str(key))
    if m:
        ri, ci = int(m.group(1)), int(m.group(2))
        if 0 <= ri < nrows and 0 <= ci < ncols:
            return ri, ci
    raise SpecError(
        f"layout.overrides: {key!r} is not a matrix cell — keys are "
        f"auto-ids '<row>-<col>' or positions '<r>,<c>'"
    )


def _facet_placeholders(node, found=None):
    if found is None:
        found = set()
    if isinstance(node, str):
        if "$row" in node:
            found.add("$row")
        if "$col" in node:
            found.add("$col")
    elif isinstance(node, dict):
        for k, v in node.items():
            _facet_placeholders(k, found)
            _facet_placeholders(v, found)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _facet_placeholders(v, found)
    return found


def _facet_subst(node, rv, cv):
    """模板深拷贝 + $row/$col 代入：整串 '$row' → 保类型的 facet 值
    （where 条件等）；字符串内嵌 $row → str 插值（title/label/字段名）。"""
    if isinstance(node, str):
        if node == "$row":
            return rv
        if node == "$col":
            return cv
        out = node
        if "$row" in out:
            out = out.replace("$row", _facet_str(rv))
        if "$col" in out:
            out = out.replace("$col", _facet_str(cv))
        return out
    if isinstance(node, list):
        return [_facet_subst(v, rv, cv) for v in node]
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if isinstance(k, str):
                k = k.replace("$row", _facet_str(rv)).replace("$col", _facet_str(cv))
            out[k] = _facet_subst(v, rv, cv)
        return out
    return node


def _series_data_bound(s, p):
    """渲染期 needs_data 的展开期镜像（与 _prepare_series 同式）：该
    series 有数据源才注入 facet where——裸 note/ref/span 注入会在渲染期
    炸 'where needs a data source'（无数据集可解析注入的过滤条件）。"""
    kind = s.get("kind")
    at = s.get("at")
    dim_at = (
        p.get("kind", "xy") == "radar"
        and isinstance(at, str)
        and at in (p.get("dims") or [])
    )
    return (
        (
            kind not in _NEUTRAL_KINDS
            and not (kind in ("heat", "contour") and "matrix" in s)
            and not (kind == "image" and ("path" in s or "rgb" in s))
            and not (kind == "sankey" and "flows" in s)
        )
        or "of" in s
        or "by" in s
        or "from" in s
        or (isinstance(at, (str, dict)) and not dim_at)
    )


def _facet_inject(p, pid, rf, rv, cf, cv):
    """facet 字段 → 数据 series 的 where 注入。strip 文本与注入条件同源
    （同一个 rv/cv），手写漂移在构造上不可能；显式 where 与 facet 值
    冲突 → SpecError。"""
    inj = {}
    if rf is not None:
        inj[rf] = rv
    if cf is not None:
        inj[cf] = cv
    if not inj:
        return
    pw = p.get("where")
    if pw is not None:
        pw = _obj(pw, f"panel {pid} where")
        for f, v in inj.items():
            if f in pw and pw[f] != v:
                raise SpecError(
                    f"panel {pid}: where[{f!r}]={pw[f]!r} contradicts the "
                    f"facet value {v!r} — the matrix injects facet fields "
                    f"itself; drop the clashing clause"
                )
    for s in p.get("series") or []:
        if not isinstance(s, dict):
            continue
        if "of" in s and "where" not in s:
            continue  # 继承父系列 where——父级已注入，不再覆盖
        if not _series_data_bound(s, p):
            continue
        w = dict(_obj(s.get("where"), f"panel {pid} series where"))
        for f, v in inj.items():
            if f in w and w[f] != v:
                raise SpecError(
                    f"panel {pid} series: where[{f!r}]={w[f]!r} "
                    f"contradicts the facet value {v!r}"
                )
            w[f] = v
        s["where"] = w


def _matrix_series_ids(p, pid):
    """模板里的显式 series id 在每格展开时撞名（ctx.records 全局命名
    空间）——按格加 pid 前缀；同格 'of' 引用同步改写，跨格 'of' 留
    原样让渲染期响亮拒。"""
    ser = [s for s in (p.get("series") or []) if isinstance(s, dict)]
    remap = {s["id"]: f"{pid}/{s['id']}" for s in ser if "id" in s}
    if not remap:
        return
    for s in ser:
        if "id" in s:
            s["id"] = remap[s["id"]]
        if isinstance(s.get("of"), str) and s["of"] in remap:
            s["of"] = remap[s["of"]]


def _merge_panel(base, patch):
    """overrides 补丁：顶层键替换，dict 值（xaxis/yaxis/y2/legend/where）
    浅合并一层——改轴标签不用重写整块。"""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def _strip_cfg(v, where):
    """strip: true|false|{fmt,bbox,size} → cfg | None。"""
    if v is False:
        return None
    cfg = {"fmt": "{l}", "bbox": True, "size": 0.22}
    if v is None or v is True:
        return cfg
    if not isinstance(v, dict):
        raise SpecError(f"{where}.strip must be true|false|an object, got {v!r}")
    _check_keys(v, {"fmt", "bbox", "size"}, f"{where}.strip")
    if "fmt" in v:
        if not isinstance(v["fmt"], str):
            raise SpecError(f"{where}.strip.fmt must be a string")
        cfg["fmt"] = v["fmt"]
    if "bbox" in v:
        b = v["bbox"]
        if b not in (True, False) and not isinstance(b, dict):
            raise SpecError(f"{where}.strip.bbox must be true|false|an object")
        cfg["bbox"] = b
    if "size" in v:
        s = v["size"]
        if not (_is_num(s) and s > 0):
            raise SpecError(f"{where}.strip.size must be a positive number")
        cfg["size"] = float(s)
    return cfg


def _strip_plan(cfg, vals, where):
    """margin 格计划：strip 文本从 facet 值（与 where 注入同源）+ fmt
    派生——{l}=labels 或 str(v)、{v}=原值、{f}=字段名。"""
    if vals is None:
        return None
    sc = _strip_cfg(cfg["strip"], where)
    if sc is None:
        return None
    fmt = sc["fmt"]
    texts = {}
    for i, v in enumerate(vals):
        try:
            lab = cfg["labels"].get(_norm_key(v), str(v))
        except TypeError:
            lab = str(v)
        texts[i] = (
            fmt.replace("{f}", str(cfg["field"] or ""))
            .replace("{l}", str(lab))
            .replace("{v}", str(v))
        )
    return {"texts": texts, "size": sc["size"], "bbox": sc["bbox"]}


def _layout_bind(plan, layout):
    bind = layout.get("bind")
    if bind is None:
        return
    if not isinstance(bind, dict):
        raise SpecError(f"layout.bind must be an object, got {bind!r}")
    for side, cfg in bind.items():
        if side not in plan.panels:
            raise SpecError(f"layout.bind: {side!r} is not a panel")
        cfg = _obj(cfg, f"layout.bind {side!r}")
        _check_keys(cfg, {"to", "axis"}, f"layout.bind {side!r}")
        main = cfg.get("to")
        if main not in plan.panels:
            raise SpecError(f"layout.bind {side!r}: 'to' panel {main!r} unknown")
        if main == side:
            raise SpecError(f"layout.bind {side!r}: cannot bind to itself")
        axis = cfg.get("axis")
        if axis not in ("x", "y"):
            raise SpecError(f"layout.bind {side!r}: axis must be 'x'|'y', got {axis!r}")
        for pid in (side, main):
            if plan.panels[pid].get("kind", "xy") != "xy":
                raise SpecError(
                    f"layout.bind: {pid!r} is not an 'xy' panel — bind "
                    f"pairs rectilinear axes only"
                )
        plan.bind[side] = (main, axis)


def _layout_edge_labels(plan):
    """rows.ylabel → 左缘（c0 最小列）每面板 yaxis.label；
    cols.xlabel → 底缘（r1 最大行）每面板 xaxis.label。
    已有同文 label 合法，异文 → SpecError（这正是要防的漂移）。
    bind 的 side 面板（joint 边际、clustermap 侧条）整体豁免——
    它们的自由轴是另一个量（密度/树状图），不该领主轴标签。"""
    rl = plan.edge["rows"]["edge_label"]
    cl = plan.edge["cols"]["edge_label"]
    if rl is None and cl is None:
        return
    lmin = min(p[2] for p in plan.placements if p[0] in plan.panels)
    bmax = max(p[3] for p in plan.placements if p[0] in plan.panels)
    for pid, _r0, c0, r1, _c1 in plan.placements:
        if pid not in plan.panels or pid in plan.bind:
            continue
        if rl is not None and c0 == lmin:
            plan.panels[pid] = _merge_axis_label(plan.panels[pid], "yaxis", rl, pid)
        if cl is not None and r1 == bmax:
            plan.panels[pid] = _merge_axis_label(plan.panels[pid], "xaxis", cl, pid)


def _merge_axis_label(p, axname, label, pid):
    cfg = dict(_obj(p.get(axname), f"panel {pid} {axname}"))
    cur = cfg.get("label")
    if cur is not None and cur != label:
        raise SpecError(
            f"panel {pid}: {axname}.label {cur!r} contradicts the edge "
            f"label {label!r} — keep a single declaration"
        )
    if cur is None:
        cfg["label"] = label
        return {**p, axname: cfg}
    return p


def _strip_bbox(b, ctx):
    if not b:
        return None
    d = {"facecolor": "vmist", "edgecolor": "none", "pad": 2.5}
    if isinstance(b, dict):
        d.update(b)
    return _resolve_props(d, ctx)


def _strip_ax(ax):
    ax.axis("off")
    # NullLocator 清掉幻影刻度（axis('off') 不删 Tick 对象，readback 会收）
    ax.xaxis.set_major_locator(NullLocator())
    ax.yaxis.set_major_locator(NullLocator())


def _draw_strips(fig, gs, plan, ctx):
    """facet strip margin 格：axis-off 格 + 居中标签——strip 是 facet
    标签（住在 margin 格里），不是面板标题；tag 仍走 title slot，
    两者互不占用（(a) 字母与 strip 文本可同时在场）。"""
    fs = plt.rcParams["font.size"] - 1.2
    if plan.strip_top:
        for ci, text in plan.strip_top["texts"].items():
            ax = fig.add_subplot(gs[0, ci])
            _strip_ax(ax)
            t = ax.text(
                0.5,
                0.5,
                text,
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=fs,
                bbox=_strip_bbox(plan.strip_top["bbox"], ctx),
            )
            t.set_gid(_NEUTRAL_GID)
    if plan.strip_right:
        for ri, text in plan.strip_right["texts"].items():
            ax = fig.add_subplot(gs[ri + plan.top_off, plan.ncols])
            _strip_ax(ax)
            t = ax.text(
                0.5,
                0.5,
                text,
                transform=ax.transAxes,
                ha="center",
                va="center",
                rotation=-90,
                fontsize=fs,
                bbox=_strip_bbox(plan.strip_right["bbox"], ctx),
            )
            t.set_gid(_NEUTRAL_GID)


def _plate_cell(p):
    """图版 cell 认定（原始 panel spec）：series 非空、含 image、其余
    只许中性 overlay（ref/span/note）——纯 note 版不算展示墙。"""
    if not isinstance(p, dict):
        return False
    ser = p.get("series")
    if not (isinstance(ser, list) and ser) or not all(isinstance(s, dict) for s in ser):
        return False
    kinds = {s.get("kind") for s in ser}
    return "image" in kinds and kinds <= _IMG_PANEL_KINDS


def _share_anchor(mode, anchors, r, c):
    if mode in (None, False, "none"):
        return None
    key = _share_key(mode, r, c)
    return anchors.get(key)


def _share_register(mode, anchors, r, c, ax):
    if mode in (None, False, "none"):
        return
    anchors.setdefault(_share_key(mode, r, c), ax)


def _share_key(mode, r, c):
    if mode is True or mode == "all":
        return "all"
    if mode == "col":
        return ("c", c)
    if mode == "row":
        return ("r", r)
    raise SpecError(
        f"share mode {mode!r} unknown (valid: true|'all'|'col'|'row'|'none'|false)"
    )


def _auto_tag(pid, order):
    try:
        return "abcdefghijklmnopqrstuvwxyz"[order.index(pid)]
    except (ValueError, IndexError):
        return None


def _resolve_raw(ref):
    if callable(ref):
        return ref
    if isinstance(ref, str) and ":" in ref:
        mod, _, name = ref.partition(":")
        try:
            return getattr(importlib.import_module(mod), name)
        except (ImportError, AttributeError) as e:
            raise SpecError(f"raw ref {ref!r} unresolvable: {e}") from e
    raise SpecError("raw must be a callable or 'pkg.module:func'")


def _savefig_metadata(fmt, ctx):
    """savefig metadata：usermeta 按后端白名单过滤 + 溯源指纹。

    png 任意键透传；pdf/svg 只收各自白名单（svg 对未知键 ValueError，
    pdf 仅 warn——统一提前过滤）；pgf 与其余后端不收 metadata kwarg。
    Creator/Keywords 是溯源指纹，三种格式统一 provenance 永远赢——被
    盖掉的 usermeta 键走 meta-key-reserved lint，被白名单丢的键走
    meta-key-dropped lint，都不静默。
    """
    usermeta = dict(ctx.meta.get("usermeta") or {})
    prov = {
        "Creator": "figure-viz fvspec",
        "Keywords": f"fvspec-spec-sha256:{ctx.spec_sha}",
    }
    if fmt not in {"png", "pdf", "svg"}:
        if usermeta:
            ctx.lint(
                "meta-key-dropped",
                f"meta.usermeta keys dropped — backend {fmt!r} does not "
                f"accept savefig metadata",
            )
        return None
    wl = {"pdf": _META_KEYS_PDF, "svg": _META_KEYS_SVG}.get(fmt)
    kept = (
        dict(usermeta) if wl is None else {k: v for k, v in usermeta.items() if k in wl}
    )
    dropped = sorted(k for k in usermeta if wl is not None and k not in wl)
    if dropped:
        ctx.lint(
            "meta-key-dropped",
            f"meta.usermeta keys {dropped} dropped — not in the {fmt} "
            f"metadata whitelist",
        )
    reserved = sorted(k for k in kept if k in prov)
    if reserved:
        ctx.lint(
            "meta-key-reserved",
            f"meta.usermeta keys {reserved} shadowed by the provenance "
            f"fingerprint — Creator/Keywords always win; rename the "
            f"usermeta keys to keep their values",
        )
    md = {str(k): str(v) for k, v in kept.items()}
    md.update(prov)
    return md


def _reserve_label_headroom(fig):
    """柱顶/柱端标签是渲染器放的（offset points 锚定，autoscale 看不见
    其墨迹）——布局定稿后 draw 一次量真实 extent，把溢出 + 余量补进
    轴限。用户在 yaxis/xaxis.lim 显式钉过的边不动（_apply_axis 记录在
    ax._fv_lim_pinned，单侧 lim 只钉单侧），越界归 audit
    `text-spills-axes` 管；非线性轴跳过（px→data 线性换算不成立）。"""
    axes = list(fig.get_axes())
    i = 0
    while i < len(axes):  # BFS：inset/twin 等后代轴同口径
        for ch in getattr(axes[i], "child_axes", ()):
            if ch not in axes:
                axes.append(ch)
        i += 1
    labeled = [a for a in axes if getattr(a, "_fv_bar_labels", None)]
    if not labeled:
        return
    fig.canvas.draw()
    pad = 2.0  # px
    for a in labeled:
        bb = a.bbox
        need = {"y0": 0.0, "y1": 0.0, "x0": 0.0, "x1": 0.0}
        for t in a._fv_bar_labels:
            if not t.get_visible():
                continue
            ext = t.get_window_extent()
            need["y1"] = max(need["y1"], ext.y1 - bb.y1)
            need["y0"] = max(need["y0"], bb.y0 - ext.y0)
            need["x1"] = max(need["x1"], ext.x1 - bb.x1)
            need["x0"] = max(need["x0"], bb.x0 - ext.x0)
        pinned = getattr(a, "_fv_lim_pinned", None) or {}
        py = pinned.get("y", ())
        px = pinned.get("x", ())
        if (need["y0"] or need["y1"]) and a.get_yscale() == "linear":
            y0, y1 = a.get_ylim()
            dpp = abs(y1 - y0) / max(bb.height, 1)
            sgn = 1.0 if y1 >= y0 else -1.0  # 反转轴外扩方向取反
            a.set_ylim(
                y0 - (need["y0"] + pad) * dpp * sgn
                if need["y0"] and "bottom" not in py
                else y0,
                y1 + (need["y1"] + pad) * dpp * sgn
                if need["y1"] and "top" not in py
                else y1,
            )
        if (need["x0"] or need["x1"]) and a.get_xscale() == "linear":
            x0, x1 = a.get_xlim()
            dpp = abs(x1 - x0) / max(bb.width, 1)
            sgn = 1.0 if x1 >= x0 else -1.0
            a.set_xlim(
                x0 - (need["x0"] + pad) * dpp * sgn
                if need["x0"] and "left" not in px
                else x0,
                x1 + (need["x1"] + pad) * dpp * sgn
                if need["x1"] and "right" not in px
                else x1,
            )


def _save(fig, spec, ctx, base_dir, outdir, dpi):
    output = spec.get("output")
    if not output and not outdir:
        return []
    output = dict(_obj(output, "output"))
    _check_keys(output, OUTPUT_KEYS, "output")
    path = output.get("path")
    if path is None:
        path = Path("figure.png") if outdir else None
        if path is None:
            return []
    path = Path(path)
    if outdir is not None:
        path = Path(outdir) / path.name
    elif not path.is_absolute():
        path = Path(base_dir or ".") / path
    path.parent.mkdir(parents=True, exist_ok=True)
    formats = output.get("formats")
    if not formats:
        formats = [path.suffix.lstrip(".")] if path.suffix else ["png"]
    stem = path.with_suffix("") if path.suffix in {"." + f for f in formats} else path
    # bbox 缺省统一 null：声明的 size（槽位/宽高/缺省版心）就是交付契约，
    # 'tight' 重裁是显式选择而非默认——output.bbox 给什么用什么
    bbox = output.get("bbox")
    if "size" in spec and bbox == "tight":
        ctx.lint(
            "tight-bbox",
            "size declared but output.bbox='tight' re-crops the canvas — "
            "the slot then only pins aspect, not the delivered footprint; "
            "set bbox=null to honor the slot",
        )
    saved = []
    for fmt in formats:
        out = stem.with_suffix("." + fmt)
        kw = {
            "dpi": dpi or output.get("dpi", 300),
            "bbox_inches": bbox,
            "pad_inches": output.get("pad", 0.015),
        }
        md = _savefig_metadata(fmt, ctx)
        if md:
            kw["metadata"] = md
        if fmt == "pgf":
            # pgf 后端不收 metadata kwarg；camera-ready 的 .pgf 文本
            # 由编译端 xelatex 接管字体，这里只钉最小 rc
            with plt.rc_context({"pgf.texsystem": "xelatex", "pgf.rcfonts": False}):
                fig.savefig(out, **kw)
        else:
            fig.savefig(out, **kw)
        saved.append(out)
    return saved
