"""fvspec_schema.py — spec 键表、常量与基础校验原语（SpecError、_check_keys）。"""

from __future__ import annotations

import difflib
import hashlib
import json as _json

import fvstyle as fv
import numpy as np
from matplotlib.colors import to_rgba

SPEC_VERSION = 1

SIZE_SLOTS = {"full": 5.5, "half": 2.70, "third": 1.77}
ROW_HEIGHT = 1.8  # 网格每行缺省高度（英寸）
MAX_GRID_CELLS = 8  # 「panels 网格至多 2x4」
MAX_GRID_DIM = 4
# 图版（image-plate：方法×样本的示例墙）放宽网格上限——cell 是像素图
# 不是数据轴，密度纪律不适用；上限仍在，防误生成百格空版
MAX_PLATE_CELLS = 64
MAX_PLATE_DIM = 16
# matrix（facet 同模板展开）密度纪律放宽——同形小多图比异质面板便宜；
# 仍在纪律内（facet_grid 常见 3x4/2x6），更大就拆图
MAX_MATRIX_CELLS = 24
MAX_MATRIX_DIM = 8
# spans 的逻辑网格是比例尺不是面板密度（joint 主区:边际 = 3:1 要 4+1
# 行/列的坐标表达）——面板数仍按 MAX_GRID_CELLS 收，网格边长单独放宽
MAX_SPANS_DIM = 8

TOP_KEYS = {
    "version",
    "theme",
    "rc",
    "size",
    "size_slots",
    "colors",
    "data",
    "layout",
    "panels",
    "legend",
    "arrange",
    "output",
    "meta",
    "audit",
}
PANEL_KEYS = {
    "kind",
    "tag",
    "title",
    "from",
    "where",
    "xaxis",
    "yaxis",
    "y2",
    "grid",
    "grid_axis",
    "frame",
    "legend",
    "series",
    "raw",
    "audit_ignore",
    "dims",
    "rlabel",
    "theta",
    "aspect",
}
AXIS_KEYS = {
    "label",
    "scale",
    "lim",
    "ticks",
    "tick_labels",
    "minor",
    "props",
    "tick_rotation",
    "tick_stride",
}
LAYOUT_KEYS = {
    "kind",
    "shape",
    "cells",
    "sharex",
    "sharey",
    "tags",
    "width_ratios",
    "height_ratios",
    "rows",
    "cols",
    "template",
    "overrides",
    "map",
    "bind",
    "strips",
}
LEGEND_KEYS = {
    "where",
    "cell",
    "loc",
    "ncol",
    "fontsize",
    "title",
    "entries",
    "from",
    "columnspacing",
    "handletextpad",
    "labelspacing",
    "props",
}
ARRANGE_KEYS = {"engine", "rect", "w_pad", "h_pad"}
OUTPUT_KEYS = {"path", "formats", "dpi", "bbox", "pad"}
META_KEYS = {"ledger", "caption", "usermeta"}
AUDIT_KEYS = {"ignore"}
COLORS_KEYS = {"registries", "ramps", "extend"}
RC_KEYS = {"font", "base"}
BAR_LABEL_KEYS = {"fmt", "fontsize", "dy", "color", "mode", "groups"}
BAR_CONNECT_KEYS = {"color", "ls", "lw", "zorder", "groups", "props", "label"}
_BAR_LABEL_MODES = ("value", "delta", "cum")
_ERR_KEYS = {"lo", "hi"}

