"""fvspec_data.py — 数据集装载、配色/主题解析、渲染上下文与轴值抽取。"""

from __future__ import annotations

import csv as _csv
import re
from pathlib import Path

import fvstyle as fv
import numpy as np
from fvagg import coerce_cell as _coerce
from fvspec_schema import (
    _ERR_KEYS,
    _OPS,
    AUDIT_KEYS,
    COLORS_KEYS,
    META_KEYS,
    SpecError,
    _check_keys,
    _hint,
    _is_num,
    _mark,
    _norm_key,
    _obj,
    _spec_hash,
)
from matplotlib.colors import to_rgba

# --------------------------------------------------------------------- 数据


def _load_datasets(spec, base_dir):
    data = spec.get("data")
    if data is not None and not isinstance(data, dict):
        raise SpecError(f"data must be an object, got {data!r}")
    out = {}
    for name, src in (data or {}).items():
        rows = None
        if isinstance(src, list):
            rows = src
        elif isinstance(src, dict):
            if "columns" in src:
                cols = src["columns"]
                if not isinstance(cols, dict):
                    raise SpecError(
                        f"data.{name}.columns must be an object, got {cols!r}"
                    )
                sizes = {len(v) for v in cols.values()}
                if len(sizes) > 1:
                    raise SpecError(f"data.{name}: ragged columns {sorted(sizes)}")
                keys = list(cols)
                rows = [dict(zip(keys, vals)) for vals in zip(*cols.values())]
            elif "csv" in src:
                if not isinstance(src["csv"], str):
                    raise SpecError(
                        f"data.{name}.csv must be a path string, got {src['csv']!r}"
                    )
                path = Path(src["csv"])
                if not path.is_absolute():
                    path = Path(base_dir or ".") / path
                try:
                    with open(path, newline="") as f:
                        rows = [
                            {k: _coerce(v) for k, v in r.items()}
                            for r in _csv.DictReader(f)
                        ]
                except OSError as e:
                    raise SpecError(
                        f"data.{name}.csv: cannot read {path}: {e.strerror or e}"
                    ) from e
            elif "fields" in src and "map" in src:
                fields, fmap = src["fields"], src["map"]
                if not isinstance(fields, (list, tuple)) or not isinstance(fmap, dict):
                    raise SpecError(
                        f"data.{name}: 'fields' must be a list and 'map' an object"
                    )
                rows = [dict(zip(fields, k)) | dict(v) for k, v in fmap.items()]
            else:
                raise SpecError(f"data.{name}: need rows | columns | csv | fields+map")
        else:
            raise SpecError(f"data.{name}: unsupported source {type(src)}")
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                raise SpecError(f"data.{name}[{i}]: row is not an object")
        out[name] = [
            {k: (v.item() if isinstance(v, np.generic) else v) for k, v in r.items()}
            for r in rows
        ]
    return out


def _match(row, where):
    for f, cond in (where or {}).items():
        v = row.get(f)
        if isinstance(cond, dict):
            for op, operand in cond.items():
                fn = _OPS.get(op)
                if fn is None:
                    raise SpecError(f"where: unknown op {op!r}")
                try:
                    ok = fn(v, operand)
                except TypeError:
                    ok = False
                if not ok:
                    return False
        elif isinstance(cond, list):
            if v not in cond:
                return False
        elif v != cond:
            return False
    return True


def _filter(rows, where):
    return [r for r in rows if _match(r, where)]


# -------------------------------------------------------------------- 配色


