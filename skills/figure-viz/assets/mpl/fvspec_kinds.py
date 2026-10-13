"""fvspec_kinds.py — 分组与系列准备、各 kind 绘制函数与 DRAW 分派表。"""

from __future__ import annotations

import copy as _copy
import itertools
import math
import re
import zlib
from pathlib import Path

import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from fvspec_data import (
    _draw_errbar,
    _drawn_idx,
    _drop_none,
    _edge_color,
    _err_fields,
    _err_vals,
    _filter,
    _Group,
    _legend_label,
    _map_err_cats,
    _resolve_props,
    _SeriesRec,
    _sort_xy_idx,
    _style_kwargs,
    _take_err,
    _take_rows,
    _vals,
)
from fvspec_schema import (
    _BAND_ALPHA,
    _BAR_LABEL_MODES,
    _FIELD_ZORDER,
    _KIND_ZORDER,
    _LUM_INK,
    _NEUTRAL_KINDS,
    _REQ_FIELDS,
    _UNITS,
    BAR_CONNECT_KEYS,
    BAR_LABEL_KEYS,
    PANEL_SERIES_KINDS,
    SERIES_COMMON,
    SERIES_KIND_KEYS,
    SpecError,
    _check_keys,
    _hint,
    _is_num,
    _mark,
    _norm_key,
    _obj,
    _pos_key,
)
from matplotlib import colormaps
from matplotlib.colors import TwoSlopeNorm, to_rgba
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.patches import Patch, PathPatch, Rectangle
from matplotlib.path import Path as MplPath
from matplotlib.ticker import NullLocator

# ------------------------------------------------------------------ 分组


def _group_rows(rows, by, sid):
    if by is None:
        return [_Group(None, None, rows)]
    if isinstance(by, dict):
        _check_keys(by, {"field", "order"}, f"series {sid} by")
        if "field" not in by:
            raise SpecError(f"series {sid}: 'by' needs a 'field' key")
        field_name, order = by["field"], by.get("order")
        if order is not None and not isinstance(order, list):
            raise SpecError(f"series {sid}: 'by.order' must be a list, got {order!r}")
    elif isinstance(by, str):
        field_name, order = by, None
    else:
        raise SpecError(
            f"series {sid}: 'by' must be a field name or "
            f"{{'field': ..., 'order': [...]}}, got {by!r}"
        )
    buckets, seq, raws = {}, [], {}
    for r in rows:
        raw = r.get(field_name)
        k = _norm_key(raw)
        if k not in buckets:
            buckets[k], raws[k] = [], raw
            seq.append(k)
        buckets[k].append(r)
    if order is not None:
        wanted = [_norm_key(o) for o in order]
        ordered = [k for k in wanted if k in buckets]
        ordered += [k for k in seq if k not in ordered]
    elif all(_is_num(k) or isinstance(k, bool) for k in seq):
        ordered = sorted(seq)
    else:
        ordered = seq
    return [_Group(k, raws[k], buckets[k]) for k in ordered]


def _fmt_label(spec, rec, g):
    if spec is None:
        return None
    out = None
    if isinstance(spec, dict):
        for k, v in spec.items():
            if _norm_key(k) == g.key:
                out = str(v)
                break
        if out is None:
            return None
    else:
        out = str(spec)
    val = g.raw if g.raw is not None else g.key
    if rec.by_field:
        out = out.replace("{" + rec.by_field + "}", str(val))
    out = out.replace("{v}", str(val)).replace("{n}", str(len(g.rows)))
    return out


_HIST_BIN_METHODS = {"auto", "fd", "doane", "scott", "stone", "rice", "sturges", "sqrt"}


def _check_hist_params(merged, sid):
    """hist 的 bins/range 形态校验——np.histogram 的 ValueError 提前成 SpecError。"""
    bins = merged.get("bins")
    if bins is not None:
        if isinstance(bins, str):
            ok = bins in _HIST_BIN_METHODS
        elif _is_num(bins):
            ok = float(bins).is_integer() and bins >= 1
        elif isinstance(bins, (list, tuple)):
            ok = (
                len(bins) >= 2
                and all(_is_num(b) for b in bins)
                and all(b2 > b1 for b1, b2 in itertools.pairwise(bins))
            )
        else:
            ok = False
        if not ok:
            raise SpecError(
                f"series {sid} (hist): bad bins {bins!r} — a positive "
                f"count, an estimator name {sorted(_HIST_BIN_METHODS)}, "
                f"or an increasing edge list"
            )
    rng = merged.get("range")
    if rng is not None and not (
        isinstance(rng, (list, tuple))
        and len(rng) == 2
        and all(_is_num(v) for v in rng)
        and rng[0] < rng[1]
    ):
        raise SpecError(
            f"series {sid} (hist): range must be [lo, hi] with lo < hi, got {rng!r}"
        )


def _check_dist_params(merged, rec, sid):
    """box/violin 的 positions/widths 按组数对齐；inner/fliers 形态校验。"""
    n = len(rec.groups)
    pos = merged.get("positions")
    if pos is not None and not (
        isinstance(pos, (list, tuple))
        and len(pos) == n
        and all(_is_num(p) for p in pos)
    ):
        raise SpecError(
            f"series {sid} ({rec.kind}): positions must be a list of "
            f"{n} numbers (one per group), got {pos!r}"
        )
    w = merged.get("widths")
    if w is not None and not (
        _is_num(w)
        or (isinstance(w, (list, tuple)) and len(w) == n and all(_is_num(v) for v in w))
    ):
        raise SpecError(
            f"series {sid} ({rec.kind}): widths must be a number or a "
            f"list of {n} numbers, got {w!r}"
        )
    if rec.kind == "box" and not isinstance(merged.get("fliers", True), bool):
        raise SpecError(
            f"series {sid} (box): fliers must be a bool, got {merged.get('fliers')!r}"
        )
    inner = merged.get("inner")
    if rec.kind == "violin" and inner not in (None, "points"):
        raise SpecError(f"series {sid} (violin): inner must be 'points', got {inner!r}")


_CBAR_KEYS = {"label", "props"}


def _check_field_cmap(merged, sid, kind):
    """cmap/vcenter/cbar 三件套形态校验——heat 与场族（contour/quiver）共用。"""
    cmap = merged.get("cmap", "seq")
    if not isinstance(cmap, str):
        raise SpecError(f"series {sid} ({kind}): cmap must be a string, got {cmap!r}")
    if cmap not in ("seq", "div") and cmap not in colormaps:
        raise SpecError(
            f"series {sid} ({kind}): unknown cmap {cmap!r} — built-ins "
            f"'seq' (paper→vteal) / 'div' (vcoral↔vteal) or a matplotlib "
            f"colormap name{_hint(cmap, list(colormaps))}"
        )
    vc = merged.get("vcenter")
    if vc is not None and not _is_num(vc):
        raise SpecError(f"series {sid} ({kind}): vcenter must be a number, got {vc!r}")
    cb = merged.get("cbar", True)
    if isinstance(cb, dict):
        _check_keys(cb, _CBAR_KEYS, f"series {sid} ({kind}) cbar")
        _obj(cb.get("props"), f"series {sid} ({kind}) cbar.props")
    elif not isinstance(cb, bool):
        raise SpecError(
            f"series {sid} ({kind}): cbar must be a bool or "
            f"{{label, props}}, got {cb!r}"
        )


def _field_colorbar(ax, artist, merged, ctx, lint):
    """cbar 落盘——heat 与场族共用的 {label, props} 语义。"""
    cb = merged.get("cbar", True)
    if not cb:
        return
    cb_kw, label = {}, None
    if isinstance(cb, dict):
        label = cb.get("label")
        cb_kw.update(_resolve_props(cb.get("props"), ctx, lint))
    cbar = ax.figure.colorbar(artist, ax=ax, **cb_kw)
    if label is not None:
        cbar.set_label(label)


def _check_heat_params(sspec, merged, sid):
    """heat 的形态校验：长表 {x,y,z} 列名 与 matrix 直给二选一。"""
    for f in ("of", "by", "color"):
        if f in sspec:
            raise SpecError(
                f"series {sid} (heat): {f!r} does not apply — one series "
                f"draws one mesh and 'cmap' is the color vehicle"
            )
    mat = merged.get("matrix")
    if mat is not None:
        ok = (
            isinstance(mat, (list, tuple))
            and len(mat) > 0
            and all(isinstance(r, (list, tuple)) and len(r) for r in mat)
        )
        if not ok:
            raise SpecError(
                f"series {sid} (heat): 'matrix' must be a non-empty "
                f"list of non-empty rows"
            )
        ncols = len(mat[0])
        if any(len(r) != ncols for r in mat):
            raise SpecError(
                f"series {sid} (heat): ragged 'matrix' rows "
                f"({sorted({len(r) for r in mat})})"
            )
        for r in mat:
            for v in r:
                if v is not None and not _is_num(v):
                    raise SpecError(
                        f"series {sid} (heat): 'matrix' cell {v!r} is non-numeric"
                    )
        for f in ("x", "y", "z", "from", "where"):
            if f in sspec:
                raise SpecError(
                    f"series {sid} (heat): {f!r} belongs to the long-table "
                    f"form — 'matrix' is data-free"
                )
        for name, n in (("xlabels", ncols), ("ylabels", len(mat))):
            lab = merged.get(name)
            if lab is not None and not (
                isinstance(lab, (list, tuple)) and len(lab) == n
            ):
                raise SpecError(
                    f"series {sid} (heat): {name} must be a list of "
                    f"{n} labels, got {lab!r}"
                )
    else:
        for req in ("x", "y", "z"):
            if req not in merged:
                raise SpecError(
                    f"series {sid} (heat): missing required {req!r} "
                    f"(or give 'matrix' for a literal grid)"
                )
            if not isinstance(merged[req], str):
                raise SpecError(
                    f"series {sid} (heat): {req} must name a data column "
                    f"(literal grids go through 'matrix')"
                )
        for name in ("xlabels", "ylabels"):
            lab = merged.get(name)
            if lab is not None and not isinstance(lab, (list, tuple)):
                raise SpecError(
                    f"series {sid} (heat): {name} must be a list of "
                    f"category values (order pin), got {lab!r}"
                )
    _check_field_cmap(merged, sid, "heat")
    ann = merged.get("annotate", False)
    if not (ann is True or ann is False or isinstance(ann, str)):
        raise SpecError(
            f"series {sid} (heat): annotate must be true|false|a "
            f"template like '{{v:.1f}}', got {ann!r}"
        )
    if isinstance(ann, str):
        try:
            ann.format(v=1.0)
        except Exception as e:
            raise SpecError(
                f"series {sid} (heat): bad annotate template {ann!r}: {e}"
            ) from e


_CONTOUR_MODES = ("fill", "lines", "fill+lines")
_CLABEL_KEYS = {"levels", "fmt", "fontsize", "props", "manual"}
_QUIVER_MODES = ("arrows", "stream")
_QUIVER_ARROW_KEYS = {"scale", "pivot"}
_QUIVER_STREAM_KEYS = {"density", "linewidth", "arrowsize"}
_QUIVER_PIVOTS = ("tail", "middle", "mid", "tip")


def _check_contour_params(sspec, merged, sid):
    """contour 的形态校验：长表 {x,y,z} 与 matrix 直给二选一（同 heat）。
    matrix 的 xlabels/ylabels 两口径：全数值 → 单调坐标轴；非数值 →
    类别标签（须互异可哈希），按位等距映射 0..n-1 并写回原串刻度。"""
    for f in ("of", "by", "color"):
        if f in sspec:
            raise SpecError(
                f"series {sid} (contour): {f!r} does not apply — one series "
                f"draws one field and 'cmap' is the color vehicle"
            )
    mat = merged.get("matrix")
    if mat is not None:
        ok = (
            isinstance(mat, (list, tuple))
            and len(mat) > 0
            and all(isinstance(r, (list, tuple)) and len(r) for r in mat)
        )
        if not ok:
            raise SpecError(
                f"series {sid} (contour): 'matrix' must be a non-empty "
                f"list of non-empty rows"
            )
        ncols = len(mat[0])
        if any(len(r) != ncols for r in mat):
            raise SpecError(
                f"series {sid} (contour): ragged 'matrix' rows "
                f"({sorted({len(r) for r in mat})})"
            )
        for r in mat:
            for v in r:
                if v is not None and not _is_num(v):
                    raise SpecError(
                        f"series {sid} (contour): 'matrix' cell {v!r} is non-numeric"
                    )
        for f in ("x", "y", "z", "from", "where"):
            if f in sspec:
                raise SpecError(
                    f"series {sid} (contour): {f!r} belongs to the long-table "
                    f"form — 'matrix' is data-free"
                )
        for name, n in (("xlabels", ncols), ("ylabels", len(mat))):
            lab = merged.get(name)
            if lab is None:
                continue
            if not (isinstance(lab, (list, tuple)) and len(lab) == n):
                raise SpecError(
                    f"series {sid} (contour): {name} must be a list of "
                    f"{n} entries, got {lab!r}"
                )
            if all(_is_num(v) for v in lab):
                # 数值坐标轴：contour 内核按真实坐标插值，乱序坐标没有语义
                if not (
                    all(b > a for a, b in itertools.pairwise(lab))
                    or all(b < a for a, b in itertools.pairwise(lab))
                ):
                    raise SpecError(
                        f"series {sid} (contour): numeric {name} must be "
                        f"monotonic coordinates, got {lab!r}"
                    )
            else:
                # 类别标签：按位等距映射 0..n-1——值须可哈希且互异，
                # 否则槽位映射歧义
                try:
                    uniq = len(set(lab)) == len(lab)
                except TypeError:
                    uniq = False
                if not uniq:
                    raise SpecError(
                        f"series {sid} (contour): categorical {name} must "
                        f"be hashable and distinct, got {lab!r}"
                    )
    else:
        for req in ("x", "y", "z"):
            if req not in merged:
                raise SpecError(
                    f"series {sid} (contour): missing required {req!r} "
                    f"(or give 'matrix' for a literal grid)"
                )
            if not isinstance(merged[req], str):
                raise SpecError(
                    f"series {sid} (contour): {req} must name a data column "
                    f"(literal grids go through 'matrix')"
                )
        for name in ("xlabels", "ylabels"):
            if name in sspec:
                raise SpecError(
                    f"series {sid} (contour): {name!r} belongs to the "
                    f"'matrix' form — long-table coordinates sort numerically"
                )
    _check_field_cmap(merged, sid, "contour")
    lv = merged.get("levels")
    if lv is not None:
        if isinstance(lv, str):
            ok = lv == "log"
        elif _is_num(lv):
            ok = float(lv).is_integer() and lv >= 2
        elif isinstance(lv, dict):
            n = lv.get("log")
            ok = set(lv) == {"log"} and _is_num(n) and float(n).is_integer() and n >= 2
        elif isinstance(lv, (list, tuple)):
            ok = (
                len(lv) >= 2
                and all(_is_num(v) for v in lv)
                and all(b > a for a, b in itertools.pairwise(lv))
            )
        else:
            ok = False
        if not ok:
            raise SpecError(
                f"series {sid} (contour): levels must be an int >= 2, an "
                f"increasing array, 'log' or {{'log': n}}, got {lv!r}"
            )
    mode = merged.get("mode", "fill")
    if mode not in _CONTOUR_MODES:
        raise SpecError(
            f"series {sid} (contour): mode must be one of {_CONTOUR_MODES}, "
            f"got {mode!r}"
        )
    cl = merged.get("clabel")
    if cl is not None and cl is not False:
        if mode == "fill":
            raise SpecError(
                f"series {sid} (contour): clabel labels contour lines — "
                f"set mode:'fill+lines' (or 'lines')"
            )
        if cl is not True:
            c = _obj(cl, f"series {sid} (contour) clabel")
            _check_keys(c, _CLABEL_KEYS, f"series {sid} (contour) clabel")
            sub = c.get("levels", "all")
            ok = (
                sub == "all"
                or (_is_num(sub) and float(sub).is_integer() and sub >= 1)
                or (
                    isinstance(sub, (list, tuple))
                    and len(sub) >= 1
                    and all(_is_num(v) for v in sub)
                )
            )
            if not ok:
                raise SpecError(
                    f"series {sid} (contour): clabel.levels must be 'all', "
                    f"an int stride >= 1 or a level list, got {sub!r}"
                )
            fmt = c.get("fmt")
            if fmt is not None and not isinstance(fmt, (str, dict)):
                raise SpecError(
                    f"series {sid} (contour): clabel.fmt must be a mpl fmt "
                    f"string, a '{{v:...}}' template or a {{level: label}} "
                    f"dict, got {fmt!r}"
                )
            fs = c.get("fontsize")
            if fs is not None and not (_is_num(fs) and fs > 0):
                raise SpecError(
                    f"series {sid} (contour): clabel.fontsize must be a "
                    f"positive number, got {fs!r}"
                )
            man = c.get("manual")
            if man is not None:
                if "levels" in c:
                    raise SpecError(
                        f"series {sid} (contour): clabel 'manual' and "
                        f"'levels' are mutually exclusive — manual pins "
                        f"label spots for all drawn levels"
                    )
                ok = (
                    isinstance(man, (list, tuple))
                    and len(man) > 0
                    and all(
                        isinstance(p, (list, tuple))
                        and len(p) == 2
                        and all(_is_num(v) for v in p)
                        for p in man
                    )
                )
                if not ok:
                    raise SpecError(
                        f"series {sid} (contour): clabel.manual must be a "
                        f"non-empty list of [x, y] data coords, got {man!r}"
                    )
            _obj(c.get("props"), f"series {sid} (contour) clabel.props")


def _check_quiver_params(sspec, merged, sid):
    """quiver 的形态校验：{x,y,u,v[,m]} 长表，mode 分流派字段互斥。"""
    for f in ("of", "by"):
        if f in sspec:
            raise SpecError(
                f"series {sid} (quiver): {f!r} does not apply — one series "
                f"draws one vector field"
            )
    mode = merged.get("mode", "arrows")
    if mode not in _QUIVER_MODES:
        raise SpecError(
            f"series {sid} (quiver): mode must be one of {_QUIVER_MODES}, got {mode!r}"
        )
    for req in ("x", "y", "u", "v"):
        if req not in merged:
            raise SpecError(f"series {sid} (quiver): missing required {req!r}")
        if not isinstance(merged[req], str):
            raise SpecError(f"series {sid} (quiver): {req} must name a data column")
    m = merged.get("m")
    if m is not None and not isinstance(m, str):
        raise SpecError(
            f"series {sid} (quiver): 'm' must name a data column, got {m!r}"
        )
    if m is not None:
        if "color" in sspec:
            raise SpecError(
                f"series {sid} (quiver): 'color' does not apply — 'm' maps "
                f"magnitudes through 'cmap'"
            )
        _check_field_cmap(merged, sid, "quiver")
    else:
        for f in ("cmap", "vcenter", "cbar"):
            if f in sspec:
                raise SpecError(
                    f"series {sid} (quiver): {f!r} needs 'm' — a magnitude "
                    f"column is the cmap vehicle"
                )
    other = _QUIVER_STREAM_KEYS if mode == "arrows" else _QUIVER_ARROW_KEYS
    want = "stream" if mode == "arrows" else "arrows"
    for f in sorted(set(sspec) & other):
        raise SpecError(
            f"series {sid} (quiver): {f!r} applies to mode:{want!r}, got mode:{mode!r}"
        )
    sc = merged.get("scale")
    if sc is not None and not (_is_num(sc) and sc > 0):
        raise SpecError(
            f"series {sid} (quiver): scale must be a positive number, got {sc!r}"
        )
    pv = merged.get("pivot")
    if pv is not None and pv not in _QUIVER_PIVOTS:
        raise SpecError(
            f"series {sid} (quiver): pivot must be one of {_QUIVER_PIVOTS}, got {pv!r}"
        )
    den = merged.get("density")
    if den is not None and not (
        (_is_num(den) and den > 0)
        or (
            isinstance(den, (list, tuple))
            and len(den) == 2
            and all(_is_num(v) and v > 0 for v in den)
        )
    ):
        raise SpecError(
            f"series {sid} (quiver): density must be a positive number or "
            f"[dx, dy], got {den!r}"
        )
    for f in ("linewidth", "arrowsize"):
        v = merged.get(f)
        if v is not None and not (_is_num(v) and v > 0):
            raise SpecError(
                f"series {sid} (quiver): {f} must be a positive number, got {v!r}"
            )


_IMAGE_FORMS = ("file", "path", "rgb")
_BADGE_CORNERS = {"bl", "br", "tl", "tr"}