SERIES_COMMON = {
    "kind",
    "id",
    "from",
    "where",
    "by",
    "of",
    "color",
    "label",
    "legend",
    "axis",
    "props",
    "zorder",
    "alpha",
    "sort_x",
    "errprops",
    "marker",
    "ls",
    "lw",
    "ms",
    "mew",
    "draw",
}
SERIES_KIND_KEYS = {
    "line": {"x", "y", "fill", "xerr", "yerr"},
    "pred": {"x", "y"},
    "band": {"x", "lo", "hi", "semantics"},
    "scatter": {"x", "y", "s", "edgecolor", "linewidths", "xerr", "yerr", "jitter"},
    "bar": {
        "x",
        "y",
        "stack",
        "dir",
        "width",
        "baseline",
        "bottom",
        "connect",
        "hatch",
        "labels",
        "xerr",
        "yerr",
    },
    "ref": {"dir", "at"},
    "span": {"dir", "at"},
    "note": {"at", "to", "text", "arrow", "units"},
    "donut": {
        "x",
        "y",
        "pct",
        "pctdistance",
        "startangle",
        "width",
        "labels",
        "edgecolor",
    },
    # 分布图族：hist/ecdf 的 x、box/violin 的 y 是数值列名（非坐标轴语义）；
    # dir:'h' = mpl orientation 同义——hist/kde/ecdf 数据落 y 轴（右侧
    # 边际，bind axis:'y'），box/violin 数据落 x 轴（顶部边际，bind 'x'）
    "hist": {"x", "bins", "range", "density", "cumulative", "dir"},
    "ecdf": {"x", "dir"},
    "kde": {"x", "bw", "bw_adjust", "grid", "fill", "clip", "dir"},
    "box": {"y", "positions", "widths", "fliers", "dir"},
    "violin": {"y", "positions", "widths", "inner", "dir"},
    "heat": {
        "x",
        "y",
        "z",
        "matrix",
        "xlabels",
        "ylabels",
        "cmap",
        "vcenter",
        "cbar",
        "annotate",
    },
    # 场族：x/y 是真实坐标轴（非 heat 的类别轴），cmap/vcenter/cbar 同 heat
    "contour": {
        "x",
        "y",
        "z",
        "matrix",
        "xlabels",
        "ylabels",
        "levels",
        "mode",
        "clabel",
        "cmap",
        "vcenter",
        "cbar",
    },
    "quiver": {
        "x",
        "y",
        "u",
        "v",
        "m",
        "mode",
        "density",
        "linewidth",
        "arrowsize",
        "scale",
        "pivot",
        "cmap",
        "vcenter",
        "cbar",
    },
    # 图像/图版：file（列名，格值为路径或数组）| path（字面文件）|
    # rgb（字面数组）三选一；extent 对格外网格（heat 叠图配方
    # (0,n,n,0) + origin 'upper' 落 pcolormesh 格心）；badge 行级角标
    "image": {"file", "path", "rgb", "extent", "cmap", "vcenter", "cbar", "badge"},
    # 守恒流向图：x=src、y=dst、z=value 三列（heat 长表同口径），或
    # flows 字面行 [{source,target,value}] 直给（数据自由——from/where/
    # x/y/z 属长表形态，响亮拒）；nodes = 节点表（dataset 名 | 字面行
    # [{id,stage,label,order,color}]，缺省按端点推导 + 拓扑分层）；
    # dir:'h'（默认，列左→右）|'v'（行上→下）；gap/width/pad 布局参数；
    # labels 节点标签（true|false|模板|{template,vfmt,fontsize}）；heads 列头
    "sankey": {
        "x",
        "y",
        "z",
        "flows",
        "nodes",
        "dir",
        "gap",
        "width",
        "pad",
        "labels",
        "heads",
    },
    # 显著性括号：数据自由度的中性注释层——每行一条括号 {a,b,y,p|text}；
    # tick=垂足长、pad=文本到梁距（数据单位，缺省随 y 量程自适应）；
    # props → bracket Line2D、textprops → 星号/文本 kwargs
    "sig": {"tick", "pad", "textprops"},
}
PANEL_KINDS = {"xy", "radar", "donut"}
PANEL_SERIES_KINDS = {
    "xy": set(SERIES_KIND_KEYS) - {"donut"},
    "radar": {"line", "pred", "band", "scatter", "ref", "span", "note"},
    "donut": {"donut"},
}

_OPS = {
    "$eq": lambda a, b: a == b,
    "$ne": lambda a, b: a != b,
    "$gt": lambda a, b: a > b,
    "$gte": lambda a, b: a >= b,
    "$lt": lambda a, b: a < b,
    "$lte": lambda a, b: a <= b,
    "$in": lambda a, b: a in b,
    "$nin": lambda a, b: a not in b,
}
_UNITS = {"data": "data", "axes": "axes fraction", "figure": "figure fraction"}
_BAND_ALPHA = {"iqr": 0.13, "std": 0.12, "range": 0.10}
_NEUTRAL_KINDS = {"ref", "span", "note"}  # 默认中性色，不占 palette[0]
# bind 的 side 面板降级为 main 的边际装饰（joint 边际、clustermap 侧
# 条）：标注义务（轴标签/图例覆盖）在主面板履行，side 两轴豁免
_BIND_SIDE_IGNORES = {"missing-axis-label", "legend-coverage"}
# 图版 cell 允许的 series 集合：image + 中性 overlay（布局放宽与面板
# 默认共用的认定口径——cell 必须含 image、其余只许中性 overlay）
_IMG_PANEL_KINDS = _NEUTRAL_KINDS | {"image"}
# sankey 面板允许的 series 集合：坐标系是流量单位不是数据轴，其余
# kind 画进去没有语义——只放行 sankey 本体与中性 overlay
_SANKEY_PANEL_KINDS = _NEUTRAL_KINDS | {"sankey"}
_NEUTRAL_GID = fv.NEUTRAL_GID  # fvstyle.audit 对 'fv-*' gid 豁免系列规则
_LEGEND_WHERE = {"below", "cell"}
_FIELD_ZORDER = 0.5  # 场族（contour/quiver）默认垫在数据系列（>=1）之下
# mpl 默认 zorder 实测值（occluded-by-heat 判定用；系列级 'zorder' 覆盖之）：
# Line2D=2 / patch&collection=1 / text=3
_KIND_ZORDER = {
    "line": 2,
    "pred": 2,
    "band": 1,
    "scatter": 1,
    "bar": 1,
    "ref": 2,
    "span": 1,
    "note": 3,
    "donut": 1,
    "hist": 1,
    "ecdf": 2,
    "kde": 2,
    "box": 1,
    "violin": 1,
    "heat": 1,
    "contour": _FIELD_ZORDER,
    "quiver": _FIELD_ZORDER,
    "image": 0,  # mpl AxesImage 默认 0——垫底的栅格层
    "sankey": 1,
    "sig": 3,  # 注释层——与 note 同高，浮在数据系列之上
}
_LUM_INK = fv._rel_luminance(to_rgba(fv.NEUTRALS["vink"]))