class _Colors:
    """registry/ramp/extend/token 颜色解析（永不静默退灰）。

    声明值（registry/ramp/extend 条目）允许写裸 hex——这些表本就是
    声明层；只有系列级字面 hex 才撞 ``hex-literal`` lint。所有声明的
    hex 都收进 ``palette_ext`` 供 ``fv.audit(extra_palette=...)``。
    """

    def __init__(self, spec_colors, theme_name):
        c = spec_colors or {}
        _check_keys(c, COLORS_KEYS, "colors")
        self.palette_ext = set()
        # extend 先行：registry/ramp 的表值允许引用 extend 命名色
        self.extend = {}
        for name, v in (c.get("extend") or {}).items():
            hv = self._declared(v, f"extend {name!r}")
            self.extend[name] = hv
        self.reg = {}
        for name, reg in (c.get("registries") or {}).items():
            self.reg[name] = self._declared_table(reg, f"registry {name!r}")
        self.ramps = {}
        for name, ramp in (c.get("ramps") or {}).items():
            self.ramps[name] = self._declared_table(ramp, f"ramp {name!r}")
        pal = fv.palette(fv.theme(theme_name).palette)
        self.palette = fv.series_colors(theme_name, len(pal))

    def _declared(self, v, where):
        """解析一条声明色值；裸 hex 静默放行。"""
        if isinstance(v, str):
            if re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                hv = v.lower()
            else:
                hv = self.token(v, lambda *_: None)
        else:
            raise SpecError(f"{where}: bad color value {v!r}")
        self.palette_ext.add(hv)
        return hv

    def _declared_table(self, table, where):
        return {_norm_key(k): self._declared(v, where) for k, v in table.items()}

    def token(self, name, lint):
        """v* 色相 / NEUTRALS / *_edge / extend 名 / hex -> hex 串。"""
        if not isinstance(name, str):
            raise SpecError(f"color token must be a string, got {name!r}")
        if name in fv.HUES:
            return fv.HUES[name]
        if name in fv.NEUTRALS:
            return fv.NEUTRALS[name]
        if name in fv.EDGE:
            return fv.EDGE[name]
        if name in self.extend:
            return self.extend[name]
        if re.fullmatch(r"#[0-9a-fA-F]{6}", name):
            lint("hex-literal", f"literal {name} bypasses colors.extend allowlist")
            return name.lower()
        raise SpecError(
            f"unknown color token {name!r}: not a v* hue, NEUTRALS, "
            f"*_edge, extend name or #rrggbb"
        )

    def _lookup(self, table, table_name, key, lint):
        del lint  # 表值已是 _declared 解析好的 hex
        nk = _norm_key(key)
        if nk not in table:
            raise SpecError(
                f"unresolved-color: {table_name} has no key {key!r} "
                f"(have {sorted(table, key=str)})"
            )
        return table[nk]

    def registry(self, name, key, lint):
        if name not in self.reg:
            raise SpecError(
                f"unresolved-color: no registry {name!r} (have {sorted(self.reg)})"
            )
        return self._lookup(self.reg[name], f"registry {name!r}", key, lint)

    def ramp(self, name, key, lint):
        if name not in self.ramps:
            raise SpecError(
                f"unresolved-color: no ramp {name!r} (have {sorted(self.ramps)})"
            )
        return self._lookup(self.ramps[name], f"ramp {name!r}", key, lint)

    def palette_at(self, i):
        if not isinstance(i, int) or i < 0 or i >= len(self.palette):
            raise SpecError(
                f"palette:{i} out of range (palette size {len(self.palette)})"
            )
        return self.palette[i]

    def resolve(self, cspec, lint, *, group=..., rows=None):
        """把系列颜色 spec 解析为 hex 或逐行 hex 列表。

        group=... 表示「无组上下文」（哨兵，区别于真实 None 键）。
        field 查找返回与 rows 对齐的列表。
        """
        if cspec is None:
            return None
        if cspec == "parent":
            return ("parent", None)
        if isinstance(cspec, str):
            if ":" in cspec:
                head, _, tail = cspec.partition(":")
                if head == "palette":
                    try:
                        idx = int(tail)
                    except ValueError:
                        raise SpecError(f"bad palette index {tail!r}") from None
                    return self.palette_at(idx)
                if head in self.reg:
                    return self.registry(head, tail, lint)
                if head in self.ramps:
                    return self.ramp(head, tail, lint)
                raise SpecError(
                    f"unknown color namespace {head!r} (have registries "
                    f"{sorted(self.reg)}, ramps {sorted(self.ramps)}, "
                    f"'palette', or a bare token)"
                )
            if cspec in self.reg:
                if group is ...:
                    raise SpecError(
                        f"color {cspec!r} is a registry: needs a 'by' group "
                        f"or 'registry:key' form"
                    )
                return self.registry(cspec, group, lint)
            return self.token(cspec, lint)
        if isinstance(cspec, dict):
            if "palette" in cspec:
                return self.palette_at(cspec["palette"])
            if "registry" in cspec:
                name = cspec["registry"]
                if "key" in cspec:
                    return self.registry(name, cspec["key"], lint)
                if "field" in cspec:
                    fld = cspec["field"]
                    if rows is None:
                        raise SpecError(f"color registry:{name} field:{fld} needs rows")
                    return [self.registry(name, r.get(fld), lint) for r in rows]
                if group is ...:
                    raise SpecError(
                        f"color registry:{name} needs 'key', 'field' or a 'by' group"
                    )
                return self.registry(name, group, lint)
            if "ramp" in cspec:
                if group is ...:
                    raise SpecError(
                        f"color ramp:{cspec['ramp']} needs a 'by' group value"
                    )
                return self.ramp(cspec["ramp"], group, lint)
            # 内联 {key: color} 映射
            if group is ...:
                raise SpecError(f"inline color map {cspec} needs a 'by' group value")
            for k, v in cspec.items():
                if _norm_key(k) == group:
                    return self.token(v, lint)
            raise SpecError(
                f"unresolved-color: inline map has no key {group!r} "
                f"(have {list(cspec)})"
            )
        raise SpecError(f"unsupported color spec {cspec!r}")