def _check_image_params(sspec, merged, sid):
    """image 的形态校验：file（列名，格值为路径或数组）/ path（字面文件）
    / rgb（字面数组）三选一互斥；'file' 挂数据集，其余两个数据自由。
    badge 只长在 'file' 形上（读行字段），extent 三形通用。"""
    for f in ("of", "by", "color"):
        if f in sspec:
            raise SpecError(
                f"series {sid} (image): {f!r} does not apply — one series "
                f"draws one image per row"
            )
    forms = [f for f in _IMAGE_FORMS if f in merged]
    if not forms:
        raise SpecError(
            f"series {sid} (image): missing source — one of 'file' "
            f"(data column of paths/arrays), 'path' (literal file), "
            f"'rgb' (literal array)"
        )
    if len(forms) > 1:
        raise SpecError(
            f"series {sid} (image): sources {forms} are mutually "
            f"exclusive — pick one of {_IMAGE_FORMS}"
        )
    form = forms[0]
    if form == "file":
        if not isinstance(merged["file"], str):
            raise SpecError(
                f"series {sid} (image): 'file' must name a data column "
                f"whose cells are file paths or arrays"
            )
    else:
        for f in ("from", "where"):
            if f in sspec:
                raise SpecError(
                    f"series {sid} (image): {f!r} belongs to the 'file' "
                    f"form — 'path'/'rgb' are data-free"
                )
        if form == "path":
            if not isinstance(merged["path"], str):
                raise SpecError(
                    f"series {sid} (image): 'path' must be a file path string"
                )
        else:
            rgb = merged["rgb"]
            arr = (
                np.asarray(rgb) if isinstance(rgb, (list, tuple, np.ndarray)) else None
            )
            if arr is None or arr.ndim not in (2, 3):
                raise SpecError(
                    f"series {sid} (image): 'rgb' must be a 2-D or 3-D "
                    f"array (H×W gray / H×W×3|4 rgb-a), got "
                    f"{type(rgb).__name__ if arr is None else arr.shape}"
                )
            if arr.ndim == 3:
                if arr.shape[2] not in (3, 4):
                    raise SpecError(
                        f"series {sid} (image): 'rgb' needs 3 or 4 "
                        f"channels, got shape {arr.shape}"
                    )
                for f in ("cmap", "vcenter", "cbar"):
                    if f in sspec:
                        raise SpecError(
                            f"series {sid} (image): {f!r} needs a scalar "
                            f"field — RGB arrays carry their own colors"
                        )
    ex = merged.get("extent")
    if ex is not None:
        ok = (
            isinstance(ex, (list, tuple))
            and len(ex) == 4
            and all(_is_num(v) for v in ex)
        )
        if not ok:
            raise SpecError(
                f"series {sid} (image): 'extent' must be [left, right, "
                f"bottom, top] of numbers, got {ex!r}"
            )
    badge = merged.get("badge")
    if badge is not None:
        if form != "file":
            raise SpecError(
                f"series {sid} (image): 'badge' needs data rows — it reads "
                f"per-row fields and only applies to the 'file' form"
            )
        _check_keys(badge, {"field", "fmt", "corner"}, f"series {sid} (image) badge")
        if not isinstance(badge.get("field"), str):
            raise SpecError(
                f"series {sid} (image): badge.field must name a data column"
            )
        fmt = badge.get("fmt", "{v:.3g}")
        if not isinstance(fmt, str):
            raise SpecError(
                f"series {sid} (image): badge.fmt must be a '{{v:...}}' "
                f"template, got {fmt!r}"
            )
        try:
            fmt.format(v=1.0)
        except Exception as e:
            raise SpecError(f"series {sid} (image): bad badge.fmt {fmt!r}: {e}") from e
        corner = badge.get("corner", "bl")
        if corner not in _BADGE_CORNERS:
            raise SpecError(
                f"series {sid} (image): badge.corner must be one of "
                f"{sorted(_BADGE_CORNERS)}, got {corner!r}"
            )
    _check_field_cmap(merged, sid, "image")


_SANKEY_NODE_KEYS = {"id", "stage", "label", "order", "color"}
_SANKEY_LABEL_KEYS = {"template", "vfmt", "fontsize"}
# 不适用 sankey 的 SERIES_COMMON 键：分组/图例/误差棒/样式对整张
# 流向图没有语义——响亮拒绝而非静默吞掉
_SANKEY_DEAD_KEYS = (
    "of",
    "by",
    "axis",
    "legend",
    "label",
    "sort_x",
    "errprops",
    "marker",
    "ls",
    "lw",
    "ms",
    "mew",
    "draw",
)


def _check_sankey_params(sspec, merged, sid):
    """sankey 的形态校验：长表 x/y/z = src/dst/value 三列（heat 同口径）
    与 flows 字面行 [{source,target,value}] 二选一；nodes 表与布局参数
    的形状；行级节点校验在 _sankey_node_rows（dataset 与字面行同口径）。"""
    for f in _SANKEY_DEAD_KEYS:
        if f in sspec:
            raise SpecError(
                f"series {sid} (sankey): {f!r} does not apply — one "
                f"series draws the whole flow diagram"
            )
    d = merged.get("dir", "h")
    if d not in ("h", "v"):
        raise SpecError(
            f"series {sid} (sankey): dir must be 'h' (columns left→right) "
            f"or 'v' (rows top→down), got {d!r}"
        )
    lit = merged.get("flows")
    if lit is not None:
        if not (
            isinstance(lit, (list, tuple))
            and lit
            and all(isinstance(fr, dict) for fr in lit)
        ):
            raise SpecError(
                f"series {sid} (sankey): 'flows' must be a non-empty list "
                f"of {{source, target, value}} objects, got {lit!r}"
            )
        for i, fr in enumerate(lit):
            miss = [k for k in ("source", "target", "value") if fr.get(k) is None]
            if miss:
                raise SpecError(
                    f"series {sid} (sankey): flows[{i}] is missing {miss} — "
                    f"every flow declares {{source, target, value}}"
                )
        for f in ("x", "y", "z", "from", "where"):
            if f in sspec:
                raise SpecError(
                    f"series {sid} (sankey): {f!r} belongs to the long-table "
                    f"form — 'flows' is data-free"
                )
    else:
        for req in ("x", "y", "z"):
            if req not in merged:
                raise SpecError(
                    f"series {sid} (sankey): missing required {req!r} "
                    f"(or give 'flows' for literal flow rows)"
                )
    nodes = merged.get("nodes")
    if nodes is not None and not isinstance(nodes, (str, list, tuple)):
        raise SpecError(
            f"series {sid} (sankey): 'nodes' must be a dataset name or a "
            f"list of node rows, got {nodes!r}"
        )
    gap = merged.get("gap", 0.05)
    if not (_is_num(gap) and gap >= 0):
        raise SpecError(
            f"series {sid} (sankey): gap must be a non-negative fraction "
            f"of the tallest column, got {gap!r}"
        )
    w = merged.get("width", 0.18)
    if not (_is_num(w) and 0 < w < 1):
        raise SpecError(
            f"series {sid} (sankey): width must be a fraction of column "
            f"spacing in (0, 1), got {w!r}"
        )
    pad = merged.get("pad", 0.05)
    if not (_is_num(pad) and pad >= 0):
        raise SpecError(f"series {sid} (sankey): pad must be >= 0, got {pad!r}")
    lab = merged.get("labels", True)
    if isinstance(lab, dict):
        _check_keys(lab, _SANKEY_LABEL_KEYS, f"series {sid} (sankey) labels")
        for k in ("template", "vfmt"):
            if k in lab and not isinstance(lab[k], str):
                raise SpecError(
                    f"series {sid} (sankey): labels.{k} must be a string, "
                    f"got {lab[k]!r}"
                )
        if "fontsize" in lab and not _is_num(lab["fontsize"]):
            raise SpecError(
                f"series {sid} (sankey): labels.fontsize must be a number, "
                f"got {lab['fontsize']!r}"
            )
        try:
            lab.get("template", "{l}").format(l="", id="", v="", value=0)
            lab.get("vfmt", "{:g}").format(1.0)
        except Exception as e:
            raise SpecError(
                f"series {sid} (sankey): bad labels template/vfmt: {e}"
            ) from e
    elif not (lab is True or lab is False or isinstance(lab, str)):
        raise SpecError(
            f"series {sid} (sankey): labels must be true|false|a "
            f"template|{{template, vfmt, fontsize}}, got {lab!r}"
        )
    heads = merged.get("heads")
    if heads is not None and not (
        (isinstance(heads, (list, tuple)) and all(isinstance(h, str) for h in heads))
        or (isinstance(heads, dict) and all(isinstance(v, str) for v in heads.values()))
    ):
        raise SpecError(
            f"series {sid} (sankey): heads must be a list of column "
            f"labels or a {{stage: label}} dict, got {heads!r}"
        )


# 不适用 sig 的 SERIES_COMMON 键：括号是中性注释层——分组/图例/逐点样式
# 字段没有语义，响亮拒绝而非静默吞掉（'color'/'alpha'/'zorder'/'props'
# 仍是合法的 ink 覆写口，'axis' 允许挂 y2）
_SIG_DEAD_KEYS = (
    "of",
    "by",
    "legend",
    "label",
    "sort_x",
    "errprops",
    "marker",
    "ls",
    "lw",
    "ms",
    "mew",
    "draw",
)


def _check_sig_params(sspec, merged, sid):
    """sig 的系列级形态校验：死键 + tick/pad 非负数据单位数 + textprops 对象。"""
    for f in _SIG_DEAD_KEYS:
        if f in sspec:
            raise SpecError(
                f"series {sid} (sig): {f!r} does not apply — sig brackets "
                f"are neutral annotations; each row declares one bracket "
                f"{{a, b, y, p|text}}"
            )
    for k in ("tick", "pad"):
        v = merged.get(k)
        if v is not None and not (_is_num(v) and v >= 0):
            raise SpecError(
                f"series {sid} (sig): {k} must be a non-negative number "
                f"in data units, got {v!r}"
            )
    _obj(merged.get("textprops"), f"series {sid} (sig) textprops")


def _check_sig_rows(rows, sid):
    """sig 的行级形态校验：每行一条括号 {a, b, y} + 'p'|'text' 恰一。
    a/b 收数值坐标、类别名或 '槽位:组值' 复合形（类别表与 dodge 几何在
    draw 时从同面板 bar/box/violin 推导）。"""
    for i, r in enumerate(rows):
        miss = [k for k in ("a", "b", "y") if r.get(k) is None]
        if miss:
            raise SpecError(
                f"series {sid} (sig): row {i} is missing {miss} — every "
                f"row declares one bracket {{a, b, y}} plus 'p' or 'text'"
            )
        for k in ("a", "b"):
            if not (_is_num(r[k]) or isinstance(r[k], str)):
                raise SpecError(
                    f"series {sid} (sig): row {i} {k!r} must be a numeric "
                    f"x coordinate or a category name, got {r[k]!r}"
                )
        if not _is_num(r["y"]):
            raise SpecError(
                f"series {sid} (sig): row {i} 'y' must be a number in "
                f"data units, got {r['y']!r}"
            )
        has_p, has_t = r.get("p") is not None, r.get("text") is not None
        if has_p == has_t:
            raise SpecError(
                f"series {sid} (sig): row {i} needs exactly one of 'p' "
                f"(p-value → stars) or 'text' (literal label)"
            )
        if has_p and not _is_num(r["p"]):
            raise SpecError(
                f"series {sid} (sig): row {i} 'p' must be a number, got {r['p']!r}"
            )
        if has_t and not isinstance(r["text"], str):
            raise SpecError(
                f"series {sid} (sig): row {i} 'text' must be a string, "
                f"got {r['text']!r}"
            )


def _series_dataset(merged, panel, ctx, sid):
    name = merged.get("from") or panel.get("from")
    if name is None:
        if len(ctx.data) == 1:
            return next(iter(ctx.data))
        raise SpecError(f"series {sid}: no 'from' and data is ambiguous")
    if name not in ctx.data:
        raise SpecError(
            f"series {sid}: unknown dataset {name!r} "
            f"(have {sorted(ctx.data)}){_hint(name, ctx.data)}"
        )
    return name


def _prepare_series(sspec, panel, pid, ctx, auto_idx):
    sid = sspec.get("id") or f"{pid}s{auto_idx}"
    if sid in ctx.records:
        raise SpecError(f"series {sid}: duplicate series id {sid!r}")
    kind = sspec.get("kind")
    if kind not in SERIES_KIND_KEYS:
        raise SpecError(
            f"series {sid}: unknown kind {kind!r}"
            f"{_hint(kind, SERIES_KIND_KEYS)}; supported: "
            f"{sorted(SERIES_KIND_KEYS)}"
        )
    _check_keys(sspec, SERIES_COMMON | SERIES_KIND_KEYS[kind], f"series {sid} ({kind})")
    pkind = panel.get("kind", "xy")
    if kind not in PANEL_SERIES_KINDS[pkind]:
        raise SpecError(f"series {sid}: kind {kind!r} not allowed in {pkind!r} panel")
    axis = sspec.get("axis", "y")
    if axis not in ("y", "y2"):
        raise SpecError(f"series {sid}: axis must be 'y' or 'y2'")
    y2_declared = (
        pkind == "xy" and panel.get("y2") is not None and panel.get("y2") is not False
    )
    if axis == "y2" and not y2_declared:
        raise SpecError(
            f"series {sid}: axis 'y2' needs panel {pid!r} to declare a "
            f"'y2' axis config (xy panels only)"
        )
    if pkind == "radar" and (
        sspec.get("xerr") is not None or sspec.get("yerr") is not None
    ):
        raise SpecError(f"series {sid}: xerr/yerr unsupported on radar panels")

    rec = _SeriesRec(sspec, sid)
    merged = dict(sspec)
    parent = None
    if "of" in sspec:
        parent = ctx.records.get(sspec["of"])
        if parent is None:
            raise SpecError(
                f"series {sid}: 'of' refers to unknown series {sspec['of']!r}"
            )
        for k in ("from", "where", "by", "x"):
            if k not in merged and k in parent.merged:
                merged[k] = parent.merged[k]
        rec.parent = parent

    if kind in ("line", "scatter", "bar", "donut"):
        for req in ("x", "y"):
            if req not in merged:
                raise SpecError(f"series {sid} ({kind}): missing required {req!r}")
    if kind == "pred" and "y" not in merged:
        raise SpecError(f"series {sid} (pred): missing required 'y'")
    if kind in ("hist", "ecdf", "kde") and "x" not in merged:
        raise SpecError(f"series {sid} ({kind}): missing required 'x'")
    if kind in ("box", "violin") and "y" not in merged:
        raise SpecError(f"series {sid} ({kind}): missing required 'y'")
    if kind == "band" and not {"lo", "hi"} <= set(merged):
        raise SpecError(f"series {sid} (band): needs 'lo' and 'hi'")
    # dir 枚举校验：此前任意非 'v' 值被静默当横/竖画（dir:'diag' 变 axhline）；
    # 分布图族 dir:'h' = mpl orientation 同义（横向边际），sankey 的 dir
    # 在 _check_sankey_params 自查
    if kind in ("ref", "span", "bar", "hist", "ecdf", "kde", "box", "violin"):
        d = merged.get("dir")
        valid = ("h", "v", "diag", "identity") if kind == "ref" else ("h", "v")
        if d is not None and d not in valid:
            raise SpecError(
                f"series {sid} ({kind}): dir must be one of {valid}, got {d!r}"
            )
    # 浮动柱 bottom 列与 stack 互斥：堆叠自己累加基线，逐行底边会与之矛盾
    if kind == "bar":
        if merged.get("stack") and merged.get("bottom") is not None:
            raise SpecError(
                f"series {sid} (bar): 'bottom' and 'stack' are mutually "
                f"exclusive — stacked bars accumulate their own bases"
            )
        bs = merged.get("bottom")
        if bs is not None and not (
            isinstance(bs, str) or _is_num(bs) or isinstance(bs, (list, tuple))
        ):
            raise SpecError(
                f"series {sid} (bar): 'bottom' must be a column name, "
                f"number or literal list, got {bs!r}"
            )
    ref_diag = kind == "ref" and merged.get("dir") in ("diag", "identity")
    if ref_diag and pkind == "radar":
        raise SpecError(f"series {sid} (ref): dir:{merged['dir']} unsupported on radar")
    if kind in ("ref", "span", "note") and "at" not in merged and not ref_diag:
        raise SpecError(f"series {sid} ({kind}): missing required 'at'")
    if kind == "note":
        if "text" not in merged:
            raise SpecError(f"series {sid} (note): missing required 'text'")
        at_d = merged.get("at")
        if isinstance(at_d, dict):
            _check_keys(at_d, {"x", "y"}, f"series {sid} (note) at")
            if "x" not in at_d or "y" not in at_d:
                raise SpecError(f"series {sid} (note): at dict needs both 'x' and 'y'")
            if pkind == "radar":
                raise SpecError(
                    f"series {sid} (note): row fan-out 'at' unsupported on radar"
                )
    if kind == "heat":
        _check_heat_params(sspec, merged, sid)
    if kind == "contour":
        _check_contour_params(sspec, merged, sid)
    if kind == "quiver":
        _check_quiver_params(sspec, merged, sid)
    if kind == "image":
        _check_image_params(sspec, merged, sid)
    if kind == "sankey":
        _check_sankey_params(sspec, merged, sid)
    if kind == "sig":
        _check_sig_params(sspec, merged, sid)
    if kind == "pred" and parent is None:
        raise SpecError(f"series {sid} ({kind}): requires 'of':<parent-id>")
    # band 无父 = 独立 fill_between 区间（x/lo/hi 全自备），不再强制挂父线
    if kind == "band" and parent is None and "x" not in merged:
        raise SpecError(f"series {sid} (band): without 'of' it needs an own 'x' column")
    if kind == "donut":
        if merged.get("by") is not None:
            raise SpecError(
                f"series {sid} (donut): 'by' does not apply — slices are "
                f"per-row, not per-group"
            )
        lab = merged.get("labels", True)
        if lab not in (True, False, "legend"):
            raise SpecError(f"series {sid} (donut): labels must be true|false|'legend'")

    ds_name = None
    panel_only_where = set()  # 仅来自 panel.where 下发的字段（lint 溯源用）
    # radar v-ref/span 的 at 可以是 dim 名（角度位置），不是数据列
    at = merged.get("at")
    dim_at = (
        pkind == "radar" and isinstance(at, str) and at in (panel.get("dims") or [])
    )
    # 'matrix' 直给的 heat/contour、'path'/'rgb' 直给的 image 与 'flows'
    # 直给的 sankey 是数据自由系列（from/where/by 已被 kind 校验拒掉）
    needs_data = (
        (
            kind not in _NEUTRAL_KINDS
            and not (kind in ("heat", "contour") and "matrix" in merged)
            and not (kind == "image" and ("path" in merged or "rgb" in merged))
            and not (kind == "sankey" and "flows" in merged)
        )
        or "of" in merged
        or "by" in merged
        or "from" in merged
        or (isinstance(at, (str, dict)) and not dim_at)
    )
    where = dict(_obj(merged.get("where"), f"series {sid} where"))
    _obj(merged.get("props"), f"series {sid} props")
    _obj(merged.get("errprops"), f"series {sid} errprops")
    if needs_data:
        # panel.where 只下发给消费数据的系列——中性 kind（note 等不读行
        # 的）继承下去只会撞 'need a data source' 误报；panel.from 同理，
        # 它本来也只在 _series_dataset 里被需要数据的系列读取
        pwhere = dict(_obj(panel.get("where"), f"panel {pid} where"))
        panel_only_where = set(pwhere) - set(where)
        pwhere.update(where)
        where = pwhere
        ds_name = _series_dataset(merged, panel, ctx, sid)
        rows = _filter(ctx.data[ds_name], where)
    elif where:
        raise SpecError(
            f"series {sid} ({kind}): 'where'/'from' need a data source — "
            f"kind {kind!r} consumes no rows; drop 'where' or give the "
            f"series a 'from'"
        )
    else:
        rows = []
    if needs_data and not rows:
        ctx.lint("empty-series", f"series {sid} matched 0 rows", pid)

    by = merged.get("by")
    rec.by_field = by.get("field") if isinstance(by, dict) else by
    rec.groups = _group_rows(rows, by, sid)
    rec.merged = merged
    # 分布图族参数形态校验（positions/widths 需先分组才知道组数）
    if kind == "hist":
        _check_hist_params(merged, sid)
    if kind == "kde":
        _check_kde_params(merged, sid)
    if kind in ("box", "violin"):
        _check_dist_params(merged, rec, sid)
    # scatter 类别坐标：非数值 x/y 在绘制期经 _cat_map 解析到同面板
    # 类别轴槽位（无建立者/未知名响亮报错）；radar 面板类别 y 无声义——
    # 提前响亮拒绝而不是让排序崩在 TypeError
    if kind == "scatter":
        yvals = [
            v
            for g in rec.groups
            for v in _vals(g.rows, merged.get("y"), "y", sid)
            if v is not None
        ]
        if any(not _is_num(v) for v in yvals) and pkind == "radar":
            raise SpecError(
                f"series {sid} (scatter): radar y must be numeric, "
                f"got categorical values"
            )
        jit = merged.get("jitter")
        if jit is not None:
            if pkind == "radar":
                raise SpecError(f"series {sid} (scatter): jitter unsupported on radar")
            _check_jitter(jit, sid)
    # bar 数值 x：x 列全数值 → 柱落真实坐标（校准图分箱中心等），
    # 刻度/宽度按数据单位；混合非数值维持类别槽位
    if kind == "bar":
        xvals = [r.get(merged.get("x")) for g in rec.groups for r in g.rows]
        xvals = [v for v in xvals if v is not None]
        rec.num_x = bool(xvals) and all(_is_num(v) for v in xvals)
    # contour matrix 类别标签：非数值 xlabels/ylabels 按位等距映射槽位
    # ——cat_x/cat_y 置位让 _apply_axis 把 ticks/scale 当 kind 层所有物告警
    if kind == "contour" and "matrix" in merged:
        xl, yl = merged.get("xlabels"), merged.get("ylabels")
        if xl is not None and not all(_is_num(v) for v in xl):
            rec.cat_x = True
        if yl is not None and not all(_is_num(v) for v in yl):
            rec.cat_y = True
    # sig 的行级形态校验在分组后做（where 过滤后才见得到行）；
    # 每行一条括号，{a,b,y} + 'p'|'text' 恰一
    if kind == "sig":
        _check_sig_rows([r for g in rec.groups for r in g.rows], sid)

    lint = ctx.lint_proxy(pid)
    # unknown-field：by/err 等引用了数据集中整列缺失的字段——此前静默
    # （by 拼错→全部行挤进 None 组）
    # where-field-missing：where 引用字段整列缺席——panel.where 广播到异构
    # dataset 时「这个系列被滤空」的直接病因，独立 lint 名可单独抑制
    # missing-rows：必需列（x/y/lo/hi）在部分行缺值——绘制时被丢弃的行数
    # 提前按行计数告警；整列缺失已由 unknown-field / _vals SpecError 覆盖
    if needs_data and ds_name is not None:
        ds_rows = ctx.data[ds_name]
        keyset = {k for r in ds_rows for k in r}
        refs = (
            {rec.by_field}
            | set(_err_fields(merged.get("xerr")))
            | set(_err_fields(merged.get("yerr")))
        )
        if isinstance(merged.get("bottom"), str):
            refs.add(merged["bottom"])
        if kind == "note" and isinstance(at, dict):
            refs |= {v for v in (at.get("x"), at.get("y")) if isinstance(v, str)}
        if kind == "image":
            if isinstance(merged.get("file"), str):
                refs.add(merged["file"])
            bd = merged.get("badge")
            if isinstance(bd, dict) and isinstance(bd.get("field"), str):
                refs.add(bd["field"])
        for f in sorted(f for f in refs if isinstance(f, str)):
            if keyset and f not in keyset and (pid, ds_name, f) not in ctx._uf_seen:
                ctx._uf_seen.add((pid, ds_name, f))
                lint(
                    "unknown-field",
                    f"series {sid}: field {f!r} absent from every row of "
                    f"dataset {ds_name!r}{_hint(f, keyset)}",
                )
        for f in sorted(f for f in where if isinstance(f, str)):
            if keyset and f not in keyset:
                src = "panel.where" if f in panel_only_where else "where"
                lint(
                    "where-field-missing",
                    f"series {sid}: {src} references field {f!r} absent from "
                    f"dataset {ds_name!r}{_hint(f, keyset)} — the clause "
                    f"filters out every row",
                )
        need = [
            merged.get(f)
            for f in _REQ_FIELDS.get(kind, ())
            if isinstance(merged.get(f), str) and merged.get(f) in keyset
        ]
        if need:
            miss = sum(
                1
                for g in rec.groups
                for r in g.rows
                if any(r.get(c) is None for c in need)
            )
            total = sum(len(g.rows) for g in rec.groups)
            if miss:
                lint(
                    "missing-rows",
                    f"series {sid}: {miss} of {total} rows carry missing "
                    f"values in required fields {need} (dropped at draw)",
                )

    # donut 逐切片在绘制时定色；跳过组样式
    if kind == "donut":
        ctx.records[sid] = rec
        return rec
    # sankey 逐流在绘制时定色；跳过组样式
    if kind == "sankey":
        ctx.records[sid] = rec
        return rec
    # sig 是中性注释层：ink 在 draw 时解析（'color' 收 token），分组样式/
    # 图例标签不适用——跳过 group styling（by 已是死键，恒单组）
    if kind == "sig":
        ctx.records[sid] = rec
        return rec

    cspec = merged.get("color")
    if cspec is None and parent is not None:
        cspec = "parent"
    markers = merged.get("marker")
    theme_marks = fv.series_markers(ctx.theme_name, len(rec.groups))
    lint = ctx.lint_proxy(pid)
    for gi, g in enumerate(rec.groups):
        # --- 颜色 ---
        if parent is not None and (
            cspec == "parent" or (isinstance(cspec, tuple) and cspec[0] == "parent")
        ):
            pg = parent.group(g.key)
            g.color = pg.color if pg else None
            if g.color is None:
                raise SpecError(
                    f"series {sid}: group {g.key!r} absent in parent "
                    f"{parent.id}; cannot inherit color"
                )
        elif cspec is None:
            if kind in _NEUTRAL_KINDS and by is None:
                g.color = None  # 中性默认色由绘制器定
            else:
                if len(rec.groups) > len(ctx.colors.palette):
                    raise SpecError(
                        f"series {sid}: {len(rec.groups)} groups exceed "
                        f"palette size {len(ctx.colors.palette)}; give "
                        f"explicit colors via a registry"
                    )
                g.color = ctx.colors.palette_at(gi)
        else:
            c = ctx.colors.resolve(cspec, lint, group=g.key, rows=g.rows)
            if isinstance(c, list):
                uniq = list(dict.fromkeys(c))
                if kind == "scatter":
                    g.color = c  # 逐行颜色数组
                elif len(uniq) == 1:
                    g.color = uniq[0]
                else:
                    raise SpecError(
                        f"series {sid}: field-resolved color not unique "
                        f"within group {g.key!r}: {uniq}"
                    )
            elif isinstance(c, tuple) and c[0] == "parent":
                pg = parent.group(g.key) if parent else None
                g.color = pg.color if pg else None
            else:
                g.color = c
        # --- marker: str | 'by'（主题轮转）| {key: marker} | None ---
        if markers == "by":
            g.marker = theme_marks[gi]
        elif isinstance(markers, dict):
            g.marker = None
            for k, v in markers.items():
                if _norm_key(k) == g.key:
                    g.marker = v
                    break
        else:
            g.marker = markers
        g.label = _fmt_label(merged.get("label"), rec, g)

    # --- 语义 lint（warn 级，audit_ignore / audit.ignore 可豁免）---
    # markers-on-dense-line：marker 点在 >50 个顶点上糊成一片，不再是编码
    if kind == "line":
        dense = 0
        for g in rec.groups:
            if g.marker is None:
                continue
            idx = _drawn_idx(
                _vals(g.rows, merged.get("x"), "x", sid),
                _vals(g.rows, merged.get("y"), "y", sid),
            )
            dense = max(dense, len(idx))
        if dense > 50:
            lint(
                "markers-on-dense-line",
                f"series {sid}: {dense} points drawn with markers — "
                f"past ~50 points markers smear into texture; drop "
                f"'marker' or thin the data",
            )
    # bar-count：未分组柱子 >12 根是一面同形墙，类别间无从比较
    # （数值 x 的柱是直方/校准图形态，类别墙语义不适用）
    if (
        kind == "bar"
        and len(rec.groups) == 1
        and not merged.get("stack")
        and not rec.num_x
    ):
        cats = []
        for g in rec.groups:
            for r in g.rows:
                v = r.get(merged.get("x"))
                if v is not None and v not in cats:
                    cats.append(v)
        if len(cats) > 12:
            lint(
                "bar-count",
                f"series {sid}: {len(cats)} ungrouped bars — a wall of "
                f"same-shape bars reads as noise; aggregate, group "
                f"('by'/'stack') or switch to dots",
            )
    # hist-bin-sanity：<5 是过平滑糊块，>200 是逐点茅草
    if kind == "hist":
        bins = merged.get("bins", "auto")
        n_bins = None
        if _is_num(bins):
            n_bins = int(bins)
        elif isinstance(bins, (list, tuple)):
            n_bins = len(bins) - 1
        if n_bins is not None and not 5 <= n_bins <= 200:
            lint(
                "hist-bin-sanity",
                f"series {sid}: {n_bins} bins — outside the sane "
                f"5..200 window (oversmooth soup / per-point grass)",
            )
    # violin-min-points：KDE 轮廓在小样本上是假精确，box 更诚实
    if kind == "violin":
        for g in rec.groups:
            n = sum(1 for v in _vals(g.rows, merged["y"], "y", sid) if _is_num(v))
            if n < 10:
                lint(
                    "violin-min-points",
                    f"series {sid}: group {g.raw!r} has {n} points (<10) — "
                    f"a KDE silhouette overfits tiny samples; use 'box'",
                )
    # kde-min-points：同口径——小样本密度曲线是假精确，ecdf/散点更诚实
    if kind == "kde":
        for g in rec.groups:
            n = sum(1 for v in _vals(g.rows, merged["x"], "x", sid) if _is_num(v))
            if n < 10:
                lint(
                    "kde-min-points",
                    f"series {sid}: group {g.raw!r} has {n} points (<10) — "
                    f"a KDE curve overfits tiny samples; use 'ecdf' or 'scatter'",
                )
    # heat-cell-text：单轴 >20 格时格内字注定糊成噪声，建议关标注
    if kind == "heat" and merged.get("annotate") not in (None, False):
        if "matrix" in merged:
            nx, ny = len(merged["matrix"][0]), len(merged["matrix"])
        else:
            xs = {r.get(merged["x"]) for g in rec.groups for r in g.rows}
            ys = {r.get(merged["y"]) for g in rec.groups for r in g.rows}
            xs.discard(None)
            ys.discard(None)
            nx, ny = len(xs), len(ys)
        if nx > 20 or ny > 20:
            lint(
                "heat-cell-text",
                f"series {sid}: {nx}x{ny} grid with annotate on — past "
                f"~20 cells per axis in-cell text smears; set annotate:false",
            )

    if kind == "pred" and parent is not None:
        p_ls = merged.get("ls") or "-"
        p_mk = merged.get("marker") or ("x" if parent.merged.get("marker") else None)
        if p_ls == (parent.merged.get("ls") or "-") and p_mk == (
            parent.merged.get("marker")
        ):
            ctx.lint(
                "pred-indistinct",
                f"series {sid} duplicates parent {parent.id} style",
                pid,
            )

    ctx.records[sid] = rec
    return rec