# spec-lint 检查名（可用 audit.ignore / 面板 audit_ignore 抑制）
LINT_NAMES = {
    "empty-series",
    "empty-legend",
    "hex-literal",
    "pred-indistinct",
    "fill-ignored",
    "scale-ignored",
    "axis-ignored",
    "unknown-ignore",
    "ignore-unscoped",
    "dim-unresolved",
    "dead-cell",
    "missing-rows",
    "unknown-field",
    "where-field-missing",
    "empty-y2",
    "twin-axis-unlabeled",
    "missing-ledger",
    "missing-caption",
    "tight-bbox",
    "meta-key-dropped",
    "meta-key-reserved",
    "dodge-single-group",
    "markers-on-dense-line",
    "tick-density",
    "bar-count",
    "hist-bin-sanity",
    "violin-min-points",
    "kde-min-points",
    "heat-cell-text",
    "note-outside-axes",
    "sig-outside-axes",
    "occluded-by-heat",
    "log-tick-unlabeled",
}
# series 必需列（missing-rows 计数口径）：ref/span/note 的 at 有独立报错，
# 不在此列
_REQ_FIELDS = {
    "line": ("x", "y"),
    "pred": ("x", "y"),
    "band": ("x", "lo", "hi"),
    "scatter": ("x", "y"),
    "bar": ("x", "y"),
    "donut": ("x", "y"),
    "hist": ("x",),
    "ecdf": ("x",),
    "kde": ("x",),
    "box": ("y",),
    "violin": ("y",),
    "heat": ("x", "y", "z"),
    "contour": ("x", "y", "z"),
    "quiver": ("x", "y", "u", "v"),
    "image": ("file",),
    "sankey": ("x", "y", "z"),
}
# savefig metadata 各后端可写键：pgf 不支持 metadata kwarg（None 不下发）；
# png 任意键；pdf/svg 白名单（svg 对未知键 ValueError、pdf 只 warn）
_META_KEYS_PDF = {
    "Title",
    "Author",
    "Subject",
    "Keywords",
    "Creator",
    "Producer",
    "CreationDate",
    "ModDate",
    "Trapped",
}
_META_KEYS_SVG = {
    "Title",
    "Coverage",
    "Creator",
    "Date",
    "Description",
    "Format",
    "Identifier",
    "Keywords",
    "Language",
    "Relation",
    "Rights",
    "Source",
    "Type",
    "Contributor",
    "Publisher",
}
# fv.RENDER_RULES 中无法归属到单一 axes 的规则名：面板 audit_ignore
# 写它们会被 ignore-unscoped lint 拒掉。
_FIGURE_RULES = {
    "collide",
    "offpalette",
    "text-outside-figure",
    "duplicate-legend-label",
    "tag-sequence",
    "missing-glyph",
    "rb-label-diff",  # 声明 vs 渲染差集是全图判定，不查 scoped
}


class SpecError(ValueError):
    """任何 spec 校验或归一化失败。"""


def _hint(bad, candidates):
    """未知 key/name/列名的 difflib「你是不是想写」后缀。"""
    m = difflib.get_close_matches(
        str(bad), [str(c) for c in candidates], n=1, cutoff=0.6
    )
    return f" — did you mean {m[0]!r}?" if m else ""


def _check_keys(d, allowed, where):
    extra = sorted(set(d) - allowed)
    if extra:
        hints = "; ".join(
            f"{k!r}{_hint(k, allowed)}" for k in extra if _hint(k, allowed)
        )
        msg = f"{where}: unknown keys {extra}; valid keys: {sorted(allowed)}"
        if hints:
            msg += f" ({hints})"
        raise SpecError(msg)


def _spec_hash(spec):
    """spec 的 sha256[:12]——写进产物 metadata 的溯源指纹。"""

    def _default(o):
        if callable(o):
            return getattr(o, "__qualname__", type(o).__name__)
        return repr(o)

    blob = _json.dumps(spec, sort_keys=True, default=_default, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _obj(v, where):
    """把应为 JSON 对象的 spec 块归一；None -> {}。"""
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise SpecError(f"{where} must be an object, got {v!r}")
    return v


def _mark(*artists):
    """给 spec 中性 overlay artist 打 fvstyle.audit 的 'fv-*' 豁免标记。"""
    fv.mark_neutral(*artists)


def _pos_key(v):
    """已归一位置值的可哈希去重键。"""
    return v if isinstance(v, (str, int, float, bool)) else repr(v)


def _norm_key(v):
    """JSON 键归一化：'0.3' == 0.3，'8' == 8，'true' == True。"""
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, bool):
        return v
    if _is_num(v):
        f = float(v)
        return int(f) if f.is_integer() else f
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        try:
            f = float(s)
        except ValueError:
            return s
        return int(f) if f.is_integer() else f
    return v