# ------------------------------------------------------------------- 上下文


class _Ctx:
    def __init__(self, spec, theme_name, base_dir):
        self.spec = spec
        self.theme_name = theme_name
        self.theme = fv.theme(theme_name)
        self.base_dir = base_dir
        self.warnings = []
        audit_cfg = _obj(spec.get("audit"), "audit")
        _check_keys(audit_cfg, AUDIT_KEYS, "audit")
        ignore = audit_cfg.get("ignore") or []
        if not isinstance(ignore, list):
            raise SpecError(f"audit.ignore must be a list, got {ignore!r}")
        self.fig_ignores = set(ignore)
        self.panel_ignores = {}
        self.colors = _Colors(spec.get("colors"), theme_name)
        self.data = _load_datasets(spec, base_dir)
        self.records = {}  # series id -> _SeriesRec（跨面板）
        self.panel_recs = {}  # panel id -> [_SeriesRec]（绘制期可查同面板兄弟系列）
        self.angles = {}  # panel id -> {dim: angle}
        self.polar = {}  # panel id -> bool
        self._uf_seen = set()  # (pid, dataset, field) 未知字段去重
        self.spec_sha = _spec_hash(spec)
        # meta：台账（ledger）与底部标识行（caption）是工作流约定——缺失告警
        meta = _obj(spec.get("meta"), "meta")
        _check_keys(meta, META_KEYS, "meta")
        for k in ("ledger", "caption"):
            v = meta.get(k)
            if v is not None and not isinstance(v, str):
                raise SpecError(f"meta.{k} must be a string, got {v!r}")
        _obj(meta.get("usermeta"), "meta.usermeta")
        self.meta = meta
        if not (isinstance(meta.get("ledger"), str) and meta["ledger"].strip()):
            self.lint(
                "missing-ledger",
                "meta.ledger absent — 语义/几何台账写进 spec 的 "
                "meta.ledger（每个绘制对象一行：类别/域/含义）",
            )
        if not (isinstance(meta.get("caption"), str) and meta["caption"].strip()):
            self.lint(
                "missing-caption",
                "meta.caption absent — 底部居中一行中性灰标识文字，"
                "只描述实际可视化内容",
            )

    def lint(self, name, msg, pid=None):
        if name in self.fig_ignores:
            return
        if pid and name in self.panel_ignores.get(pid, ()):
            return
        where = f" (panel {pid})" if pid else ""
        self.warnings.append(f"{name}: {msg}{where}")

    def lint_proxy(self, pid):
        def go(name, msg):
            self.lint(name, msg, pid)

        return go


class _Group:
    __slots__ = ("artist", "color", "key", "label", "marker", "raw", "rows", "xs")

    def __init__(self, key, raw, rows):
        self.key, self.raw, self.rows = key, raw, rows
        self.artist = None  # 本组实际画出的 artist
        self.color = None
        self.marker = None
        self.label = None
        self.xs = None  # 实际绘制的 x 网格（line/pred 父系列）


class _SeriesRec:
    """预处理好的系列：spec + 展开的组 + 逐组定好的样式。"""

    def __init__(self, sspec, sid):
        self.sspec = sspec
        self.merged = sspec
        self.id = sid
        self.kind = sspec["kind"]
        self.groups = []
        self.parent = None
        self.by_field = None
        self.handles = None  # 显式图例 handle（donut 切片）
        self.num_x = False  # bar 数值 x：柱落在真实坐标而非类别槽位
        self.cat_y = False  # contour matrix 类别 ylabels → 槽位轴（刻度归 kind 层）
        self.cat_x = False  # contour matrix 类别 xlabels → 槽位轴（刻度归 kind 层）
        self.note_annots = []  # note 画出的 annotation（含逐行扇出）
        self.conn_label = (
            None  # bar connect.label 画出的图例幽灵标签（无命中时为 None）
        )
        self.sig_spans = []  # sig 画出的 (y, pad, fontsize)——sig-outside-axes lint 用

    def group(self, key):
        for g in self.groups:
            if g.key == key:
                return g
        return None


# ------------------------------------------------------------- 轴值