# ------------------------------------------------------------------- 图型


def _angles_for(panel, recs, ctx, pid):
    dims = panel.get("dims")
    if dims is None:
        seen = []
        for rec in recs:
            for g in rec.groups:
                for r in g.rows:
                    v = r.get(rec.merged.get("x"))
                    if v is not None and v not in seen:
                        seen.append(v)
        dims = seen
    ctx.angles[pid] = dict(
        zip(dims, np.linspace(0, 2 * np.pi, len(dims), endpoint=False))
    )
    return ctx.angles[pid]


def _to_angle(amap, v):
    """radar 维度标签 -> 角度；非维度/不可哈希值原样穿透。"""
    try:
        return amap[v]
    except (KeyError, TypeError):
        return v


def _dim_angle(amap, x):
    """x 是声明维度或裸数值角度则 -> 角度，否则 None。"""
    try:
        return amap[x]
    except (KeyError, TypeError):
        return x if _is_num(x) else None


def _polar_join(ctx, pid, rec, xs, *cols):
    """把 radar 的 x 值解析为角度，值列同步过滤。

    维度名经面板的 dim->angle 表映射；数值即裸角度。其余（拼错的维度
    名、None 缺 x）丢弃——每个被丢的非 None 行都发 ``dim-unresolved``
    lint，部分数据丢失绝不静默。
    """
    amap = ctx.angles.get(pid, {})
    lint = ctx.lint_proxy(pid)
    ang, out = [], [[] for _ in cols]
    for i, x in enumerate(xs):
        if x is None:
            continue
        a = _dim_angle(amap, x)
        if a is None:
            lint(
                "dim-unresolved",
                f"series {rec.id}: x {x!r} is not a dim of radar panel",
            )
            continue
        ang.append(a)
        for o, col in zip(out, cols):
            o.append(col[i])
    return ang, out


def _polar_pts(ctx, pid, rec, xs, ys):
    """radar 轮廓线：按维度 join、丢缺失 y、闭合回路。"""
    ang, (ys,) = _polar_join(ctx, pid, rec, xs, ys)
    pts = sorted((a, y) for a, y in zip(ang, ys) if y is not None)
    if not pts:
        return [], []
    xs2 = [p[0] for p in pts] + [pts[0][0] + 2 * np.pi]
    ys2 = [p[1] for p in pts] + [pts[0][1]]
    return xs2, ys2


def _child_xgrid(rec, g, pg, *cols):
    """``of`` 子组的 x 网格与对齐值列。

    子组自声明 ``x`` 画在自己的列上；继承的 ``x`` 把子组行*按值* join
    到父系列实际绘制的 x 网格上（网格顺序优先）——子组 x 不在父网格
    中是 SpecError，绝不静默重采样或长度错位填充。
    返回 ``(xs, cols, joined)``，每个 col 与 xs 对齐。
    """
    merged = rec.merged
    xs = _vals(g.rows, merged.get("x"), "x", rec.id)
    cols = list(cols)
    for c in cols:
        if len(c) != len(xs):
            raise SpecError(
                f"series {rec.id}: x has {len(xs)} values but a value "
                f"column has {len(c)}"
            )
    if pg is None or not pg.xs or "x" in rec.sspec:
        return xs, cols, False
    pos = {}
    for i, x in enumerate(pg.xs):
        try:
            pos.setdefault(x, i)
        except TypeError:
            continue  # 父 x 不可哈希——无法锚定 join
    order = []
    for i, x in enumerate(xs):
        if x is None:
            continue
        try:
            order.append((pos[x], i))
        except (KeyError, TypeError):
            raise SpecError(
                f"series {rec.id}: x {x!r} is not on parent "
                f"{rec.parent.id}'s x grid; declare an own 'x' column "
                f"to draw on a different grid"
            ) from None
    order.sort()
    keep = [i for _, i in order]
    return [xs[i] for i in keep], [[c[i] for i in keep] for c in cols], True


def _draw_line(ax, rec, ctx, pid):
    merged = rec.merged
    if ctx.polar.get(pid, False):
        xmap = ymap = xdisp = ydisp = None
    else:
        xmap, xdisp = _cat_map(ctx.panel_recs.get(pid, ()), "x")
        ymap, ydisp = _cat_map(ctx.panel_recs.get(pid, ()), "y")
    for g in rec.groups:
        xs = _vals(g.rows, merged.get("x"), "x", rec.id)
        ys = _vals(g.rows, merged.get("y"), "y", rec.id)
        if ctx.polar.get(pid, False):
            xs, ys = _polar_pts(ctx, pid, rec, xs, ys)
            xerr = yerr = None  # polar 在 prepare 已拒绝 xerr/yerr
        else:
            # 类别轴字符串值先落到同面板槽位再排序——裸字符串排序会崩
            xs = [_cat_lookup(v, xmap, xdisp, "x", rec.id, "line") for v in xs]
            ys = [_cat_lookup(v, ymap, ydisp, "y", rec.id, "line") for v in ys]
            idx = _sort_xy_idx(xs, ys, merged.get("sort_x", True))
            xerr = _take_err(_err_vals(g.rows, merged.get("xerr"), "xerr", rec.id), idx)
            yerr = _take_err(_err_vals(g.rows, merged.get("yerr"), "yerr", rec.id), idx)
            xs = [xs[i] for i in idx]
            ys = [ys[i] for i in idx]
        kw = _style_kwargs(g, merged)
        g.artist = ax.plot(
            xs,
            ys,
            color=g.color,
            label=_legend_label(rec, g),
            **{**kw, **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))},
        )[0]
        _draw_errbar(ax, xs, ys, xerr, yerr, merged, g.color, ctx, pid)
        if merged.get("fill"):
            if ctx.polar.get(pid, False):
                _mark(*ax.fill(xs, ys, color=g.color, alpha=merged["fill"]))
            else:
                ctx.lint(
                    "fill-ignored", f"series {rec.id}: fill only applies on radar", pid
                )


def _draw_pred(ax, rec, ctx, pid):
    merged = rec.merged
    parent = rec.parent
    polar = ctx.polar.get(pid, False)
    xmap, xdisp = (None, None) if polar else _cat_map(ctx.panel_recs.get(pid, ()), "x")
    for g in rec.groups:
        xs, (ys,), joined = _child_xgrid(
            rec,
            g,
            parent.group(g.key),
            _vals(g.rows, merged.get("y"), "y", rec.id),
        )
        if polar:
            xs, ys = _polar_pts(ctx, pid, rec, xs, ys)
        else:
            xs = [_cat_lookup(v, xmap, xdisp, "x", rec.id, "pred") for v in xs]
            pairs = _drop_none(xs, ys)
            if not joined and all(_is_num(x) for x, _ in pairs):
                pairs.sort(key=lambda p: p[0])
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
        kw = _style_kwargs(g, merged)
        kw.setdefault("linestyle", "--")
        if parent.merged.get("marker") is not None and g.marker is None:
            kw["marker"] = "x"
        g.artist = ax.plot(
            xs,
            ys,
            color=g.color,
            label=_legend_label(rec, g),
            **{**kw, **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))},
        )[0]
        _mark(g.artist)


def _draw_band(ax, rec, ctx, pid):
    merged = rec.merged
    parent = rec.parent
    polar = ctx.polar.get(pid, False)
    xmap, xdisp = (None, None) if polar else _cat_map(ctx.panel_recs.get(pid, ()), "x")
    alpha = merged.get("alpha")
    if alpha is None:
        alpha = _BAND_ALPHA.get(merged.get("semantics"), 0.12)
    for g in rec.groups:
        xs, (lo, hi), joined = _child_xgrid(
            rec,
            g,
            parent.group(g.key) if parent is not None else None,
            _vals(g.rows, merged["lo"], "lo", rec.id),
            _vals(g.rows, merged["hi"], "hi", rec.id),
        )
        if polar:
            ang, (lo, hi) = _polar_join(ctx, pid, rec, xs, lo, hi)
            pts = sorted(
                (a, lv, hv)
                for a, lv, hv in zip(ang, lo, hi)
                if lv is not None and hv is not None
            )
            if pts:
                # 闭合轮廓带：首点在 +2pi 处续接
                pts.append((pts[0][0] + 2 * np.pi, pts[0][1], pts[0][2]))
            xs = [p[0] for p in pts]
            lo = [p[1] for p in pts]
            hi = [p[2] for p in pts]
        else:
            xs = [_cat_lookup(v, xmap, xdisp, "x", rec.id, "band") for v in xs]
            pts = [
                (x, lv, hv)
                for x, lv, hv in zip(xs, lo, hi)
                if x is not None and lv is not None and hv is not None
            ]
            if not joined and all(_is_num(p[0]) for p in pts):
                pts.sort(key=lambda p: p[0])
            xs = [p[0] for p in pts]
            lo = [p[1] for p in pts]
            hi = [p[2] for p in pts]
        g.artist = ax.fill_between(
            xs,
            lo,
            hi,
            color=g.color,
            alpha=alpha,
            linewidth=0,
            label=_legend_label(rec, g),
            **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid))),
        )
        if merged.get("zorder") is not None:
            g.artist.set_zorder(merged["zorder"])
        _mark(g.artist)


_JITTER_KEYS = {"w", "at", "axis", "seed"}


def _check_jitter(jit, sid):
    """scatter jitter 形态校验：正数（±j/2 对称窗）或 {w,at,axis,seed}。"""
    where = f"series {sid} (scatter) jitter"
    if _is_num(jit):
        if jit <= 0:
            raise SpecError(f"{where}: must be > 0, got {jit!r}")
        return
    if not isinstance(jit, dict):
        raise SpecError(
            f"{where}: must be a number or {{w, at, axis, seed}}, got {jit!r}"
        )
    _check_keys(jit, _JITTER_KEYS, where)
    w = jit.get("w")
    if not (_is_num(w) and w > 0):
        raise SpecError(f"{where}: 'w' must be a positive number, got {w!r}")
    if "at" in jit and not _is_num(jit["at"]):
        raise SpecError(f"{where}: 'at' must be a number, got {jit['at']!r}")
    axis = jit.get("axis", "x")
    if axis not in ("x", "y"):
        raise SpecError(f"{where}: axis must be 'x'|'y', got {axis!r}")
    seed = jit.get("seed")
    if seed is not None and not (
        isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0
    ):
        raise SpecError(f"{where}: seed must be a non-negative int, got {seed!r}")


def _jitter_offsets(jit, n, sid, gkey):
    """-> (offsets, axis)：seeded 均匀位移。种子逐 (series,组键) 派生——
    跨进程可复现，且增删其他组不动本组布局；组内行序追加只吃 rng 流尾部，
    已有点的位移不漂。"""
    if _is_num(jit):
        lo, hi, axis, seed = -float(jit) / 2, float(jit) / 2, "x", None
    else:
        lo = float(jit.get("at", 0.0))
        hi = lo + float(jit["w"])
        axis = jit.get("axis", "x")
        seed = jit.get("seed")
    if seed is None:
        seed = zlib.crc32(f"{sid}|{gkey}".encode())
    return np.random.default_rng(seed).uniform(lo, hi, n), axis