def _vals(rows, spec, what, sid):
    """解析轴位置 spec：列名 | 数值 | 字面列表。"""
    if isinstance(spec, str):
        if rows and all(spec not in r for r in rows):
            keyset = {k for r in rows for k in r}
            raise SpecError(
                f"series {sid}: {what} {spec!r} is not a data column "
                f"(a literal string can never be an axis position)"
                f"{_hint(spec, keyset)}"
            )
        return [r.get(spec) for r in rows]
    if _is_num(spec):
        return [spec] * len(rows)
    if isinstance(spec, (list, tuple)):
        return list(spec)
    raise SpecError(
        f"series {sid}: bad {what} spec {spec!r} (column name | number | list)"
    )


def _drop_none(xs, ys):
    return [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]


def _drawn_idx(xs, ys):
    """行索引 of drawable (x,y) pairs — missing x/y 的行在此落出。"""
    n = min(len(xs), len(ys))
    return [i for i in range(n) if xs[i] is not None and ys[i] is not None]


def _sort_xy_idx(xs, ys, sort_x):
    """drawable 行索引，按 x 排序（sort_x 且全数值时）。"""
    idx = _drawn_idx(xs, ys)
    if sort_x and all(_is_num(xs[i]) for i in idx):
        idx.sort(key=lambda i: xs[i])
    return idx


def _sort_xy(g, xs, ys, sort_x):
    idx = _sort_xy_idx(xs, ys, sort_x)
    return [xs[i] for i in idx], [ys[i] for i in idx]


def _err_fields(espec):
    """errorbar spec 里引用的列名集合（str 列名或 {lo,hi} 里的列名）。"""
    if isinstance(espec, str):
        return [espec]
    if isinstance(espec, dict):
        return [v for v in (espec.get("lo"), espec.get("hi")) if isinstance(v, str)]
    return []


def _err_vals(rows, espec, what, sid):
    """errorbar spec -> ('sym', 行对齐列表) | ('asym', lo, hi)。

    标量/列名/字面数组 为对称误差；{lo, hi} 为双侧不等误差（两侧各自再按
    标量|列名|数组 解析）。None 一律转 NaN——mpl 要求 yerr 内无 None，
    NaN 是官方「跳过该点」写法。
    """
    if espec is None:
        return None
    if isinstance(espec, dict):
        _check_keys(espec, _ERR_KEYS, f"series {sid} {what}")
        if "lo" not in espec or "hi" not in espec:
            raise SpecError(
                f"series {sid}: {what} asymmetric error needs both 'lo' and 'hi'"
            )
        lo = [
            np.nan if v is None else v
            for v in _vals(rows, espec["lo"], f"{what}.lo", sid)
        ]
        hi = [
            np.nan if v is None else v
            for v in _vals(rows, espec["hi"], f"{what}.hi", sid)
        ]
        return ("asym", lo, hi)
    col = [np.nan if v is None else v for v in _vals(rows, espec, what, sid)]
    return ("sym", col)


def _take_err(pack, idx):
    """行对齐的 errorbar 列按绘制索引 idx 取子集。"""
    if pack is None:
        return None
    if pack[0] == "asym":
        return [[pack[1][i] for i in idx], [pack[2][i] for i in idx]]
    return [pack[1][i] for i in idx]


def _take_rows(v, n_rows, idx):
    """行对齐值列按绘制索引取子集；非标量且长度≠行数则原样返回
    （长度对不上的交给 mpl 响亮报错，不在这里静默截断）。"""
    if isinstance(v, (list, tuple, np.ndarray)) and len(v) == n_rows:
        return [v[i] for i in idx]
    return v


def _map_err_cats(pack, xcat, cats):
    """行对齐的 errorbar 列映射到类别网格（与 _draw_bar 的 ymap 同口径）。"""
    if pack is None:
        return None

    def mp(col):
        m = dict(zip(xcat, col))
        return [m.get(c, np.nan) for c in cats]

    if pack[0] == "asym":
        return [mp(pack[1]), mp(pack[2])]
    return mp(pack[1])