def _draw_scatter(ax, rec, ctx, pid):
    merged = rec.merged
    # 类别轴坐标统一走同面板 _cat_map（bar 槽位 / box·violin 组位 / heat
    # 格心）——scatter 不再按自身首见序私建映射：与兄弟系列的类别序
    # 错位即静默落错槽位
    if ctx.polar.get(pid, False):
        xmap = ymap = xdisp = ydisp = None
    else:
        xmap, xdisp = _cat_map(ctx.panel_recs.get(pid, ()), "x")
        ymap, ydisp = _cat_map(ctx.panel_recs.get(pid, ()), "y")
    for g in rec.groups:
        n = len(g.rows)
        xs = _vals(g.rows, merged.get("x"), "x", rec.id)
        ys = _vals(g.rows, merged.get("y"), "y", rec.id)
        if xmap is not None:
            xs = [_cat_lookup(v, xmap, xdisp, "x", rec.id, "scatter") for v in xs]
            ys = [_cat_lookup(v, ymap, ydisp, "y", rec.id, "scatter") for v in ys]
        s = merged.get("s", 20)
        s_col = _vals(g.rows, s, "s", rec.id) if isinstance(s, str) else s
        xerr = _err_vals(g.rows, merged.get("xerr"), "xerr", rec.id)
        yerr = _err_vals(g.rows, merged.get("yerr"), "yerr", rec.id)
        if ctx.polar.get(pid, False):
            # xerr/yerr 已在 prepare 拒掉；s/逐行 color 要随 join 锁步过滤
            xs, joined = _polar_join(
                ctx,
                pid,
                rec,
                xs,
                ys,
                s_col if isinstance(s_col, list) else [None] * len(xs),
                g.color if isinstance(g.color, list) else [None] * len(xs),
            )
            ys = joined[0]
            if isinstance(s_col, list):
                s_col = joined[1]
            if isinstance(g.color, list):
                g.color = joined[2]
            xerr = yerr = None
        else:
            idx = _drawn_idx(xs, ys)
            xs = [xs[i] for i in idx]
            ys = [ys[i] for i in idx]
            s_col = _take_rows(s_col, n, idx)
            g.color = _take_rows(g.color, n, idx)
            xerr = _take_err(xerr, idx)
            yerr = _take_err(yerr, idx)
            jit = merged.get("jitter")
            if jit is not None:
                # strip/raincloud 点层：位置列 + 窗内 seeded 位移，免物化 xj 列；
                # 位移在 errbar 之前生效，点与误差棒保持锚定
                joff, jaxis = _jitter_offsets(jit, len(xs), rec.id, g.key)
                tgt = xs if jaxis == "x" else ys
                if any(not _is_num(v) for v in tgt):
                    raise SpecError(
                        f"series {rec.id} (scatter): jitter needs numeric "
                        f"positions on axis {jaxis!r}"
                    )
                tgt = [v + o for v, o in zip(tgt, joff)]
                if jaxis == "x":
                    xs = tgt
                else:
                    ys = tgt
        marker = g.marker or "o"
        kw = {
            "s": s_col,
            "color": g.color,
            "marker": marker,
            "alpha": merged.get("alpha", 0.8),
            "label": _legend_label(rec, g),
        }
        # 空心 marker（x、+、tick）不认 edgecolors，matplotlib 会告警
        if MarkerStyle(marker).is_filled():
            ec = merged.get("edgecolor")
            if ec is not None:
                ec = _edge_color(ec, ctx, ctx.lint_proxy(pid), rec.id)
            kw["edgecolors"] = ec if ec is not None else "white"
            kw["linewidths"] = merged.get("linewidths", 0.4)
        if merged.get("zorder") is not None:
            kw["zorder"] = merged["zorder"]
        props = dict(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))
        # 注入 kwargs 的 props 别名会在 scatter() 内撞名
        # （edgecolor vs edgecolors 等）——props 赢，丢掉默认
        if props.keys() & {"edgecolor", "edgecolors"}:
            kw.pop("edgecolors", None)
        if props.keys() & {"linewidth", "linewidths"}:
            kw.pop("linewidths", None)
        g.artist = ax.scatter(xs, ys, **{**kw, **props})
        _draw_errbar(
            ax,
            xs,
            ys,
            xerr,
            yerr,
            merged,
            g.color if g.color is not None else fv.NEUTRALS["vink"],
            ctx,
            pid,
        )


def _bar_cats(rec):
    """bar 系列的类别槽位序：跨组首见序合并、全数值升序——_draw_bar 的
    柱位与 sig 的类别挂点共用同一份口径。"""
    cats = []
    xcol = rec.merged.get("x")
    for g in rec.groups:
        for r in g.rows:
            v = r.get(xcol)
            if v is not None and v not in cats:
                cats.append(v)
    if all(_is_num(c) for c in cats):
        cats.sort()
    return cats


def _bar_geometry(rec):
    """bar 的槽位几何 -> (pos 表, 单柱宽)：_draw_bar 布柱与 sig 的
    '槽位:组值' 挂点共用同一份口径。pos 键是原始类别值（num_x 为真实
    坐标）；width 已是 dodge 口径的单组宽度（stacked 不按组数缩）。"""
    merged = rec.merged
    cats = _bar_cats(rec)
    n = len(rec.groups)
    stacked = merged.get("stack", False)
    if rec.num_x:
        # 数值 x：柱落真实坐标（校准图分箱中心等），宽度单位 = 数据单位，
        # 默认取最小间距的 0.8（dodge 再按组数分）；显式 width 同单位
        pos = {c: float(c) for c in cats}
        gaps = np.diff(sorted({float(c) for c in cats}))
        unit = float(gaps.min()) if gaps.size else 1.0
        width = merged.get("width") or (
            0.8 * unit if stacked else 0.8 * unit / max(n, 1)
        )
    else:
        pos = {c: i for i, c in enumerate(cats)}
        # stacked 时各组同槽位重叠堆叠——宽度不按组数缩（dodge 才分宽）
        width = merged.get("width") or (0.8 if stacked else min(0.8 / max(n, 1), 0.8))
    return pos, width


def _draw_bar(ax, rec, ctx, pid):
    merged = rec.merged
    cats = _bar_cats(rec)
    num_x = rec.num_x
    n = len(rec.groups)
    stacked = merged.get("stack", False)
    horiz = merged.get("dir") == "h"
    pos, width = _bar_geometry(rec)
    base = merged.get("baseline", 0)
    lint = ctx.lint_proxy(pid)
    if n > 1 and not stacked:
        # by 扇出但每个 x 槽位至多一组有行：宽度仍按 n 缩窄、柱体逐槽偏
        # 离槽位中心，dodge 形同虚设——by==x 字段误用是典型来源
        xs_per_group = [
            {r.get(merged.get("x")) for r in g.rows} - {None} for g in rec.groups
        ]
        max_in_slot = max(
            (sum(c in xs for xs in xs_per_group) for c in cats), default=0
        )
        if max_in_slot <= 1:
            misuse = (
                "; 'by' names the x field itself, which is almost always a field misuse"
                if rec.by_field is not None and rec.by_field == merged.get("x")
                else ""
            )
            lint(
                "dodge-single-group",
                f"series {rec.id}: 'by' fans out to {n} groups but every "
                f"x slot holds at most one — bars still narrow to "
                f"{width:.3g} and dodge off the slot center{misuse}",
            )
    labels = dict(_obj(merged.get("labels"), f"series {rec.id} labels"))
    label_groups = None
    if labels:
        _check_keys(labels, BAR_LABEL_KEYS, f"series {rec.id} labels")
        mode = labels.get("mode", "value")
        if mode not in _BAR_LABEL_MODES:
            raise SpecError(
                f"series {rec.id}: labels.mode must be one of "
                f"{_BAR_LABEL_MODES}, got {mode!r}"
            )
        lg = labels.get("groups")
        if lg is not None:
            if not isinstance(lg, list):
                raise SpecError(
                    f"series {rec.id}: labels.groups must be a list, got {lg!r}"
                )
            label_groups = {_norm_key(k) for k in lg}
        if "color" in labels:
            labels["color"] = ctx.colors.token(labels["color"], lint)
    conn_kw = None
    conn_groups = None
    conn_label = None
    if merged.get("connect"):
        cc = merged["connect"]
        cc = {} if cc is True else dict(_obj(cc, f"series {rec.id} connect"))
        _check_keys(cc, BAR_CONNECT_KEYS, f"series {rec.id} connect")
        conn_label = cc.get("label")
        if conn_label is not None and not isinstance(conn_label, str):
            raise SpecError(
                f"series {rec.id}: connect.label must be a string, got {conn_label!r}"
            )
        conn_kw = {
            "color": ctx.colors.token(cc.get("color", "baseline"), lint),
            "ls": cc.get("ls", "--"),
            "lw": cc.get("lw", 0.8),
            "zorder": cc.get("zorder", 3),
        }
        props = _resolve_props(cc.get("props"), ctx, lint)
        # props 别名与注入键在 mpl 内撞车（ls+linestyle 双双 TypeError）——
        # props-win 惯例：props 提供了别名就撤掉被覆盖的注入默认
        if props.keys() & {"ls", "linestyle"}:
            conn_kw.pop("ls", None)
        if props.keys() & {"lw", "linewidth"}:
            conn_kw.pop("lw", None)
        if props.keys() & {"c", "color"}:
            conn_kw.pop("color", None)
        conn_kw.update(props)
        cg = cc.get("groups")
        if cg is not None:
            if not isinstance(cg, list):
                raise SpecError(
                    f"series {rec.id}: connect.groups must be a list, got {cg!r}"
                )
            conn_groups = {_norm_key(k) for k in cg}
    if merged.get("xerr") is not None and not num_x:
        lint(
            "axis-ignored",
            f"series {rec.id}: xerr on a categorical bar axis has no meaning — dropped",
        )
    bspec = merged.get("bottom")
    label_hit = conn_hit = False
    # 混合正负堆叠：正/负各自从 baseline 双向累加，互不吞没
    acc_pos = np.zeros(len(cats))
    acc_neg = np.zeros(len(cats))
    for gi, g in enumerate(rec.groups):
        xcol = [r.get(merged.get("x")) for r in g.rows]
        vals = [r.get(merged.get("y")) for r in g.rows]
        ymap = {x: v for x, v in zip(xcol, vals) if x is not None}
        vcol = [ymap.get(c, 0) or 0 for c in cats]
        if stacked:
            vf = np.asarray(vcol, dtype=float)
            off = 0.0
            bottom = np.where(vf >= 0, acc_pos, acc_neg) + base
            acc_pos += np.clip(vf, 0, None)
            acc_neg += np.clip(vf, None, 0)
        else:
            off = (gi - (n - 1) / 2) * width
            if bspec is None:
                bottom = base
            else:
                # 浮动柱：逐行底边列（瀑布 run-in），缺值回落 baseline
                bvals = _vals(g.rows, bspec, "bottom", rec.id)
                bmap = {x: b for x, b in zip(xcol, bvals) if x is not None}
                bottom = []
                for c in cats:
                    b = bmap.get(c)
                    if b is None:
                        b = base
                    elif not _is_num(b):
                        raise SpecError(
                            f"series {rec.id}: bottom {bspec!r} must be "
                            f"numeric, got {b!r} at x={c!r}"
                        )
                    bottom.append(b)
        hatch = None
        hs = merged.get("hatch")
        if isinstance(hs, dict):
            for k, v in hs.items():
                if _norm_key(k) == g.key:
                    hatch = v
        elif hs:
            hatch = hs
        elif ctx.theme.emphasis == "accent-first" and gi == 0:
            hatch = "//"
        kw = {
            "color": g.color,
            "label": _legend_label(rec, g),
            "edgecolor": "white",
            "hatch": hatch,
            "alpha": merged.get("alpha", 0.92),
        }
        if merged.get("zorder") is not None:
            kw["zorder"] = merged["zorder"]
        kw.update(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))
        # yerr 沿数值轴：竖条 → yerr，横条 → 换成 xerr；锚在柱顶（累计尖端）
        err = _map_err_cats(
            _err_vals(g.rows, merged.get("yerr"), "yerr", rec.id),
            xcol,
            cats,
        )
        # 数值 x 才有沿 x 的误差棒；类别 x 的 xerr 上面已按 axis-ignored 报
        xerr_pack = (
            _map_err_cats(
                _err_vals(g.rows, merged.get("xerr"), "xerr", rec.id),
                xcol,
                cats,
            )
            if num_x
            else None
        )
        tip = np.asarray(bottom, dtype=float) + np.asarray(vcol, float)
        slots = [pos[c] + off for c in cats]
        if horiz:
            rects = ax.barh(slots, vcol, height=width, left=bottom, **kw)
            _draw_errbar(
                ax, tip, slots, err, xerr_pack, merged, fv.NEUTRALS["vink"], ctx, pid
            )
        else:
            rects = ax.bar(slots, vcol, width=width, bottom=bottom, **kw)
            _draw_errbar(
                ax, slots, tip, xerr_pack, err, merged, fv.NEUTRALS["vink"], ctx, pid
            )
        g.artist = rects
        if conn_kw is not None and (conn_groups is None or g.key in conn_groups):
            # conn_hit 语义 = 真有线段画出（<2 类别时 _bar_connect 空转，
            # 幽灵图例不能跟着撒谎）
            conn_hit = conn_hit or bool(
                _bar_connect(ax, slots, tip, width, conn_kw, horiz)
            )
        if labels and (label_groups is None or g.key in label_groups):
            label_hit = True
            _bar_labels(ax, rects, vcol, labels, horiz, tip, err)
    if label_groups is not None and not label_hit:
        lint(
            "axis-ignored",
            f"series {rec.id}: labels.groups matched no group — no labels drawn",
        )
    if conn_label is not None and conn_hit:
        # 图例幽灵：连接线是 fv-neutral（不算系列、不进图例），label 需要
        # 一个零数据 Line2D 载体进图例；样式克隆归并后的 conn_kw
        ghost = Line2D(
            [],
            [],
            color=conn_kw.get("color"),
            linestyle=conn_kw.get("linestyle", conn_kw.get("ls", "--")),
            linewidth=conn_kw.get("linewidth", conn_kw.get("lw", 0.8)),
            label=conn_label,
        )
        ax.add_line(ghost)
        _mark(ghost)
        rec.conn_label = conn_label
    if conn_groups is not None and not conn_hit:
        lint(
            "axis-ignored",
            f"series {rec.id}: connect.groups matched no group — no connectors drawn",
        )
    if conn_kw is not None and len(cats) < 2:
        lint(
            "axis-ignored",
            f"series {rec.id}: connect needs at least 2 categories — nothing drawn",
        )
    if not num_x:
        # 数值 x 走 mpl 自动数值刻度；类别槽位才由 kind 层写刻度
        if horiz:
            ax.set_yticks(list(pos.values()), [str(c) for c in cats])
        else:
            ax.set_xticks(list(pos.values()), [str(c) for c in cats])


def _bar_connect(ax, slots, tips, width, kw, horiz):
    """相邻柱的边到边虚线连接：level = 前一根柱的远端边（瀑布 run-out），
    只画在柱间隙（右缘 -> 下一根左缘）。逐组调用，dodge 错位照走。
    返回画出的线段列表（供 conn_hit 判定与幽灵图例）。"""
    arts = []
    for i in range(len(slots) - 1):
        a, b = slots[i] + width / 2, slots[i + 1] - width / 2
        if horiz:
            arts += ax.plot([tips[i], tips[i]], [a, b], **kw)
        else:
            arts += ax.plot([a, b], [tips[i], tips[i]], **kw)
    _mark(*arts)
    return arts


def _bar_labels(ax, rects, vals, labels, horiz, tips=None, err=None):
    mode = labels.get("mode", "value")
    fmt = labels.get("fmt")
    if fmt is None:
        fmt = "{:+.3g}" if mode == "delta" else "{:.2g}"
    color = labels.get("color", fv.NEUTRALS["vink"])
    shown = vals if mode != "cum" or tips is None else tips
    # delta/cum 的负值柱把标值推到远端边外侧（value 模式锚点维持旧行为）
    outward = mode in ("delta", "cum")
    # 误差帽沿数值轴顶出柱尖：标值锚点加对外一侧的帽长（数据单位），
    # dy 的 offset points 仍落在帽外；sym 双侧同值取绝对值、asym 取
    # 对外一侧（负帽长/非数值按 0 ——帽没顶出去就不占净空）
    pads = [0.0] * len(vals)
    if err:
        asym = isinstance(err[0], list)
        los, his = (err[0], err[1]) if asym else (err, err)
        pads = []
        for v, lo, hi in zip(vals, los, his):
            side = lo if (outward and v < 0) else hi
            if _is_num(side) and np.isfinite(side):
                pads.append(max(float(side), 0.0) if asym else abs(float(side)))
            else:
                pads.append(0.0)
    for i, (r, v, d) in enumerate(zip(rects, vals, shown)):
        pad = pads[i]
        if horiz:
            dx = labels.get("dy", 2)
            ha = "left"
            sgn = 1
            if outward and v < 0:
                dx = -abs(dx)
                ha = "right"
                sgn = -1
            t = ax.annotate(
                fmt.format(d),
                (
                    r.get_x() + r.get_width() + sgn * pad,
                    r.get_y() + r.get_height() / 2,
                ),
                xytext=(dx, 0),
                textcoords="offset points",
                va="center",
                ha=ha,
                fontsize=labels.get("fontsize"),
                color=color,
            )
        else:
            dy = labels.get("dy", 1.5)
            va = "baseline"
            sgn = 1
            if outward and v < 0:
                dy = -abs(dy)
                va = "top"
                sgn = -1
            t = ax.annotate(
                fmt.format(d),
                (
                    r.get_x() + r.get_width() / 2,
                    r.get_y() + r.get_height() + sgn * pad,
                ),
                xytext=(0, dy),
                textcoords="offset points",
                ha="center",
                va=va,
                fontsize=labels.get("fontsize"),
                color=color,
            )
        _mark(t)
        # renderer 放的标签墨迹 autoscale 看不见（offset points）——挂到
        # axes 上，render 收尾的 _reserve_label_headroom 量真实 extent 补轴限
        ax.__dict__.setdefault("_fv_bar_labels", []).append(t)


# ------------------------------------------------------------------ sig


_SIG_STAR_CUTS = ((0.001, "***"), (0.01, "**"), (0.05, "*"))


def _owner_cat_map(recs, axis):
    """结构所有者的类别表：bar 类目序槽位（数值 x 柱 → 真实坐标）、
    box/violin 组位（组键与 label 都收，raw 优先）、heat 两轴类别
    （格心 i+0.5）；dir:'h' 的 bar/box/violin 类别落在 y 轴。多来源
    冲突首见优先；disp 是报错时列给用户的可用类别清单。"""
    pos, disp = {}, []

    def put(name, p):
        if name is None:
            return
        nk = _norm_key(name)
        if nk not in pos:
            pos[nk] = p
            disp.append(name)

    for r in recs:
        horiz = r.merged.get("dir") == "h"
        on_axis = horiz == (axis == "y")
        if r.kind == "bar" and on_axis:
            cats = _bar_cats(r)
            m = (
                {c: float(c) for c in cats}
                if r.num_x
                else {c: i for i, c in enumerate(cats)}
            )
            for c, p in m.items():
                put(c, p)
        elif r.kind in ("box", "violin") and on_axis:
            pp = r.merged.get("positions") or list(range(1, len(r.groups) + 1))
            for g, p in zip(r.groups, pp):
                put(g.raw, p)
                put(g.label, p)
        elif r.kind == "heat":
            xcats, ycats, _ = _heat_cells(r.merged, r)
            for i, c in enumerate(xcats if axis == "x" else ycats):
                put(c, i + 0.5)
    return pos, disp


# 消费型类别轴建立者：结构所有者缺席时按自身数据首见序建槽位
_CONSUMER_CAT_KINDS = ("scatter", "line")


def _consumer_cat_map(recs, axis):
    """消费型类别表：scatter/line 的 axis 字段字符串值按组内首见序
    落槽位 0,1,2…（蜂群/类别散点是真实图型）。字段解析与 draw 走同
    一条 _vals（列名 | 数值 | 字面列表）；只收字符串，数值照旧直通。"""
    pos, disp = {}, []
    for r in recs:
        if r.kind not in _CONSUMER_CAT_KINDS:
            continue
        for g in r.groups:
            for v in _vals(g.rows, r.merged.get(axis), axis, r.id):
                if isinstance(v, str):
                    nk = _norm_key(v)
                    if nk not in pos:
                        pos[nk] = len(pos)
                        disp.append(v)
    return pos, disp


def _cat_map(recs, axis):
    """同面板类别名 → axis 轴位置（'_cat_lookup' 的查表源）：结构所有
    者图优先；空缺时由消费型 kind（scatter/line）按全面板数据首见序
    兜底建表。表一旦建成就冻结——未知名不静默追加，由 _cat_lookup
    响亮报错。"""
    pos, disp = _owner_cat_map(recs, axis)
    if pos:
        return pos, disp
    return _consumer_cat_map(recs, axis)


def _owns_cat_axis(r, axis):
    """该 rec 是否在 axis 轴上拥有类别刻度（_apply_axis/_tick_density
    的 categorical 口径）：非数值 bar、box/violin——dir:'h' 类别落 y
    轴，与 _owner_cat_map 的 on_axis 同口径；num_x bar 是数值轴。"""
    if r.kind == "bar" and r.num_x:
        return False
    return r.kind in ("bar", "box", "violin") and (r.merged.get("dir") == "h") == (
        axis == "y"
    )


def _cat_lookup(v, catmap, disp, axis, sid, what):
    """坐标值 → 轴位置：数值直过；字符串按 _norm_key 命中同面板类别表
    ——未知名响亮报错并列出可用类别，该轴无类别建立者时报非类别轴。"""
    if _is_num(v):
        return float(v)
    if isinstance(v, str):
        nk = _norm_key(v)
        if nk in catmap:
            return float(catmap[nk])
        if disp:
            raise SpecError(
                f"series {sid} ({what}): {v!r} is not a known {axis}-axis "
                f"category {disp[:12]}"
            )
        raise SpecError(
            f"series {sid} ({what}): string coordinate {v!r} on a "
            f"non-categorical {axis}-axis"
        )
    return v


def _sig_group_anchor(v, recs, sid):
    """'槽位:组值' 复合挂点 → 组内 dodge 柱心 x：末个 ':' 切分（槽位名
    本身可含 ':'），在同面板竖直 bar 的 by 扇出组里找组值（raw 与
    label 都收），命中后按 _bar_geometry 的 (gi-(n-1)/2)·width 偏移解
    出实际柱位（stacked 偏移为 0 即槽位中心）；找不到能同时提供该槽位
    与该组的 bar 时响亮报错。"""
    slot_s, _, grp_s = v.rpartition(":")
    nslot, ngrp = _norm_key(slot_s), _norm_key(grp_s)
    groups, slots = [], []
    for r in recs:
        if r.kind != "bar" or r.merged.get("dir") == "h":
            continue  # 横条 dodge 在 y 轴——sig a/b 只挂 x
        pos, width = _bar_geometry(r)
        npos = {_norm_key(c): p for c, p in pos.items()}
        groups.extend(g.raw for g in r.groups)
        slots.extend(pos)
        gi = next(
            (
                i
                for i, g in enumerate(r.groups)
                if ngrp in (_norm_key(g.raw), _norm_key(g.label))
            ),
            None,
        )
        if gi is None or nslot not in npos:
            continue  # 组或槽位不归这条 bar——换下一条
        n = len(r.groups)
        off = 0.0 if r.merged.get("stack", False) else (gi - (n - 1) / 2) * width
        return float(npos[nslot] + off)
    raise SpecError(
        f"series {sid} (sig): anchor {v!r} matched no dodged bar group — "
        f"same-panel bar groups "
        f"{[g for g in groups if g is not None][:12]}, slots {slots[:12]}"
    )


def _sig_anchor(v, catmap, disp, recs, sid):
    """挂点值 → x 坐标：数值直接用；字符串按 _norm_key 命中同面板类别
    名（bar 槽位 / box、violin 组位）；'槽位:组值' 复合形按该 bar 的
    dodge 几何解到组内柱心；其余响亮报错并给出可用类别。"""
    if _is_num(v):
        return float(v)
    if isinstance(v, str):
        nk = _norm_key(v)
        if nk in catmap:
            return float(catmap[nk])
        if ":" in v:
            return _sig_group_anchor(v, recs, sid)
        raise SpecError(
            f"series {sid} (sig): anchor {v!r} is neither a numeric x "
            f"coordinate nor a known category {disp[:12]}"
        )
    raise SpecError(
        f"series {sid} (sig): anchor {v!r} must be a number or a category name"
    )


def _sig_text(row, base_fs):
    """行 → (标签文本, 字号)：p 映射星号（'ns' 弱化一档），text 字面量
    直用（弱化半档）——sigbracket_demo 的字号对。"""
    p = row.get("p")
    if p is None:
        return row["text"], base_fs - 1.2
    for cut, s in _SIG_STAR_CUTS:
        if p < cut:
            return s, base_fs - 0.6
    return "ns", base_fs - 1.4


def _draw_sig(ax, rec, ctx, pid):
    """显著性括号层：每行 {a, b, y, p|text} 一条 Π 形括号——横梁在数据
    坐标 y、垂足长 tick、文本浮 pad 之上。a/b 挂点收数值 x、类别名
    （同面板 bar 类目序 / box、violin 组位）或 '槽位:组值' 复合形
    （by 扇出柱的组内 dodge 柱心）；全 artist fv-neutral，
    不算系列、不进图例。"""
    merged = rec.merged
    sid = rec.id
    rows = [r for g in rec.groups for r in g.rows]
    if not rows:
        return  # empty-series lint 已报过
    lint = ctx.lint_proxy(pid)
    recs = ctx.panel_recs.get(pid, ())
    catmap, disp = _cat_map(recs, "x")
    cspec = merged.get("color")
    ink = ctx.colors.token(cspec, lint) if cspec is not None else fv.NEUTRALS["vink"]
    # tick/pad 缺省按 y 数据窗自适应——draw 前 relim 取的是当前已画
    # artist 的数据域（sig 自己的线还没进 dataLim）
    ax.relim()
    yr = ax.dataLim.y1 - ax.dataLim.y0
    if not np.isfinite(yr) or yr <= 0:
        ys = [float(r["y"]) for r in rows]
        yr = (max(ys) - min(ys)) or 1.0
    tick = merged.get("tick")
    tick = float(tick) if tick is not None else 0.02 * yr
    pad = merged.get("pad")
    pad = float(pad) if pad is not None else 0.008 * yr
    lkw = {
        "color": ink,
        "lw": 0.7,
        "solid_capstyle": "butt",
        "clip_on": False,
        "zorder": merged.get("zorder", _KIND_ZORDER["sig"]),
    }
    if merged.get("alpha") is not None:
        lkw["alpha"] = merged["alpha"]
    props = _resolve_props(merged.get("props"), ctx, lint)
    # props 别名与注入键撞车（ls+linestyle 双双 TypeError）——props-win
    if props.keys() & {"c", "color"}:
        lkw.pop("color", None)
    if props.keys() & {"lw", "linewidth"}:
        lkw.pop("lw", None)
    if props.keys() & {"capstyle", "solid_capstyle"}:
        lkw.pop("solid_capstyle", None)
    lkw.update(props)
    tkw = {
        "ha": "center",
        "va": "bottom",
        "color": ink,
        "clip_on": False,
        "zorder": merged.get("zorder", _KIND_ZORDER["sig"]),
    }
    tprops = _resolve_props(merged.get("textprops"), ctx, lint)
    if tprops.keys() & {"ha", "horizontalalignment"}:
        tkw.pop("ha", None)
    if tprops.keys() & {"va", "verticalalignment"}:
        tkw.pop("va", None)
    if tprops.keys() & {"c", "color"}:
        tkw.pop("color", None)
    tkw.update(tprops)
    base_fs = plt.rcParams["font.size"]
    rec.sig_spans = []
    for r in rows:
        xa = _sig_anchor(r["a"], catmap, disp, recs, sid)
        xb = _sig_anchor(r["b"], catmap, disp, recs, sid)
        if xb < xa:
            xa, xb = xb, xa
        y = float(r["y"])
        txt, fs = _sig_text(r, base_fs)
        (ln,) = ax.plot([xa, xa, xb, xb], [y - tick, y, y, y - tick], **lkw)
        kw_t = dict(tkw)
        kw_t.setdefault("fontsize", fs)
        t = ax.text((xa + xb) / 2, y + pad, txt, **kw_t)
        _mark(ln, t)
        rec.sig_spans.append((y, pad, t.get_fontsize()))


def _resolve_at_value(v, g, rec, ctx, catmap=None):
    """一条 ref/span 位置值：数值 | 列名 | join dict。

    列名必须在组内恰好取到一个值；join dict ``{from, key, field}``
    必须恰好取到一行值。给出 catmap 时非列名字符串原样交还——调用方
    续按类别名查 _cat_lookup
    （列名解释优先，类别名兜底；未知名与非类别轴由 _cat_lookup 报错）。
    """
    if isinstance(v, dict):
        _check_keys(v, {"from", "key", "field"}, f"series {rec.id} at")
        if "field" not in v:
            raise SpecError(f"series {rec.id}: at-join dict needs a 'field' key")
        rows = _filter(ctx.data.get(v.get("from"), []), v.get("key") or {})
        vals = list({_norm_key(r.get(v["field"])) for r in rows})
        if len(vals) != 1:
            raise SpecError(
                f"series {rec.id}: at-join yielded {len(vals)} values (want exactly 1)"
            )
        return vals[0]
    if isinstance(v, str):
        vals = list({_norm_key(r.get(v)) for r in g.rows if v in r})
        if not vals:
            if catmap is not None:
                return v
            raise SpecError(f"series {rec.id}: 'at' {v!r} is not a data column")
        if len(vals) > 1:
            raise SpecError(
                f"series {rec.id}: at-field {v!r} nonunique within a "
                f"group: {sorted(vals, key=str)}"
            )
        return vals[0]
    return v


def _resolve_at(merged, g, rec, ctx, catmap=None):
    """ref 'at'：数值 | 列名 | {from,key,field} join。"""
    return _resolve_at_value(merged.get("at"), g, rec, ctx, catmap)


def _draw_ref(ax, rec, ctx, pid):
    merged = rec.merged
    d = merged.get("dir", "h")
    if d in ("diag", "identity"):
        # y=x 对角线（校准图/parity/ROC/qq）：at 给 y 截距，缺省 0 = 恒等线；
        # 仍走 _resolve_at——列名/join 按组取值照常
        seen = set()
        for g in rec.groups:
            b = _resolve_at(merged, g, rec, ctx) if "at" in merged else 0
            if not _is_num(b):
                raise SpecError(
                    f"series {rec.id} (ref): 'at' on dir:{d} is the "
                    f"y-intercept and must resolve to a number, got {b!r}"
                )
            key = _pos_key(b)
            if key in seen:
                continue
            seen.add(key)
            kw = _style_kwargs(g, merged)
            kw.setdefault(
                "linestyle",
                fv.line_styles(ctx.theme.line_preset)["reference"],
            )
            kw.setdefault("linewidth", 1.0)
            color = g.color or fv.NEUTRALS["baseline"]
            g.artist = ax.axline(
                (0.0, float(b)),
                slope=1.0,
                color=color,
                label=_legend_label(rec, g),
                **{
                    **kw,
                    **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid))),
                },
            )
            _mark(g.artist)
        return
    vert = d == "v"
    fn = ax.axvline if vert else ax.axhline
    # radar 面板的 v-ref：at 的 dim 名直接是角度位置，优先于数据列解释
    amap = ctx.angles.get(pid, {}) if (vert and ctx.polar.get(pid)) else {}
    axis = "x" if vert else "y"
    catmap, disp = (
        (None, [])
        if ctx.polar.get(pid)
        else _cat_map(ctx.panel_recs.get(pid, ()), axis)
    )
    seen = set()
    for g in rec.groups:
        raw_at = merged.get("at")
        if isinstance(raw_at, str) and raw_at in amap:
            at = amap[raw_at]
        else:
            at = _resolve_at(merged, g, rec, ctx, catmap)
            if vert and ctx.polar.get(pid):
                at = _to_angle(amap, at)
                if not _is_num(at):
                    raise SpecError(
                        f"series {rec.id}: ref at {raw_at!r} is not a "
                        f"dim or angle of radar panel {pid!r}"
                    )
            elif catmap is not None:
                at = _cat_lookup(at, catmap, disp, axis, rec.id, "ref")
        key = _pos_key(at)
        if key in seen:
            continue  # 'of'/'by' 扇出 + 字面 at：只画一次，不画 N 次
        seen.add(key)
        kw = _style_kwargs(g, merged)
        kw.setdefault(
            "linestyle",
            fv.line_styles(ctx.theme.line_preset)["reference"],
        )
        kw.setdefault("linewidth", 1.0)
        color = g.color or fv.NEUTRALS["baseline"]
        g.artist = fn(
            at,
            color=color,
            label=_legend_label(rec, g),
            **{**kw, **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))},
        )
        _mark(g.artist)


def _draw_span(ax, rec, ctx, pid):
    merged = rec.merged
    at = merged["at"]
    if not (isinstance(at, (list, tuple)) and len(at) == 2):
        raise SpecError(f"series {rec.id} (span): 'at' must be [lo, hi]")
    vert = merged.get("dir", "v") == "v"
    polar_v = vert and ctx.polar.get(pid, False)
    amap = ctx.angles.get(pid, {}) if polar_v else {}
    axis = "x" if vert else "y"
    catmap, disp = (
        (None, [])
        if ctx.polar.get(pid)
        else _cat_map(ctx.panel_recs.get(pid, ()), axis)
    )
    fn = ax.axvspan if vert else ax.axhspan
    seen = set()
    for g in rec.groups:
        ends = []
        for v in at:
            if polar_v and isinstance(v, str) and v in amap:
                ends.append(amap[v])
            else:
                e = _resolve_at_value(v, g, rec, ctx, catmap)
                if polar_v:
                    e = _to_angle(amap, e)
                elif catmap is not None:
                    e = _cat_lookup(e, catmap, disp, axis, rec.id, "span")
                ends.append(e)
        if polar_v and not all(_is_num(e) for e in ends):
            raise SpecError(
                f"series {rec.id}: span at {merged['at']!r} is not a pair "
                f"of dims or angles of radar panel {pid!r}"
            )
        key = (_pos_key(ends[0]), _pos_key(ends[1]))
        if key in seen:
            continue  # 'of'/'by' 扇出 + 字面 at：只画一次
        seen.add(key)
        color = g.color or fv.HUES["vgray"]
        g.artist = fn(
            ends[0],
            ends[1],
            color=color,
            alpha=merged.get("alpha", 0.10),
            label=_legend_label(rec, g),
            **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid))),
        )
        if merged.get("zorder") is not None:
            g.artist.set_zorder(merged["zorder"])
        _mark(g.artist)


_ROW_FIELD_RE = re.compile(r"\{([A-Za-z_]\w*)(?::([^{}]*))?\}")


def _row_text(template, row):
    """note 逐行扇出的文本模板：`{field}`/`{field:fmt}` 按行字段替换；
    不是行字段的占位（`{v}` 这类）原样保留，不吞用户的字面花括号。"""

    def sub(m):
        name, fmt = m.group(1), m.group(2)
        if name not in row:
            return m.group(0)
        v = row[name]
        if fmt is not None:
            try:
                return ("{:" + fmt + "}").format(v)
            except (ValueError, TypeError) as e:
                raise SpecError(
                    f"note text template {m.group(0)!r}: bad format spec ({e})"
                ) from e
        return str(v)

    return _ROW_FIELD_RE.sub(sub, str(template))


def _draw_note(ax, rec, ctx, pid):
    merged = rec.merged
    at = merged["at"]
    units = merged.get("units", "data")
    try:
        xycoords = (
            tuple(_UNITS[u] for u in units)
            if isinstance(units, (list, tuple))
            else _UNITS[units]
        )
    except KeyError as e:
        raise SpecError(
            f"series {rec.id} (note): bad units {e} (valid: {sorted(_UNITS)} or a pair)"
        ) from e
    to = merged.get("to")
    props = dict(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))
    upair = units if isinstance(units, (list, tuple)) else (units, units)
    if "figure" in upair:
        # figure 坐标的 annotate 仍挂在宿主 axes 上、计入其 tight bbox，
        # tight_layout 会把面板挤向画布边缘——figure 语义本就在版心外
        props.setdefault("in_layout", False)
    if merged.get("arrow"):
        props.setdefault(
            "arrowprops",
            {"arrowstyle": "->", "color": fv.NEUTRALS["vink"], "linewidth": 0.7},
        )
    if merged.get("zorder") is not None:
        props.setdefault("zorder", merged["zorder"])
    if isinstance(at, dict):
        # 逐行扇出（at:{x,y} 两列按行落位）：forest 右侧 est(CI) 文本列、
        # 逐点标注；text 里 {field}/{field:fmt} 按行替换；缺 x/y 的行跳过。
        # data 单位的字符串值经同面板类别轴解析（非 data 轴照旧报错）
        recs = ctx.panel_recs.get(pid, ())
        xmap, xdisp = _cat_map(recs, "x")
        ymap, ydisp = _cat_map(recs, "y")
        for g in rec.groups:
            xs = _vals(g.rows, at["x"], "at.x", rec.id)
            ys = _vals(g.rows, at["y"], "at.y", rec.id)
            if len(xs) != len(g.rows) or len(ys) != len(g.rows):
                raise SpecError(
                    f"series {rec.id} (note): at lists must align to "
                    f"{len(g.rows)} rows, got {len(xs)}/{len(ys)}"
                )
            p = dict(props)
            if g.color is not None:
                p.setdefault("color", g.color)
            miss, seen = 0, set()
            for r, xv, yv in zip(g.rows, xs, ys):
                if xv is None or yv is None:
                    miss += 1
                    continue
                if upair[0] == "data":
                    xv = _cat_lookup(xv, xmap, xdisp, "x", rec.id, "note")
                if upair[1] == "data":
                    yv = _cat_lookup(yv, ymap, ydisp, "y", rec.id, "note")
                if not (_is_num(xv) and _is_num(yv)):
                    raise SpecError(
                        f"series {rec.id} (note): fan-out at must resolve "
                        f"to numbers, got ({xv!r}, {yv!r})"
                    )
                txt = _row_text(merged["text"], r)
                key = (float(xv), float(yv), txt)
                if key in seen:
                    continue
                seen.add(key)
                g.artist = ax.annotate(
                    txt,
                    xy=(float(xv), float(yv)),
                    xycoords=xycoords,
                    xytext=to or (float(xv), float(yv)),
                    textcoords="offset points" if to else xycoords,
                    **p,
                )
                _mark(g.artist)
                rec.note_annots.append(g.artist)
            if miss:
                ctx.lint(
                    "missing-rows",
                    f"series {rec.id}: {miss} note rows carry missing "
                    f"at values (skipped at draw)",
                    pid,
                )
        return
    if not (isinstance(at, (list, tuple)) and len(at) == 2):
        raise SpecError(f"series {rec.id} (note): 'at' must be [x, y]")
    at = list(at)
    if ctx.polar.get(pid, False):
        at[0] = _to_angle(ctx.angles.get(pid, {}), at[0])
    else:
        # data 单位的字符串按同面板类别轴落槽（axes/figure 单位照旧报错）
        recs = ctx.panel_recs.get(pid, ())
        if upair[0] == "data":
            xmap, xdisp = _cat_map(recs, "x")
            at[0] = _cat_lookup(at[0], xmap, xdisp, "x", rec.id, "note")
        if upair[1] == "data":
            ymap, ydisp = _cat_map(recs, "y")
            at[1] = _cat_lookup(at[1], ymap, ydisp, "y", rec.id, "note")
    if not all(_is_num(v) for v in at):
        raise SpecError(
            f"series {rec.id} (note): 'at' must resolve to numbers, got {at!r}"
        )
    seen = set()
    for g in rec.groups:
        key = (repr(at), repr(to))
        if key in seen:
            continue  # 'of'/'by' 扇出 + 字面 at：只画一次
        seen.add(key)
        p = dict(props)
        if g.color is not None:
            p.setdefault("color", g.color)
        g.artist = ax.annotate(
            merged["text"],
            xy=at,
            xycoords=xycoords,
            xytext=to or at,
            textcoords="offset points" if to else xycoords,
            **p,
        )
        _mark(g.artist)
        rec.note_annots.append(g.artist)


def _donut_slice_color(cspec, lab, row, i, nrows, ctx, lint, sid):
    """donut 单切片的颜色解析——按 cspec 形态分派（palette 序 / 注册表 /
    field 逐行 / 类别映射 / 统一 token）。"""
    if cspec is None:
        if nrows > len(ctx.colors.palette):
            raise SpecError(
                f"series {sid}: {nrows} slices exceed palette "
                f"size {len(ctx.colors.palette)}"
            )
        return ctx.colors.palette_at(i)
    if isinstance(cspec, str) and cspec in ctx.colors.reg:
        return ctx.colors.registry(cspec, lab, lint)
    if isinstance(cspec, dict) and "field" in cspec:
        return ctx.colors.resolve(cspec, lint, rows=[row])[0]
    if (
        isinstance(cspec, dict)
        and "registry" not in cspec
        and "ramp" not in cspec
        and "palette" not in cspec
    ):
        hit = None
        for k, v in cspec.items():
            if _norm_key(k) == _norm_key(lab):
                hit = v
        if hit is None:
            raise SpecError(f"series {sid}: donut color map misses slice {lab!r}")
        return ctx.colors.token(hit, lint)
    return ctx.colors.resolve(cspec, lint)


def _draw_donut(ax, rec, ctx, pid):
    merged = rec.merged
    rows = [r for g in rec.groups for r in g.rows]
    labels = _vals(rows, merged.get("x"), "x", rec.id)
    vals = _vals(rows, merged.get("y"), "y", rec.id)
    keep = [
        i
        for i in range(min(len(rows), len(labels), len(vals)))
        if labels[i] is not None and vals[i] is not None
    ]
    rows = [rows[i] for i in keep]
    labels = [labels[i] for i in keep]
    vals = [vals[i] for i in keep]
    cspec = merged.get("color")
    lint = ctx.lint_proxy(pid)
    colors = [
        _donut_slice_color(cspec, lab, rows[i], i, len(rows), ctx, lint, rec.id)
        for i, lab in enumerate(labels)
    ]
    ec = merged.get("edgecolor")
    if ec is not None:
        ec = _edge_color(ec, ctx, lint, rec.id)
    res = ax.pie(
        vals,
        labels=labels if merged.get("labels", True) is True else None,
        colors=colors,
        autopct=merged.get("pct"),
        pctdistance=merged.get("pctdistance", 0.78),
        startangle=merged.get("startangle", 100),
        wedgeprops={
            "width": merged.get("width", 0.42),
            "edgecolor": ec if ec is not None else "white",
            "linewidth": 1.2,
        },
    )
    wedges = res[0]
    # autopct 标签压在扇区色上：mpl 默认墨色在深扇区上对比度不足——与
    # heat 格字同口径，按扇区底色在白/vink 里取 WCAG 对比度高者；外侧
    # labels（白底上）保持默认墨色不动。字色已由渲染器按扇底选过，
    # _mark 标中性让 low-contrast 跳过它（其 axes 底色近似对扇区字失效）。
    # res[2] 兼容两版返回形态：老版 3 元组 / mpl>=3.11 PieContainer
    # （无 __len__，autopct 缺省时 res[2] IndexError）
    try:
        autotexts = res[2]
    except IndexError:
        autotexts = ()
    for w, t in zip(wedges, autotexts):
        bg = fv._rel_luminance(to_rgba(w.get_facecolor()))
        t.set_color(
            "white"
            if _wcag_contrast(bg, 1.0) > _wcag_contrast(bg, _LUM_INK)
            else fv.NEUTRALS["vink"]
        )
        _mark(t)
    if ctx.theme.emphasis == "accent-first" and len(wedges) > 1:
        wedges[0].set_hatch("//")
    rec.handles = [
        Patch(facecolor=w.get_facecolor(), edgecolor="white", label=str(lab))
        for w, lab in zip(wedges, labels)
    ]


# ------------------------------------------------------------- 分布