def _draw_errbar(ax, xs, ys, xerr, yerr, merged, ecolor, ctx, pid):
    """一组的误差棒 overlay；xs/ys 是最终绘制坐标（已过滤/排序）。"""
    if xerr is None and yerr is None:
        return
    kw = {
        # fmt="none" 的 data line 不可见但仍占 ax.lines 且默认吃 C0——
        # color 跟随 ecolor 让它落在调色板内（OFFPALETTE 不豁免 fv-* gid）
        "fmt": "none",
        "color": ecolor,
        "ecolor": ecolor,
        "elinewidth": 0.7,
        "capsize": 1.6,
        "capthick": 0.7,
        "zorder": merged.get("zorder"),
    }
    # errprops 是误差棒的造型透传口（capsize/elinewidth/capthick/ecolor）——
    # props-win 惯例：显式声明顶掉上面的注入默认
    kw.update(_resolve_props(merged.get("errprops"), ctx, ctx.lint_proxy(pid)))
    cont = ax.errorbar(
        xs,
        ys,
        xerr=xerr,
        yerr=yerr,
        **{k: v for k, v in kw.items() if v is not None},
    )
    # ErrorbarContainer = (data_line, caplines-tuple, barcols-tuple)；
    # 逐 artist 打 fv-neutral gid，cap 线不进 audit 的 series 计数
    stack = list(cont)
    while stack:
        it = stack.pop()
        if it is None:
            continue
        if isinstance(it, (list, tuple)):
            stack.extend(it)
        else:
            _mark(it)


def _style_kwargs(g, merged):
    kw = {}
    if merged.get("ls") is not None:
        kw["linestyle"] = merged["ls"]
    if merged.get("lw") is not None:
        kw["linewidth"] = merged["lw"]
    if merged.get("ms") is not None:
        kw["markersize"] = merged["ms"]
    if merged.get("mew") is not None:
        kw["markeredgewidth"] = merged["mew"]
    if merged.get("draw") is not None:
        kw["drawstyle"] = merged["draw"]
    if merged.get("alpha") is not None:
        kw["alpha"] = merged["alpha"]
    if merged.get("zorder") is not None:
        kw["zorder"] = merged["zorder"]
    if g.marker is not None:
        kw["marker"] = g.marker
    return kw


def _legend_label(rec, g):
    want = rec.merged.get("legend")
    if want is False:
        return None
    if g.label is not None:
        return g.label
    if want is True:
        return rec.id
    return None


_PROP_COLOR_KEYS = {
    "color",
    "colors",
    "edgecolor",
    "edgecolors",
    "facecolor",
    "c",
    "markeredgecolor",
    "markerfacecolor",
    "mec",
    "mfc",
    "ec",
    "fc",
}


def _prop_color(v, ctx, lint):
    """props 单值颜色走完整 resolve：调色板 token、registry/ramp 引用
    （'fam:Key'、'palette:2'）、#rrggbb 与系列 color 字段同口径；resolve
    拒收但 mpl 认识的原生颜色（'red'、'0.3'、'tab:blue'）原样放行，其余
    原样抛 SpecError（unresolved-color 带候选），不再穿透到 mpl 炸裸
    ValueError。"""
    if not isinstance(v, str):
        return v
    try:
        out = ctx.colors.resolve(v, lint)
    except SpecError as e:
        try:
            to_rgba(v)
        except ValueError:
            raise e from None
        return v
    if not isinstance(out, str):
        raise SpecError(
            f"props color {v!r}: 'parent'/per-row color specs have no "
            f"meaning inside props"
        )
    return out


def _edge_color(v, ctx, lint, sid):
    """scatter/donut 一等 edgecolor：与 _prop_color 同口径走完整 resolve
    （调色板 token、'fam:Key' registry/ramp 引用、'palette:i'）；resolve
    拒收但 mpl 认识的原生颜色（'white'/'none'/'tab:blue'）原样放行，
    其余响亮报错——不留「引用没解析被 mpl 炸成 ValueError」的洞。"""
    if not isinstance(v, str):
        return v
    try:
        out = ctx.colors.resolve(v, lint)
    except SpecError as e:
        try:
            to_rgba(v)
        except ValueError:
            raise SpecError(f"series {sid}: edgecolor: {e}") from None
        return v
    if not isinstance(out, str):
        raise SpecError(
            f"series {sid}: edgecolor {v!r}: 'parent'/per-row color specs "
            f"have no meaning here"
        )
    return out


def _resolve_props(props, ctx, lint=None):
    """series/axis/legend props 直通 mpl 前把调色板 token 换成 hex：
    'color':'vteal' 不经解析会在 mpl 侧炸成不可读 ValueError。嵌套 dict
    （arrowprops/boxprops/wedgeprops）递归处理；非颜色键原样。"""
    if ctx is None:
        return dict(props or {})
    lint = lint if lint is not None else ctx.lint
    out = {}
    for k, v in (props or {}).items():
        if isinstance(v, dict):
            out[k] = _resolve_props(v, ctx, lint)
        elif k.lower() in _PROP_COLOR_KEYS:
            if isinstance(v, (list, tuple)):
                out[k] = [_prop_color(x, ctx, lint) for x in v]
            else:
                out[k] = _prop_color(v, ctx, lint)
        else:
            out[k] = v
    return out