def _num_vals(rows, spec, what, rec):
    """分布数值列：_vals 解析 → 丢 None（missing-rows 已按行报）→
    非数值响亮报错（np.histogram 的 TypeError 提前成 SpecError）。"""
    out, bad = [], 0
    for v in _vals(rows, spec, what, rec.id):
        if v is None:
            continue
        if _is_num(v):
            out.append(float(v))
        else:
            bad += 1
    if bad:
        raise SpecError(
            f"series {rec.id} ({rec.kind}): {what} {spec!r} resolved "
            f"{bad} non-numeric values — distribution kinds need numbers"
        )
    return out


def _draw_hist(ax, rec, ctx, pid):
    merged = rec.merged
    alpha = merged.get("alpha")
    if alpha is None:
        # 多组重叠：半透填充 + vink 细描边，交叠带仍读得出
        alpha = 0.55 if len(rec.groups) > 1 else 0.85
    kw = {
        "bins": merged.get("bins", "auto"),
        "range": merged.get("range"),
        "density": merged.get("density"),
        "cumulative": merged.get("cumulative"),
        "zorder": merged.get("zorder"),
        # dir:'h' = mpl orientation='horizontal'：bins 沿 y、计数沿 x
        # （joint 右侧边际，配 layout.bind axis:'y'）
        "orientation": "horizontal" if merged.get("dir") == "h" else None,
    }
    kw = {k: v for k, v in kw.items() if v is not None}
    for g in rec.groups:
        vals = _num_vals(g.rows, merged["x"], "x", rec)
        _, _, patches = ax.hist(
            vals,
            color=g.color,
            alpha=alpha,
            edgecolor=fv.NEUTRALS["vink"],
            linewidth=0.4,
            label=_legend_label(rec, g),
            **{**kw, **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))},
        )
        if isinstance(patches, (list, tuple)):
            g.artist = patches[0] if patches else None
        else:
            g.artist = patches


def _draw_ecdf(ax, rec, ctx, pid):
    merged = rec.merged
    horiz = merged.get("dir") == "h"
    for g in rec.groups:
        vals = sorted(_num_vals(g.rows, merged["x"], "x", rec))
        if not vals:
            continue
        # 右连续 ECDF：起笔 (x0, 0)，观测点处跳到 (i+1)/n；
        # dir:'h' 换轴（数据在 y、概率在 x）——原 steps-post 的「先平后跳」
        # 镜像成「先跳后平」= steps-pre
        xs = [vals[0], *vals]
        ys = [0.0] + [(i + 1) / len(vals) for i in range(len(vals))]
        kw = _style_kwargs(g, merged)
        kw.setdefault("drawstyle", "steps-pre" if horiz else "steps-post")
        g.artist = ax.plot(
            ys if horiz else xs,
            xs if horiz else ys,
            color=g.color,
            label=_legend_label(rec, g),
            **{**kw, **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))},
        )[0]


_KDE_BW_METHODS = ("scott", "silverman")
_KDE_GRID_N = 200
_KDE_CUT = 3.0  # 无 clip 时评估窗在数据两端各延 3 倍带宽（seaborn cut=3 同口径）


def _check_kde_params(merged, sid):
    """kde 的 bw/bw_adjust/grid/clip/fill 形态校验。"""
    bw = merged.get("bw", "scott")
    if isinstance(bw, str):
        if bw not in _KDE_BW_METHODS:
            raise SpecError(
                f"series {sid} (kde): bw must be 'scott'|'silverman' or a "
                f"positive number, got {bw!r}"
            )
    elif not (_is_num(bw) and bw > 0):
        raise SpecError(f"series {sid} (kde): bw must be a positive number, got {bw!r}")
    adj = merged.get("bw_adjust", 1.0)
    if not (_is_num(adj) and adj > 0):
        raise SpecError(
            f"series {sid} (kde): bw_adjust must be a positive number, got {adj!r}"
        )
    grid = merged.get("grid", _KDE_GRID_N)
    if _is_num(grid):
        if not (float(grid).is_integer() and grid >= 2):
            raise SpecError(
                f"series {sid} (kde): grid must be an int >= 2 or an "
                f"increasing array, got {grid!r}"
            )
    elif not (
        isinstance(grid, (list, tuple))
        and len(grid) >= 2
        and all(_is_num(v) for v in grid)
        and all(b > a for a, b in itertools.pairwise(grid))
    ):
        raise SpecError(
            f"series {sid} (kde): grid array must be >= 2 increasing "
            f"numbers, got {grid!r}"
        )
    clip = merged.get("clip")
    if clip is not None and not (
        isinstance(clip, (list, tuple))
        and len(clip) == 2
        and all(_is_num(v) for v in clip)
        and clip[0] < clip[1]
    ):
        raise SpecError(
            f"series {sid} (kde): clip must be [lo, hi] with lo < hi, got {clip!r}"
        )
    fill = merged.get("fill")
    if fill is not None and not (_is_num(fill) and 0 <= fill <= 1):
        raise SpecError(
            f"series {sid} (kde): fill must be an alpha in [0,1], got {fill!r}"
        )


def _kde_curve(vals, merged, sid):
    """-> (grid, dens)：gaussian KDE，scott/silverman 带宽 × bw_adjust。

    评估窗：`clip` 直接钉 [lo,hi]；否则数据两端各延 3·bw。`grid` 给点数
    （默认 200）或显式升序数组（数组 + clip 时按 clip 过滤，剩余 <2 点
    SpecError）。clip 只截断评估支撑、不改数据也不重归一——窗内曲线是
    真实密度的截段。
    """
    xs = np.asarray(vals, dtype=float)
    n = xs.size
    bw = merged.get("bw", "scott")
    if isinstance(bw, str):
        s = float(np.std(xs, ddof=1)) if n > 1 else 0.0
        h = s * (n**-0.2 if bw == "scott" else (0.75 * n) ** -0.2)
    else:
        h = float(bw)
    h *= float(merged.get("bw_adjust", 1.0))
    if not np.isfinite(h) or h <= 0:
        raise SpecError(
            f"series {sid} (kde): degenerate bandwidth — a constant or "
            f"single-point group has no density (use 'ecdf'/'scatter')"
        )
    g = merged.get("grid", _KDE_GRID_N)
    clip = merged.get("clip")
    if isinstance(g, (list, tuple)):
        grid = np.asarray(g, dtype=float)
    else:
        if clip is not None:
            lo, hi = float(clip[0]), float(clip[1])
        else:
            lo, hi = xs.min() - _KDE_CUT * h, xs.max() + _KDE_CUT * h
        grid = np.linspace(lo, hi, int(g))
    if clip is not None and isinstance(g, (list, tuple)):
        grid = grid[(grid >= clip[0]) & (grid <= clip[1])]
        if grid.size < 2:
            raise SpecError(f"series {sid} (kde): clip {clip} leaves <2 grid points")
    z = (grid[:, None] - xs[None, :]) / h
    dens = np.exp(-0.5 * z * z).sum(axis=1) / (n * h * np.sqrt(2.0 * np.pi))
    return grid, dens


def _draw_kde(ax, rec, ctx, pid):
    merged = rec.merged
    # dir:'h'：数据值在 y 轴、密度沿 x（joint 右侧边际，bind axis:'y'）
    horiz = merged.get("dir") == "h"
    for g in rec.groups:
        vals = _num_vals(g.rows, merged["x"], "x", rec)
        if not vals:
            continue  # 全 None 组——missing-rows/empty-series 已报过
        grid, dens = _kde_curve(vals, merged, rec.id)
        kw = _style_kwargs(g, merged)
        g.artist = ax.plot(
            dens if horiz else grid,
            grid if horiz else dens,
            color=g.color,
            label=_legend_label(rec, g),
            **{**kw, **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))},
        )[0]
        if merged.get("fill"):
            fill = (
                ax.fill_betweenx(grid, 0.0, dens)
                if horiz
                else ax.fill_between(grid, 0.0, dens)
            )
            fill.set(color=g.color, alpha=merged["fill"], linewidth=0)
            _mark(fill)


def _dist_groups(rec, merged):
    """box/violin 逐组数值列 + positions/widths 按非空组对齐过滤。"""
    pos = merged.get("positions") or list(range(1, len(rec.groups) + 1))
    data, kept, kept_pos, kept_idx = [], [], [], []
    for i, (g, p) in enumerate(zip(rec.groups, pos)):
        vals = _num_vals(g.rows, merged["y"], "y", rec)
        if not vals:
            continue  # 全 None 组——missing-rows 已在 prepare 报过
        kept_idx.append(i)
        kept.append(g)
        data.append(vals)
        kept_pos.append(p)
    kw = {}
    w = merged.get("widths")
    if w is not None:
        kw["widths"] = [w[i] for i in kept_idx] if isinstance(w, (list, tuple)) else w
    # box 的 zorder 走 boxplot 形参；violin 收 dict of collections 后逐件设
    if rec.kind == "box" and merged.get("zorder") is not None:
        kw["zorder"] = merged["zorder"]
    return data, kept, kept_pos, kw


def _dist_ticks(ax, kept, ppos, horiz=False):
    """box/violin 的组刻度归 kind 层所有：位置 + 组名（label 或原始键）；
    dir:'h'（mpl orientation='horizontal'）时组位置在 y 轴。"""
    labels = [g.label or (str(g.raw) if g.raw is not None else "") for g in kept]
    if horiz:
        ax.set_yticks(ppos, labels)
    else:
        ax.set_xticks(ppos, labels)


def _draw_box(ax, rec, ctx, pid):
    merged = rec.merged
    horiz = merged.get("dir") == "h"
    data, kept, ppos, kw = _dist_groups(rec, merged)
    if not data:
        return
    bxp = ax.boxplot(
        data,
        positions=ppos,
        patch_artist=True,
        showfliers=merged.get("fliers", True),
        **{
            "orientation": "horizontal" if horiz else "vertical",
            **kw,
            **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid))),
        },
    )
    ink = fv.NEUTRALS["vink"]
    alpha = merged.get("alpha", 0.55)
    # 整枚箱线图是一个复合 glyph：须线/帽/中位/离群点全是结构件，
    # gid fv-neutral 豁免 audit 的 series 计数（箱体 PathPatch 同理）
    for key in ("whiskers", "caps", "medians", "means"):
        for art in bxp.get(key) or []:
            art.set_color(ink)
            art.set_linewidth(0.7)
            _mark(art)
    for art in bxp.get("fliers") or []:
        art.set(
            color=ink,
            markeredgecolor=ink,
            markerfacecolor="none",
            markersize=2.6,
            markeredgewidth=0.5,
        )
        _mark(art)
    for patch, g in zip(bxp["boxes"], kept):
        patch.set_facecolor(to_rgba(g.color or fv.HUES["vgray"], alpha))
        patch.set_edgecolor(ink)
        patch.set_linewidth(0.7)
        lab = _legend_label(rec, g)
        if lab is not None:
            patch.set_label(lab)
        _mark(patch)
        g.artist = patch
    _dist_ticks(ax, kept, ppos, horiz)


def _draw_violin(ax, rec, ctx, pid):
    merged = rec.merged
    horiz = merged.get("dir") == "h"
    data, kept, ppos, kw = _dist_groups(rec, merged)
    if not data:
        return
    kw.setdefault("showmedians", True)
    res = ax.violinplot(
        data,
        positions=ppos,
        **{
            "orientation": "horizontal" if horiz else "vertical",
            **kw,
            **(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid))),
        },
    )
    if merged.get("zorder") is not None:
        for part in res.values():
            for c in part if isinstance(part, (list, tuple)) else [part]:
                if c is not None:
                    c.set_zorder(merged["zorder"])
    ink = fv.NEUTRALS["vink"]
    alpha = merged.get("alpha", 0.55)
    for key in ("cmaxes", "cmins", "cbars", "cmeans", "cmedians"):
        coll = res.get(key)
        if coll is not None:
            coll.set_color(ink)
            coll.set_linewidth(0.7)
            _mark(coll)
    for body, g in zip(res["bodies"], kept):
        body.set_facecolor(to_rgba(g.color or fv.HUES["vgray"], alpha))
        body.set_edgecolor(ink)
        body.set_linewidth(0.5)
        lab = _legend_label(rec, g)
        if lab is not None:
            body.set_label(lab)
        _mark(body)
        g.artist = body
    if merged.get("inner") == "points":
        # 确定性等距 jitter（可复现，不引随机源）；点叠在箱体轮廓之上；
        # dir:'h' 时数据值在 x 轴、组位置在 y 轴
        for g, p in zip(kept, ppos):
            vals = _num_vals(g.rows, merged["y"], "y", rec)
            jit = (
                np.full(len(vals), float(p))
                if len(vals) == 1
                else p + np.linspace(-0.18, 0.18, len(vals))
            )
            sc = ax.scatter(
                vals if horiz else jit,
                jit if horiz else vals,
                s=4.5,
                color=ink,
                alpha=0.45,
                linewidths=0,
            )
            _mark(sc)
    _dist_ticks(ax, kept, ppos, horiz)


def _heat_cells(merged, rec):
    """-> (xcats, ycats, zmat)：matrix 直给与长表 {x,y,z} 透视归一成同一矩阵。

    长表语义与 bar 一致：类别按首见序、全数值则升序；`xlabels`/`ylabels`
    作顺序钉（列出的类别先排、未列出的按原序追加——与 by.order 同口径）。
    重复 (x,y) 格与非数值 z 响亮报错；缺 (x,y) 组合与 None z 落 NaN 格。
    """
    if "matrix" in merged:
        mat = merged["matrix"]
        zmat = np.asarray(
            [[np.nan if v is None else float(v) for v in row] for row in mat],
            dtype=float,
        )
        ny, nx = zmat.shape
        xcats = list(merged.get("xlabels") or range(nx))
        ycats = list(merged.get("ylabels") or range(ny))
        return xcats, ycats, zmat
    sid = rec.id
    xcol, ycol, zcol = merged["x"], merged["y"], merged["z"]
    rows = [r for g in rec.groups for r in g.rows]
    keyset = {k for r in rows for k in r}
    for f in (xcol, ycol, zcol):
        if rows and all(f not in r for r in rows):
            raise SpecError(
                f"series {sid} (heat): {f!r} is not a data column{_hint(f, keyset)}"
            )
    cellz, xraw, yraw = {}, {}, {}
    xcats, ycats = [], []
    for r in rows:
        xv, yv, zv = r.get(xcol), r.get(ycol), r.get(zcol)
        if xv is None or yv is None:
            continue  # 缺类别字段的行不构格——missing-rows 已先行计数
        if zv is not None and not _is_num(zv):
            raise SpecError(
                f"series {sid} (heat): z value {zv!r} is non-numeric — "
                f"cells need numbers"
            )
        xk, yk = _norm_key(xv), _norm_key(yv)
        if (xk, yk) in cellz:
            raise SpecError(
                f"series {sid} (heat): duplicate cell ({xv!r}, {yv!r}) — "
                f"aggregate upstream before the spec"
            )
        cellz[(xk, yk)] = zv
        if xk not in xraw:
            xraw[xk] = xv
            xcats.append(xk)
        if yk not in yraw:
            yraw[yk] = yv
            ycats.append(yk)
    if all(_is_num(c) for c in xcats):
        xcats.sort()
    if all(_is_num(c) for c in ycats):
        ycats.sort()
    for name, cats in (("xlabels", xcats), ("ylabels", ycats)):
        pin = merged.get(name)
        if pin is None:
            continue
        want = list(dict.fromkeys(_norm_key(v) for v in pin))
        ordered = [c for w in want for c in cats if c == w]
        ordered += [c for c in cats if c not in want]
        cats[:] = ordered
    zmat = np.full((len(ycats), len(xcats)), np.nan)
    xi = {c: i for i, c in enumerate(xcats)}
    yi = {c: i for i, c in enumerate(ycats)}
    for (xk, yk), zv in cellz.items():
        if zv is not None:
            zmat[yi[yk], xi[xk]] = zv
    return [xraw[c] for c in xcats], [yraw[c] for c in ycats], zmat


def _heat_cmap(name, sid, kind="heat"):
    """cmap 解析——薄壳调 fvstyle.ramp_cmap（公开色带 API），heat 与场族
    共用；其 ValueError 翻成 SpecError 保持 spec 报错口径；prepare 的
    kind 校验已先拦未知名，这里是防线。"""
    try:
        return fv.ramp_cmap(name)
    except ValueError:
        raise SpecError(f"series {sid} ({kind}): unknown cmap {name!r}") from None


def _heat_norm(merged, zmat, sid, kind="heat"):
    """div/显式 vcenter -> TwoSlopeNorm；div 取 vcenter 对称窗口（seaborn
    center= 同口径，保证两端色程等长）；其余 None 交给 mpl autoscale。"""
    vc = merged.get("vcenter")
    div = merged.get("cmap", "seq") == "div"
    if not div and vc is None:
        return None
    finite = zmat[np.isfinite(zmat)]
    zmin = float(finite.min()) if finite.size else 0.0
    zmax = float(finite.max()) if finite.size else 1.0
    if div:
        vc = 0.0 if vc is None else float(vc)
        half = max(abs(zmax - vc), abs(zmin - vc)) or 1.0
        return TwoSlopeNorm(vcenter=vc, vmin=vc - half, vmax=vc + half)
    vc = float(vc)
    if not zmin < vc < zmax:
        raise SpecError(
            f"series {sid} ({kind}): vcenter {vc:g} outside data range "
            f"[{zmin:g}, {zmax:g}] — a centered norm needs data "
            f"straddling the center"
        )
    return TwoSlopeNorm(vcenter=vc, vmin=zmin, vmax=zmax)


def _heat_fmt(v):
    """annotate:true 的默认格值格式：整数按原样（confusion 计数），
    其余取三位有效数字（win-rate/correlation）。"""
    return f"{v:g}" if float(v).is_integer() else f"{v:.3g}"


def _wcag_contrast(l1, l2):
    """WCAG 相对亮度对比度 (L_hi+0.05)/(L_lo+0.05)。"""
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _draw_heat(ax, rec, ctx, pid):
    merged = rec.merged
    xcats, ycats, zmat = _heat_cells(merged, rec)
    ny, nx = zmat.shape
    if not nx or not ny:
        return  # 无格可画——empty-series lint 已报过
    cmap = _copy.copy(_heat_cmap(merged.get("cmap", "seq"), rec.id))
    # 缺格画成 mist：空洞可见但不冒充数据色（拷贝后 set_bad 不污染注册板）
    cmap.set_bad(fv.NEUTRALS["vmist"])
    norm = _heat_norm(merged, zmat, rec.id)
    kw = {"cmap": cmap, "edgecolors": "white", "linewidth": 0.5}
    if norm is not None:
        kw["norm"] = norm
    for f in ("alpha", "zorder"):
        if merged.get(f) is not None:
            kw[f] = merged[f]
    kw.update(_resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid)))
    mesh = ax.pcolormesh(np.arange(nx + 1), np.arange(ny + 1), zmat, **kw)
    if rec.groups:
        rec.groups[0].artist = mesh
    ax.set_xlim(0, nx)
    ax.set_ylim(ny, 0)  # 行 0 在顶——矩阵/表格的阅读序
    ax.set_xticks(np.arange(nx) + 0.5, [str(c) for c in xcats])
    ax.set_yticks(np.arange(ny) + 0.5, [str(c) for c in ycats])
    _field_colorbar(ax, mesh, merged, ctx, ctx.lint_proxy(pid))
    ann = merged.get("annotate", False)
    if ann is True:
        fmt = _heat_fmt
    elif isinstance(ann, str):

        def fmt(v):
            return ann.format(v=v)

    else:
        fmt = None
    if fmt is not None:
        mesh.norm.autoscale_None(np.ma.masked_invalid(zmat))
        fs = plt.rcParams["font.size"] - 1.2
        for iy in range(ny):
            for ix in range(nx):
                v = zmat[iy, ix]
                if not np.isfinite(v):
                    continue
                # 按格底 WCAG 对比度在黑/白里取高者——旧的单向亮度阈值
                # 0.18 低于内置 seq/div 端点（vteal≈0.240），最深格永远切
                # 不到白字；双向取大后 vteal 底配白字 ~3.6:1 > vink ~3.0:1
                bg = fv._rel_luminance(mesh.cmap(mesh.norm(v)))
                ink = (
                    "white"
                    if _wcag_contrast(bg, 1.0) > _wcag_contrast(bg, _LUM_INK)
                    else fv.NEUTRALS["vink"]
                )
                t = ax.text(
                    ix + 0.5,
                    iy + 0.5,
                    fmt(v),
                    ha="center",
                    va="center",
                    fontsize=fs,
                    color=ink,
                )
                _mark(t)


def _field_grid(merged, rec, cols, sid, kind):
    """-> (xs, ys, {col: (ny,nx) 网格})：场族长表按数值 (x,y) 透视成规则
    网格。与 _heat_cells 的差别：x/y 是真实坐标——必须数值、按升序、
    非等距照收（类别网格是 heat 语义）；重复格与缺列响亮报错。"""
    xcol, ycol = merged["x"], merged["y"]
    rows = [r for g in rec.groups for r in g.rows]
    keyset = {k for r in rows for k in r}
    for f in (xcol, ycol, *cols):
        if rows and all(f not in r for r in rows):
            raise SpecError(
                f"series {sid} ({kind}): {f!r} is not a data column{_hint(f, keyset)}"
            )
    cell, xset, yset = {}, set(), set()
    for r in rows:
        xv, yv = r.get(xcol), r.get(ycol)
        if xv is None or yv is None:
            continue  # 缺坐标字段的行不构格——missing-rows 已先行计数
        if not (_is_num(xv) and _is_num(yv)):
            raise SpecError(
                f"series {sid} ({kind}): grid coordinates must be numeric, "
                f"got ({xv!r}, {yv!r}) — categorical grids are heat semantics"
            )
        key = (float(xv), float(yv))
        if key in cell:
            raise SpecError(
                f"series {sid} ({kind}): duplicate cell ({xv!r}, {yv!r}) — "
                f"aggregate upstream before the spec"
            )
        vals = []
        for c in cols:
            v = r.get(c)
            if v is not None and not _is_num(v):
                raise SpecError(
                    f"series {sid} ({kind}): {c!r} value {v!r} is non-numeric"
                )
            vals.append(v)
        cell[key] = vals
        xset.add(float(xv))
        yset.add(float(yv))
    xs, ys = sorted(xset), sorted(yset)
    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: i for i, y in enumerate(ys)}
    grids = {}
    for k, c in enumerate(cols):
        g = np.full((len(ys), len(xs)), np.nan)
        for (xv, yv), vals in cell.items():
            if vals[k] is not None:
                g[yi[yv], xi[xv]] = float(vals[k])
        grids[c] = g
    return np.asarray(xs), np.asarray(ys), grids


def _contour_levels(merged, zmat, sid):
    """levels 解析：None 交 mpl（MaxNLocator nice levels）、int>=2 直接给
    contour、显式数组照收；'log'/{'log':n} 在 [zmin,zmax] 等比取样。"""
    lv = merged.get("levels")
    if lv is None:
        return None
    if _is_num(lv):
        return int(lv)
    if isinstance(lv, (list, tuple)):
        return np.asarray(lv, dtype=float)
    finite = zmat[np.isfinite(zmat)]
    if not finite.size:
        raise SpecError(f"series {sid} (contour): no finite z values for levels")
    lo, hi = float(finite.min()), float(finite.max())
    n = 10 if lv == "log" else int(lv["log"])
    if lo <= 0:
        raise SpecError(
            f"series {sid} (contour): 'log' levels need zmin > 0, got {lo:g}"
        )
    if not lo < hi:
        raise SpecError(
            f"series {sid} (contour): 'log' levels need a z range, got constant {lo:g}"
        )
    return np.geomspace(lo, hi, n)


def _field_view_pad(ax, xs, ys):
    """contourf/streamplot 会把轴限钉死在场域边界（普通 artist 的 5%
    autoscale 边距不生效）——按 axes.xmargin/ymargin 补齐同样口径的
    视野余量；用户在 xaxis/yaxis.lim 显式定限时其后 _apply_axis 覆盖。"""
    mx = float(plt.rcParams.get("axes.xmargin", 0.05))
    my = float(plt.rcParams.get("axes.ymargin", 0.05))
    x0, x1 = float(xs[0]), float(xs[-1])
    y0, y1 = float(ys[0]), float(ys[-1])
    px = mx * (x1 - x0) if x1 > x0 else 0.5
    py = my * (y1 - y0) if y1 > y0 else 0.5
    ax.set_xlim(x0 - px, x1 + px)
    ax.set_ylim(y0 - py, y1 + py)


def _draw_clabel(ax, cs, merged, ctx, sid, lint):
    """clabel 落盘：true 用 mpl 默认；dict 的 levels 取 'all'|步长|显式子集
    （须 ⊆ 实际画的层），fmt 支持 mpl 格式串、'{v:...}' 逐层渲染模板与
    {level: label} dict。标签文字 vink 上墨并 _mark 为中性覆盖层。"""
    cl = merged.get("clabel")
    if cl is None or cl is False:
        return
    if cl is True:
        texts = ax.clabel(cs, colors=[fv.NEUTRALS["vink"]])
        _mark(*texts)
        return
    kw = {"colors": [fv.NEUTRALS["vink"]]}
    drawn = [float(v) for v in cs.levels]
    sub = cl.get("levels", "all")
    if isinstance(sub, (list, tuple)):
        want = [float(v) for v in sub]
        missing = [v for v in want if v not in drawn]
        if missing:
            raise SpecError(
                f"series {sid} (contour): clabel.levels {missing} not among "
                f"the drawn levels {drawn}"
            )
        kw["levels"] = want
    elif _is_num(sub):
        kw["levels"] = drawn[:: int(sub)]
    fmt = cl.get("fmt")
    if isinstance(fmt, str) and "{v" in fmt:
        kw["fmt"] = {v: fmt.format(v=v) for v in drawn}
    elif fmt is not None:
        kw["fmt"] = fmt
    if cl.get("fontsize") is not None:
        kw["fontsize"] = cl["fontsize"]
    man = cl.get("manual")
    if man is not None:
        # manual 与 levels 互斥（check 期已拦）：手工点位对所有画出的层生效
        kw["manual"] = [tuple(float(v) for v in p) for p in man]
    kw.update(_resolve_props(cl.get("props"), ctx, lint))
    texts = ax.clabel(cs, **kw)
    _mark(*texts)


def _contour_axis(lab, n):
    """matrix 直给的坐标轴 → (位置数组, 类别标签|None)：None → 0..n-1
    数值；全数值 → 真实坐标数组；非数值 → 类别槽位 0..n-1 + 原串刻度
    标签（类别坐标按位等距）。"""
    if lab is None:
        return np.arange(n, dtype=float), None
    if all(_is_num(v) for v in lab):
        return np.asarray(lab, dtype=float), None
    return np.arange(n, dtype=float), lab


def _draw_contour(ax, rec, ctx, pid):
    """contour：数值坐标场上的等值面/线。mode 'fill'（默认）| 'lines' |
    'fill+lines'（色面 + vink 细描线供 clabel 挂靠）；z 缺格 mask 成
    mist 坏色，cmap/vcenter/cbar 与 heat 同口径。matrix 的类别标签轴
    按位等距映射槽位并把原串写回刻度。"""
    merged = rec.merged
    sid = rec.id
    xcats = ycats = None
    if "matrix" in merged:
        mat = merged["matrix"]
        zmat = np.asarray(
            [[np.nan if v is None else float(v) for v in row] for row in mat],
            dtype=float,
        )
        ny, nx = zmat.shape
        xs, xcats = _contour_axis(merged.get("xlabels"), nx)
        ys, ycats = _contour_axis(merged.get("ylabels"), ny)
    else:
        xs, ys, grids = _field_grid(merged, rec, (merged["z"],), sid, "contour")
        zmat = grids[merged["z"]]
    if not zmat.size or not np.isfinite(zmat).any():
        return  # 无格可画——empty-series/missing-rows lint 已报过
    if min(zmat.shape) < 2:
        raise SpecError(
            f"series {sid} (contour): grid is {zmat.shape[1]}x{zmat.shape[0]} "
            f"— contouring needs >=2 distinct coordinates per axis"
        )
    zmask = np.ma.masked_invalid(zmat)
    levels = _contour_levels(merged, zmat, sid)
    cmap = _copy.copy(_heat_cmap(merged.get("cmap", "seq"), sid, "contour"))
    cmap.set_bad(fv.NEUTRALS["vmist"])
    norm = _heat_norm(merged, zmat, sid, "contour")
    kw = {
        "levels": levels,
        "cmap": cmap,
        "norm": norm,
        "zorder": merged.get("zorder", _FIELD_ZORDER),
        "alpha": merged.get("alpha"),
    }
    kw = {k: v for k, v in kw.items() if v is not None}
    props = _resolve_props(merged.get("props"), ctx, ctx.lint_proxy(pid))
    mode = merged.get("mode", "fill")
    art, cs_lines = None, None
    if mode in ("fill", "fill+lines"):
        art = ax.contourf(xs, ys, zmask, **{**kw, **props})
    if mode == "lines":
        art = ax.contour(xs, ys, zmask, **{**kw, **props})
        cs_lines = art
    elif mode == "fill+lines":
        # 描线层：跟随填充实际画的层，vink 细线浮在色面上方一点——纯
        # 覆盖墨（fv-neutral），不算数据系列也不进图例
        cs_lines = ax.contour(
            xs,
            ys,
            zmask,
            levels=list(art.levels),
            colors=[fv.NEUTRALS["vink"]],
            linewidths=0.35,
            alpha=0.55,
            zorder=kw["zorder"] + 0.1,
        )
        _mark(cs_lines)
    if rec.groups:
        g = rec.groups[0]
        g.artist = art
        lbl = _legend_label(rec, g)
        if lbl:
            art.set_label(lbl)
    _field_view_pad(ax, xs, ys)
    # 类别标签轴：槽位坐标已按位等距布好，把原串写回刻度（与 bar/heat
    # 同口径——刻度归 kind 层所有）
    if xcats is not None:
        ax.set_xticks(xs.tolist(), [str(v) for v in xcats])
    if ycats is not None:
        ax.set_yticks(ys.tolist(), [str(v) for v in ycats])
    _field_colorbar(ax, art, merged, ctx, ctx.lint_proxy(pid))
    if cs_lines is not None:
        _draw_clabel(ax, cs_lines, merged, ctx, sid, ctx.lint_proxy(pid))


def _require_uniform_axis(arr, col, sid):
    """streamplot 的 Grid 要求轴等距（allclose(diff, 均值步长)，与 mpl
    同口径）——长表经 CSV round-trip（%.6g 截断）常把等距坐标写得微不
    齐，在这里把 mpl 的裸 ValueError 换成点名罪魁列与期望步长的
    SpecError。"""
    d = np.diff(arr)
    step = (arr[-1] - arr[0]) / (len(arr) - 1)
    if not np.allclose(d, step):
        raise SpecError(
            f"series {sid} (quiver): mode:'stream' requires an evenly "
            f"spaced grid — column {col!r} steps vary "
            f"[{float(d.min()):g}..{float(d.max()):g}] vs expected "
            f"≈{float(step):g}; a CSV round-trip truncating precision is "
            f"the usual cause — write integer grid coords or repr() "
            f"precision floats in the glue script"
        )


def _draw_quiver(ax, rec, ctx, pid):
    """quiver：mode 'arrows'（默认）逐行向量，位置任意（scatter 同口径）；
    mode 'stream' 把 {x,y,u,v[,m]} 透视成网格喂 streamplot（缺格 NaN，
    网格轴必须等距——非等距由 _require_uniform_axis 响亮报错）。
    'm' 是 cmap 载体——m 缺省时回退系列色。"""
    merged = rec.merged
    sid = rec.id
    mode = merged.get("mode", "arrows")
    lint = ctx.lint_proxy(pid)
    props = _resolve_props(merged.get("props"), ctx, lint)
    z = merged.get("zorder", _FIELD_ZORDER)
    mcol = merged.get("m")
    g = rec.groups[0] if rec.groups else None
    if mode == "stream":
        cols = [merged["u"], merged["v"]] + ([mcol] if mcol else [])
        xs, ys, grids = _field_grid(merged, rec, cols, sid, "quiver")
        if not len(xs) or not len(ys):
            return  # 无格可画——empty-series/missing-rows lint 已报过
        if len(xs) < 2 or len(ys) < 2:
            raise SpecError(
                f"series {sid} (quiver): mode:'stream' needs a >=2x2 grid, "
                f"got {len(xs)}x{len(ys)} — per-row vectors use mode:'arrows'"
            )
        _require_uniform_axis(xs, merged["x"], sid)
        _require_uniform_axis(ys, merged["y"], sid)
        kw = {
            "density": merged.get("density", 1.0),
            "arrowsize": merged.get("arrowsize", 1.0),
        }
        if merged.get("linewidth") is not None:
            kw["linewidth"] = merged["linewidth"]
        if mcol:
            cmap = _copy.copy(_heat_cmap(merged.get("cmap", "seq"), sid, "quiver"))
            cmap.set_bad(fv.NEUTRALS["vmist"])
            kw["color"] = np.ma.masked_invalid(grids[mcol])
            kw["cmap"] = cmap
            norm = _heat_norm(merged, grids[mcol], sid, "quiver")
            if norm is not None:
                kw["norm"] = norm
        else:
            kw["color"] = g.color if g is not None and g.color else fv.HUES["vteal"]
        kw.update(props)
        ss = ax.streamplot(
            xs,
            ys,
            np.ma.masked_invalid(grids[merged["u"]]),
            np.ma.masked_invalid(grids[merged["v"]]),
            **kw,
        )
        # streamplot 没有 zorder/alpha/label 形参——逐部件后设
        ss.lines.set_zorder(z)
        ss.arrows.set_zorder(z + 0.05)
        _field_view_pad(ax, xs, ys)
        if merged.get("alpha") is not None:
            ss.lines.set_alpha(merged["alpha"])
            ss.arrows.set_alpha(merged["alpha"])
        if g is not None:
            label = _legend_label(rec, g)
            if label:
                ss.lines.set_label(label)
            g.artist = ss.lines
        if mcol:
            _field_colorbar(ax, ss.lines, merged, ctx, lint)
        return
    # mode 'arrows'
    if g is None or not g.rows:
        return  # 无行可画——empty-series lint 已报过
    xs = _vals(g.rows, merged["x"], "x", sid)
    ys = _vals(g.rows, merged["y"], "y", sid)
    us = _vals(g.rows, merged["u"], "u", sid)
    vs = _vals(g.rows, merged["v"], "v", sid)
    ms = _vals(g.rows, mcol, "m", sid) if mcol else None
    drawn = []
    for i in range(len(g.rows)):
        quad = (xs[i], ys[i], us[i], vs[i])
        if any(v is None for v in quad):
            continue  # 缺字段行不画——missing-rows 已先行计数
        if not all(_is_num(v) for v in quad):
            raise SpecError(
                f"series {sid} (quiver): x/y/u/v need numbers, got {quad!r}"
            )
        drawn.append(i)
    if mcol:
        for i in drawn:
            if ms[i] is not None and not _is_num(ms[i]):
                raise SpecError(
                    f"series {sid} (quiver): 'm' value {ms[i]!r} is non-numeric"
                )
    if not drawn:
        return
    kw = {"zorder": z}
    if merged.get("scale") is not None:
        kw["scale"] = merged["scale"]
    if merged.get("pivot") is not None:
        kw["pivot"] = "middle" if merged["pivot"] == "mid" else merged["pivot"]
    if merged.get("alpha") is not None:
        kw["alpha"] = merged["alpha"]
    if mcol:
        mv = np.ma.masked_array(
            [ms[i] if _is_num(ms[i]) else np.nan for i in drawn],
            mask=[not _is_num(ms[i]) for i in drawn],
        )
        cmap = _copy.copy(_heat_cmap(merged.get("cmap", "seq"), sid, "quiver"))
        cmap.set_bad(fv.NEUTRALS["vmist"])
        kw["cmap"] = cmap
        norm = _heat_norm(
            merged, np.asarray(mv.filled(np.nan), dtype=float), sid, "quiver"
        )
        if norm is not None:
            kw["norm"] = norm
        kw["label"] = _legend_label(rec, g)
        q = ax.quiver(
            [xs[i] for i in drawn],
            [ys[i] for i in drawn],
            [us[i] for i in drawn],
            [vs[i] for i in drawn],
            mv,
            **{**kw, **props},
        )
        _field_colorbar(ax, q, merged, ctx, lint)
    else:
        kw["color"] = g.color
        kw["label"] = _legend_label(rec, g)
        q = ax.quiver(
            [xs[i] for i in drawn],
            [ys[i] for i in drawn],
            [us[i] for i in drawn],
            [vs[i] for i in drawn],
            **{**kw, **props},
        )
    g.artist = q


def _load_image(src, ctx, sid):
    """-> ndarray：str 当文件路径（相对 spec 目录；'.npy' 走 np.load，
    其余 plt.imread——csv 路径同口径的 SpecError）；数组原样进。
    解不出 2-D/3-D 数组响亮报错。"""
    if isinstance(src, str):
        path = Path(src)
        if not path.is_absolute():
            path = Path(ctx.base_dir or ".") / path
        try:
            arr = np.load(path) if path.suffix == ".npy" else plt.imread(path)
        except OSError as e:
            raise SpecError(
                f"series {sid} (image): cannot read {path}: {e.strerror or e}"
            ) from e
        except ValueError as e:
            raise SpecError(f"series {sid} (image): cannot decode {path}: {e}") from e
    else:
        arr = np.asarray(src)
    if arr.ndim not in (2, 3):
        raise SpecError(
            f"series {sid} (image): source {src!r} must decode to a 2-D "
            f"or 3-D array, got shape {arr.shape}"
        )
    if arr.ndim == 3 and arr.shape[2] not in (3, 4):
        raise SpecError(
            f"series {sid} (image): RGB arrays need 3 or 4 channels, "
            f"got shape {arr.shape}"
        )
    return arr


def _image_mist_cell():
    """缺源占位格：单像素 mist 色图——空洞可见但不冒充数据图（heat 缺格
    cmap.set_bad(vmist) 同约定）。"""
    rgb = to_rgba(fv.NEUTRALS["vmist"])[:3]
    return np.broadcast_to(np.array(rgb), (1, 1, 3)).copy()


_BADGE_ANCHOR = {  # corner -> (x-frac, y-frac, ha, va)：extent/axes 内缩锚点
    "bl": (0.04, 0.05, "left", "bottom"),
    "br": (0.96, 0.05, "right", "bottom"),
    "tl": (0.04, 0.95, "left", "top"),
    "tr": (0.96, 0.95, "right", "top"),
}


def _draw_image_badge(ax, badge, row, extent, sid):
    """角标：extent 角的数据坐标锚点（extent 缺省则 axes 角）+ 半透明
    黑底白字——图版 cell 的 per-row 元数据（方法名/指标值）。"""
    fmt = badge.get("fmt", "{v:.3g}")
    v = row.get(badge["field"])
    try:
        text = fmt.format(v=v)
    except Exception as e:
        raise SpecError(
            f"series {sid} (image): badge.fmt {fmt!r} failed on {v!r}: {e}"
        ) from e
    fx, fy, ha, va = _BADGE_ANCHOR[badge.get("corner", "bl")]
    kw = {
        "ha": ha,
        "va": va,
        "fontsize": plt.rcParams["font.size"] - 1.6,
        "color": "white",
        "bbox": {
            "facecolor": "black",
            "alpha": 0.55,
            "pad": 1.4,
            "edgecolor": "none",
        },
    }
    if extent is not None:
        x0, x1, y0, y1 = extent
        txt = ax.text(x0 + fx * (x1 - x0), y0 + fy * (y1 - y0), text, **kw)
    else:
        txt = ax.text(fx, fy, text, transform=ax.transAxes, **kw)
    _mark(txt)


def _draw_image(ax, rec, ctx, pid):
    """image：每行一张 imshow——'file' 列（格值 = 路径/.npy/数组）、'path'
    字面文件或 'rgb' 字面数组，三形互斥已在 prepare 校验。2-D 数组走
    cmap/vcenter/cbar 三件套（heat 同口径、NaN 落 mist 坏色），3-D 自带
    颜色拒收三件套；'file' 格值 None 画 mist 占位格。extent 对齐外部
    网格——heat 叠图配方 (0,n,n,0) + origin 'upper' 落 pcolormesh 格心。
    """
    merged = rec.merged
    sid = rec.id
    lint = ctx.lint_proxy(pid)
    props = _resolve_props(merged.get("props"), ctx, lint)
    extent = merged.get("extent")
    badge = merged.get("badge")
    fcol = merged.get("file")
    rows = [r for g in rec.groups for r in g.rows]
    if fcol is None:
        srcs = [merged.get("path", merged.get("rgb"))]
    else:
        if rows and all(fcol not in r for r in rows):
            keyset = {k for r in rows for k in r}
            raise SpecError(
                f"series {sid} (image): {fcol!r} is not a data column"
                f"{_hint(fcol, keyset)}"
            )
        srcs = [r.get(fcol) for r in rows]
    g = rec.groups[0] if rec.groups else None
    badge_miss = 0
    for i, src in enumerate(srcs):
        # 缺源行画 mist 占位格——missing-rows 已先行计数
        arr = _image_mist_cell() if src is None else _load_image(src, ctx, sid)
        kw = {}
        if arr.ndim == 2:
            cmap = _copy.copy(_heat_cmap(merged.get("cmap", "seq"), sid, "image"))
            cmap.set_bad(fv.NEUTRALS["vmist"])
            kw["cmap"] = cmap
            norm = _heat_norm(merged, np.asarray(arr, dtype=float), sid, "image")
            if norm is not None:
                kw["norm"] = norm
        else:
            for f in ("cmap", "vcenter", "cbar"):
                if f in rec.sspec:
                    raise SpecError(
                        f"series {sid} (image): {f!r} needs a scalar "
                        f"field — RGB arrays carry their own colors"
                    )
        if extent is not None:
            kw["extent"] = list(extent)
        for f in ("alpha", "zorder"):
            if merged.get(f) is not None:
                kw[f] = merged[f]
        kw.update(props)
        im = ax.imshow(arr, **kw)
        if i == 0 and g is not None:
            label = _legend_label(rec, g)
            if label:
                im.set_label(label)
            g.artist = im
            if arr.ndim == 2:
                _field_colorbar(ax, im, merged, ctx, lint)
        if badge is not None and src is not None:
            if rows[i].get(badge["field"]) is None:
                badge_miss += 1
            else:
                _draw_image_badge(ax, badge, rows[i], extent, sid)
    if badge_miss:
        lint(
            "missing-rows",
            f"series {sid}: {badge_miss} rows carry missing badge field "
            f"{badge['field']!r} (badge skipped)",
        )


# ------------------------------------------------------------------ sankey


def _sankey_node_rows(merged, ctx, sid):
    """nodes 表 -> {norm_id: row}（附 '_seq' 首见序）；None = 由 flow 端点
    推导。dataset 名与字面行同口径——行级校验统一落在这里。"""
    src = merged.get("nodes")
    if src is None:
        return None
    if isinstance(src, str):
        if src not in ctx.data:
            raise SpecError(
                f"series {sid} (sankey): unknown nodes dataset {src!r} "
                f"(have {sorted(ctx.data)}){_hint(src, ctx.data)}"
            )
        rows = ctx.data[src]
    else:
        rows = list(src)
    nodes = {}
    for i, nr in enumerate(rows):
        where = f"series {sid} (sankey) nodes[{i}]"
        if not isinstance(nr, dict):
            raise SpecError(f"{where} must be an object, got {nr!r}")
        _check_keys(nr, _SANKEY_NODE_KEYS, where)
        if "id" not in nr:
            raise SpecError(f"{where} needs an 'id'")
        nid = _norm_key(nr["id"])
        if nid in nodes:
            raise SpecError(f"{where}: duplicate node id {nr['id']!r}")
        for k in ("stage", "order"):
            if k in nr and not _is_num(nr[k]):
                raise SpecError(f"{where}: {k} must be numeric, got {nr[k]!r}")
        if "stage" in nr and not (float(nr["stage"]).is_integer() and nr["stage"] >= 0):
            raise SpecError(
                f"{where}: stage must be an integer >= 0, got {nr['stage']!r}"
            )
        if "label" in nr and not isinstance(nr["label"], str):
            raise SpecError(f"{where}: label must be a string, got {nr['label']!r}")
        row = dict(nr)
        row["_seq"] = i
        nodes[nid] = row
    return nodes


def _sankey_depths(nodes, flows, sid):
    """无 stage 字段时的拓扑分层：longest-path（d3 'justify'——source 置 0、
    逐前驱最深 +1，sink 自然沉到末列）。环 -> SpecError。"""
    adj = {nid: [] for nid in nodes}
    indeg = dict.fromkeys(nodes, 0)
    for f in flows:
        adj[f["s"]].append(f["d"])
        indeg[f["d"]] += 1
    depth = dict.fromkeys(nodes, 0)
    queue = [nid for nid in nodes if indeg[nid] == 0]
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        for w in adj[u]:
            depth[w] = max(depth[w], depth[u] + 1)
            indeg[w] -= 1
            if indeg[w] == 0:
                queue.append(w)
    if head < len(nodes):
        bad = sorted(str(nid) for nid in nodes if indeg[nid] > 0)
        raise SpecError(
            f"series {sid} (sankey): flows contain a cycle through {bad[:4]}"
        )
    return depth


def _sankey_flow_colors(flows, cspec, node_col, ctx, lint, sid):
    """逐 flow 解析色带颜色。cspec None -> dst 节点色（d3 'target' 语义——
    首扇出即见类色、末列守恒收口同色相）；{'field':f} 按行取字面 token；
    {'registry':R,'field':f} 按行查注册表；其余形态（token/registry:key/
    palette:N）走通用 resolve 取统一色。"""
    if cspec is None:
        return [node_col[f["d"]] for f in flows]
    if cspec == "parent":
        raise SpecError(
            f"series {sid} (sankey): color 'parent' needs a parent series — "
            f"sankey has none"
        )
    if isinstance(cspec, dict):
        keys = set(cspec)
        if keys == {"field"}:
            fld = cspec["field"]
            out = []
            for f in flows:
                v = f["row"].get(fld)
                if not isinstance(v, str):
                    raise SpecError(
                        f"series {sid} (sankey): color field {fld!r} is "
                        f"missing or non-string on a flow row"
                    )
                out.append(ctx.colors.token(v, lint))
            return out
        if keys == {"registry", "field"}:
            name, fld = cspec["registry"], cspec["field"]
            return [ctx.colors.registry(name, f["row"].get(fld), lint) for f in flows]
        # 其余 dict 形态里只有 key/palette 定值有 sankey 语境（'key' 优先于
        # 'field'，与 resolve 一致）；inline map/ramp/registry+field 之外
        # 的 field 组合都要组上下文——sankey 没有
        if not keys <= {"registry", "key", "field", "palette"} or (
            "field" in keys and "key" not in keys
        ):
            raise SpecError(
                f"series {sid} (sankey): color {cspec} has no group "
                f"context — flows take {{'registry': R, 'field': f}}, "
                f"{{'field': f}}, 'registry:key', 'palette:N' or a token"
            )
    if isinstance(cspec, str) and (
        cspec in ctx.colors.reg or cspec in ctx.colors.ramps
    ):
        raise SpecError(
            f"series {sid} (sankey): color {cspec!r} names a whole table — "
            f"use 'name:key' or {{'registry': name, 'field': f}}"
        )
    uni = ctx.colors.resolve(cspec, lint)
    return [uni] * len(flows)


def _sankey_band(
    ax, a0, a1, lo0, hi0, lo1, hi1, color, alpha, zorder, props, vertical=False
):
    """段区间 [lo0,hi0]@a0 -> [lo1,hi1]@a1 的 cubic-bezier 缎带：两缘各
    一条 CURVE4、控制点取行进轴中点（d3-sankey 的 min-curvature 形态）。
    默认行进轴是 x（段区间在 y）；vertical=True 行进轴是 y（缎带自上
    向下，段区间在 x）。"""
    am = (a0 + a1) / 2.0
    if vertical:
        verts = [
            (hi0, a0),
            (hi0, am),
            (hi1, am),
            (hi1, a1),
            (lo1, a1),
            (lo1, am),
            (lo0, am),
            (lo0, a0),
            (0.0, 0.0),
        ]
    else:
        verts = [
            (a0, hi0),
            (am, hi0),
            (am, hi1),
            (a1, hi1),
            (a1, lo1),
            (am, lo1),
            (am, lo0),
            (a0, lo0),
            (0.0, 0.0),
        ]
    codes = [
        MplPath.MOVETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.LINETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CLOSEPOLY,
    ]
    kw = {
        "facecolor": color,
        "edgecolor": "none",
        "lw": 0.5,
        "alpha": alpha,
        "zorder": zorder,
    }
    kw.update(props)  # props-win：显式声明顶掉注入默认
    p = PathPatch(MplPath(verts, codes), **kw)
    ax.add_patch(p)
    _mark(p)


def _draw_sankey(ax, rec, ctx, pid):
    """sankey：守恒流向图。一条 series 画整张图——列布局（显式 stage 或
    拓扑分层）、列内堆叠、段偏移记账、cubic-bezier 缎带、节点分段条与
    标签策略（首列左/末列右/中列骑流白带衬底）全套自绘。坐标系是流量
    单位不是数据轴：刻度归本层收掉（NullLocator 让 tick Text 不存在，
    幻影刻度盒是 readback 已知坑），frame/grid 默认在 _render。全部
    artist 标 fv-neutral——sankey 不算数据系列（missing-axis-label 等
    轴语义规则对无轴图不适用），offpalette/文本规则照查。"""
    merged = rec.merged
    sid = rec.id
    lint = ctx.lint_proxy(pid)
    ax.xaxis.set_major_locator(NullLocator())
    ax.yaxis.set_major_locator(NullLocator())
    lit = merged.get("flows")
    if lit is not None:
        # 字面流形态：行即 {source,target,value}（多余键仍可作 color field）
        rows = list(lit)
        xf, yf, zf = "source", "target", "value"
    else:
        rows = [r for g in rec.groups for r in g.rows]
        xf, yf, zf = merged.get("x"), merged.get("y"), merged.get("z")
    xs = _vals(rows, xf, "x", sid)
    ys = _vals(rows, yf, "y", sid)
    zs = _vals(rows, zf, "z", sid)
    if not (len(xs) == len(ys) == len(zs) == len(rows)):
        raise SpecError(
            f"series {sid} (sankey): x/y/z literal lists must align to "
            f"{len(rows)} rows, got {len(xs)}/{len(ys)}/{len(zs)}"
        )
    # flows：缺值行跳过（missing-rows 已按行报）；自环/重复对响亮报错
    flows, seen = [], {}
    for i, r in enumerate(rows):
        s, d, v = xs[i], ys[i], zs[i]
        if s is None or d is None or v is None:
            continue
        if not _is_num(v):
            raise SpecError(
                f"series {sid} (sankey): z value {v!r} on row {i} is "
                f"non-numeric — ribbon widths must be numbers"
            )
        v = float(v)
        if v < 0:
            raise SpecError(
                f"series {sid} (sankey): negative flow {v} on row {i} — "
                f"swap src/dst instead"
            )
        ns, nd = _norm_key(s), _norm_key(d)
        if ns == nd:
            raise SpecError(
                f"series {sid} (sankey): self-loop {s!r}->{d!r} on row "
                f"{i} cannot be drawn"
            )
        if (ns, nd) in seen:
            raise SpecError(
                f"series {sid} (sankey): duplicate flow {s!r}->{d!r} "
                f"(rows {seen[(ns, nd)]} and {i}) — aggregate upstream"
            )
        seen[(ns, nd)] = i
        flows.append({"s": ns, "d": nd, "v": v, "row": r})
    if not flows:
        return  # empty-series lint 已报——没有什么可画
    # nodes：显式表校验端点/orphan；缺省按端点推导（首见序记账）
    nodes = _sankey_node_rows(merged, ctx, sid)
    if nodes is None:
        nodes = {}
        for f in flows:
            for e in (f["s"], f["d"]):
                if e not in nodes:
                    nodes[e] = {"id": e, "_seq": len(nodes)}
    else:
        for f in flows:
            for e in (f["s"], f["d"]):
                if e not in nodes:
                    raise SpecError(
                        f"series {sid} (sankey): flow endpoint {e!r} "
                        f"absent from 'nodes'{_hint(e, nodes)}"
                    )
        used = {e for f in flows for e in (f["s"], f["d"])}
        for nid in nodes:
            if nid not in used:
                raise SpecError(
                    f"series {sid} (sankey): node {nodes[nid]['id']!r} is "
                    f"not referenced by any flow — remove it or check "
                    f"for an id typo"
                )
    # stage：显式全有或全无；全无走拓扑分层（longest-path/justify）
    have_stage = [nid for nid in nodes if "stage" in nodes[nid]]
    if have_stage and len(have_stage) != len(nodes):
        raise SpecError(
            f"series {sid} (sankey): 'stage' must be on all nodes or "
            f"none ({len(have_stage)} of {len(nodes)} given)"
        )
    if have_stage:
        stage_of = {nid: int(nodes[nid]["stage"]) for nid in nodes}
        for f in flows:
            if stage_of[f["s"]] >= stage_of[f["d"]]:
                raise SpecError(
                    f"series {sid} (sankey): flow {f['s']!r}->{f['d']!r} "
                    f"goes stage {stage_of[f['s']]} -> {stage_of[f['d']]} "
                    f"— flows must point to a later column"
                )
    else:
        stage_of = _sankey_depths(nodes, flows, sid)
    stages = sorted({stage_of[nid] for nid in nodes})
    rank_of_stage = {s: i for i, s in enumerate(stages)}
    cols = {s: [] for s in stages}
    for nid in nodes:
        cols[stage_of[nid]].append(nid)
    for s in stages:
        cols[s].sort(
            key=lambda nid: (
                nodes[nid].get("order", nodes[nid]["_seq"]),
                nodes[nid]["_seq"],
            )
        )
    rank = {nid: i for s in stages for i, nid in enumerate(cols[s])}
    out_f = {nid: [] for nid in nodes}
    in_f = {nid: [] for nid in nodes}
    for f in flows:
        out_f[f["s"]].append(f)
        in_f[f["d"]].append(f)
    # 守恒校验：既有入流又有出流的节点必须相等（纯源/纯汇豁免）
    total = {}
    for nid in nodes:
        i = sum(f["v"] for f in in_f[nid])
        o = sum(f["v"] for f in out_f[nid])
        if i > 0 and o > 0 and not math.isclose(i, o, rel_tol=1e-6, abs_tol=1e-9):
            raise SpecError(
                f"series {sid} (sankey): node {nodes[nid]['id']!r} "
                f"inflow {i:g} != outflow {o:g} — conservation violated"
            )
        total[nid] = max(i, o)
    # 堆叠布局：gap 按最高列（dir:'h'）/最宽行（'v'）总量折算、列/行内
    # 堆叠、共中线居中。h = 列沿 x 排、列内自上向下；v = 行沿 y 排
    # （stage 0 在顶）、行内自左向右——同一记账，轴向对调
    vertical = merged.get("dir") == "v"
    gap_abs = float(merged.get("gap", 0.05)) * max(
        sum(total[nid] for nid in c) for c in cols.values()
    )
    col_h = {
        s: sum(total[nid] for nid in cols[s]) + gap_abs * (len(cols[s]) - 1)
        for s in stages
    }
    max_h = max(col_h.values()) or 1.0
    mid = max_h / 2.0
    y0, x0 = {}, {}
    for s in stages:
        edge = mid + col_h[s] / 2.0 if not vertical else mid - col_h[s] / 2.0
        for nid in cols[s]:
            if vertical:
                x0[nid] = edge
                edge += total[nid] + gap_abs
            else:
                y0[nid] = edge - total[nid]
                edge = y0[nid] - gap_abs
    # 节点色：默认 dst 着色的载体——按 (stage, order) 序取调色板；
    # node 'color' 可点名覆盖。显式 color spec 时节点色失载 -> lint
    node_col = {}
    if merged.get("color") is None:
        i = 0
        for s in stages:
            for nid in cols[s]:
                c = nodes[nid].get("color")
                node_col[nid] = (
                    ctx.colors.token(c, lint)
                    if c is not None
                    else ctx.colors.palette_at(i)
                )
                i += 1
    elif any("color" in nodes[nid] for nid in nodes):
        lint(
            "axis-ignored",
            f"series {sid} (sankey): node 'color' is owned by the "
            f"series-level 'color' spec — ignored",
        )
    for f, c in zip(
        flows,
        _sankey_flow_colors(flows, merged.get("color"), node_col, ctx, lint, sid),
    ):
        f["c"] = c
    # 段偏移：出段按对端列/行位堆叠、入段同理（减交叉启发）——h 自上
    # 向下记账，v 自左向右记账（堆叠序镜像：首个对端取最上/最左切片）
    for nid in nodes:
        if vertical:
            cur = x0[nid]
            for f in sorted(out_f[nid], key=lambda f: rank[f["d"]]):
                f["sseg"] = (cur, cur + f["v"])
                cur += f["v"]
            cur = x0[nid]
            for f in sorted(in_f[nid], key=lambda f: rank[f["s"]]):
                f["dseg"] = (cur, cur + f["v"])
                cur += f["v"]
        else:
            cur = y0[nid] + total[nid]
            for f in sorted(out_f[nid], key=lambda f: rank[f["d"]]):
                cur -= f["v"]
                f["sseg"] = (cur, cur + f["v"])
            cur = y0[nid] + total[nid]
            for f in sorted(in_f[nid], key=lambda f: rank[f["s"]]):
                cur -= f["v"]
                f["dseg"] = (cur, cur + f["v"])
    w = float(merged.get("width", 0.18))
    hw = w / 2.0
    zrib = merged.get("zorder", 1.6)
    alpha = merged.get("alpha", 0.52)
    props = _resolve_props(merged.get("props"), ctx, lint)
    # 行进轴坐标：h 列位 x = stage rank；v 行位 y = R-1-rank（stage 0 在顶）
    if vertical:
        yrow = {
            nid: float(len(stages) - 1 - rank_of_stage[stage_of[nid]]) for nid in nodes
        }
    else:
        x_of = {nid: float(rank_of_stage[stage_of[nid]]) for nid in nodes}
    for f in flows:
        (lo0, hi0), (lo1, hi1) = f["sseg"], f["dseg"]
        if vertical:
            _sankey_band(
                ax,
                yrow[f["s"]] - hw,
                yrow[f["d"]] + hw,
                lo0,
                hi0,
                lo1,
                hi1,
                f["c"],
                alpha,
                zrib,
                props,
                vertical=True,
            )
        else:
            _sankey_band(
                ax,
                x_of[f["s"]] + hw,
                x_of[f["d"]] - hw,
                lo0,
                hi0,
                lo1,
                hi1,
                f["c"],
                alpha,
                zrib,
                props,
            )
    # 节点分段条：有入流按入段（来路构成）、纯源按出段（去向构成）
    for nid in nodes:
        segs = (
            [(f["dseg"], f["c"]) for f in in_f[nid]]
            if in_f[nid]
            else [(f["sseg"], f["c"]) for f in out_f[nid]]
        )
        for (lo, hi), c in segs:
            if vertical:
                p = Rectangle(
                    (lo, yrow[nid] - hw),
                    hi - lo,
                    w,
                    facecolor=c,
                    edgecolor=fv.NEUTRALS["vink"],
                    lw=0.5,
                    zorder=zrib + 0.4,
                )
            else:
                p = Rectangle(
                    (x_of[nid] - hw, lo),
                    w,
                    hi - lo,
                    facecolor=c,
                    edgecolor=fv.NEUTRALS["vink"],
                    lw=0.5,
                    zorder=zrib + 0.4,
                )
            ax.add_patch(p)
            _mark(p)
    # 标签策略：首列左对齐于条左、末列右对齐于条右、中列同左置但骑流
    # 白带衬底（d3-sankey 惯例）；v 镜像为首行上置、末行下置、中行上置
    lab = merged.get("labels", True)
    if lab is not False:
        template, vfmt = "{l} {v}", "{:g}"
        fs = float(plt.rcParams.get("font.size", 7.6)) - 1.0
        if isinstance(lab, str):
            template = lab
        elif isinstance(lab, dict):
            template = lab.get("template", template)
            vfmt = lab.get("vfmt", vfmt)
            fs = lab.get("fontsize", fs)
        pad = float(merged.get("pad", 0.05))
        last_rank = len(stages) - 1
        for nid in nodes:
            n = nodes[nid]
            text = template.format(
                l=n.get("label", n["id"]),
                id=n["id"],
                v=vfmt.format(total[nid]),
                value=total[nid],
            )
            cr = rank_of_stage[stage_of[nid]]
            kw = {}
            if vertical:
                xc = x0[nid] + total[nid] / 2.0
                if cr == last_rank:
                    yt, va = yrow[nid] - hw - pad, "top"
                else:
                    yt, va = yrow[nid] + hw + pad, "bottom"
                    if cr != 0:
                        kw["bbox"] = {
                            "facecolor": "white",
                            "alpha": 0.78,
                            "edgecolor": "none",
                            "pad": 0.8,
                        }
                t = ax.text(xc, yt, text, ha="center", va=va, fontsize=fs, **kw)
            else:
                yc = y0[nid] + total[nid] / 2.0
                if cr == last_rank:
                    xt, ha = x_of[nid] + hw + pad, "left"
                else:
                    xt, ha = x_of[nid] - hw - pad, "right"
                    if cr != 0:
                        kw["bbox"] = {
                            "facecolor": "white",
                            "alpha": 0.78,
                            "edgecolor": "none",
                            "pad": 0.8,
                        }
                t = ax.text(xt, yc, text, ha=ha, va="center", fontsize=fs, **kw)
            _mark(t)
    # 列/行头：heads 列表按排序后列位（行位）对齐、dict 按 stage 值键控；
    # h 居中于列上方，v 右对齐于行左缘
    heads = merged.get("heads")
    head_map = {}
    if isinstance(heads, (list, tuple)):
        head_map = dict(zip(stages, heads))
    elif isinstance(heads, dict):
        head_map = {_norm_key(k): v for k, v in heads.items()}
    head_off = 0.04 * max_h
    for s in stages:
        htext = head_map.get(_norm_key(s))
        if htext is None:
            continue
        if vertical:
            t = ax.text(
                mid - col_h[s] / 2.0 - head_off,
                float(len(stages) - 1 - rank_of_stage[s]),
                htext,
                ha="right",
                va="center",
                fontsize=float(plt.rcParams.get("font.size", 7.6)) - 0.4,
                fontweight="bold",
            )
        else:
            t = ax.text(
                float(rank_of_stage[s]),
                mid + col_h[s] / 2.0 + head_off,
                htext,
                ha="center",
                va="bottom",
                fontsize=float(plt.rcParams.get("font.size", 7.6)) - 0.4,
                fontweight="bold",
            )
        _mark(t)
    # 显式视窗：h 左右留标签通道、上方留列头空间；v 上下留标签通道、
    # 左方留行头空间。auto=False 防 relim/autoscale（note lint 路径）
    # 冲掉——lim 仍是用户加宽逃生口
    m = 0.6 + hw
    if vertical:
        head_room = (head_off + 0.30 * max_h) if head_map else 0.0
        ax.set_xlim(-0.04 * max_h - head_room, max_h + 0.04 * max_h, auto=False)
        ax.set_ylim(-m, len(stages) - 1 + m, auto=False)
    else:
        ax.set_xlim(-m, len(stages) - 1 + m, auto=False)
        ax.set_ylim(
            -0.04 * max_h,
            max_h + head_off + (0.06 * max_h if head_map else 0.0),
            auto=False,
        )


DRAW = {
    "line": _draw_line,
    "pred": _draw_pred,
    "band": _draw_band,
    "scatter": _draw_scatter,
    "bar": _draw_bar,
    "ref": _draw_ref,
    "span": _draw_span,
    "note": _draw_note,
    "donut": _draw_donut,
    "hist": _draw_hist,
    "ecdf": _draw_ecdf,
    "kde": _draw_kde,
    "box": _draw_box,
    "violin": _draw_violin,
    "heat": _draw_heat,
    "contour": _draw_contour,
    "quiver": _draw_quiver,
    "image": _draw_image,
    "sankey": _draw_sankey,
    "sig": _draw_sig,
}
