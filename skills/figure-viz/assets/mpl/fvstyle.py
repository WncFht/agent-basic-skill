"""fvstyle.py — matplotlib 侧共享 token，与 assets/tikz/vizstyle.tex 共用同一调色板。

scripts/check_palette.py 校验两个文件的 hex 一致；改色必须两侧同步。

用法:
    import fvstyle as fv
    theme = fv.apply_rc("paper")          # 设置 rcParams，返回 ThemePreset
    colors = fv.series_colors("paper", n) # 取前 n 个系列色
    marks = fv.series_markers("paper", n)
    fv.apply_frame(ax, theme.frame); fv.apply_grid(ax, theme.grid)
    fv.mark_neutral(artist)               # 手写 overlay 标成审计中性（gid fv-neutral）
    cmap = fv.ramp_cmap("seq")            # 语义色带：seq paper→vteal / div 发散
    problems = fv.audit(fig)              # 渲染后审计，规则名见 RENDER_RULES
    fv.overlay(fig, "dbg.overlay.png")    # 渲染后几何覆盖层（rb-* 同款测量）
"""

from __future__ import annotations

import copy
import itertools
import logging
import re
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colormaps, font_manager
from matplotlib.artist import Artist
from matplotlib.collections import PathCollection, QuadMesh
from matplotlib.colors import LinearSegmentedColormap, to_hex, to_rgb, to_rgba
from matplotlib.container import BarContainer
from matplotlib.contour import QuadContourSet
from matplotlib.ft2font import FT2Font
from matplotlib.image import AxesImage
from matplotlib.patches import Rectangle, Wedge
from matplotlib.text import Annotation, Text
from matplotlib.transforms import IdentityTransform

# --- 调色板（与 vizstyle.tex 一一对应） -------------------------------------

HUES = {
    "vteal": "#4F8FA5",
    "vorange": "#EE995B",
    "vcoral": "#C95B5B",
    "vviolet": "#8A74B5",
    "vgreen": "#6FA287",
    "vgold": "#D9A93C",
    "vblue": "#5478A0",
    "vrose": "#B9748F",
    "vgray": "#85898F",
}

NEUTRALS = {
    "vink": "#3A3F45",
    "vmist": "#D8DBDE",
    "paper": "#FFFFFF",
    "baseline": "#85898F",  # == vgray，参考线语义别名
}

SERIES_ORDER = [
    "vteal",
    "vorange",
    "vcoral",
    "vviolet",
    "vgreen",
    "vgold",
    "vblue",
    "vrose",
    "vgray",
]

PALETTES = {
    # 多系列均衡：按 SERIES_ORDER 顺序取
    "paper": [HUES[k] for k in SERIES_ORDER],
    # 单系列强调：第一色突出，其余退成灰阶
    "accent": [HUES["vteal"], HUES["vgray"], "#B9BDC2", "#D3D6DA", "#EBEDEF"],
    # 单色论文风：ink 到 mist 的灰阶
    "mono": ["#3A3F45", "#6B7178", "#9AA0A7", "#C4C8CD", "#E3E5E8"],
}

EDGE = {
    k + "_edge": v
    for k, v in {
        "vteal": "#3A6E80",
        "vorange": "#C47A3E",
        "vcoral": "#9E4444",
        "vviolet": "#6B5791",
        "vgreen": "#537C66",
        "vgold": "#A8842C",
        "vblue": "#3F5C7C",
        "vrose": "#93596F",
        "vgray": "#62676D",
    }.items()
}

MARKER_PRESETS = {
    "standard": ("o", "s", "^", "D", "P", "X", "v", "*"),
    "contrast": ("o", "^", "D", "X", "*", "s", "P", "v"),
}

LINE_PRESETS = {
    "with-reference": {
        "primary": "-",
        "secondary": "-",
        "reference": "--",
        "grid": "--",
    },
    "with-dotted-grid": {
        "primary": "-",
        "secondary": "-",
        "reference": "--",
        "grid": ":",
    },
    "dashed-secondary": {
        "primary": "-",
        "secondary": "--",
        "reference": ":",
        "grid": "--",
    },
}


@dataclass(frozen=True)
class ThemePreset:
    name: str
    palette: str
    markers: str
    line_preset: str
    frame: str
    grid: str
    emphasis: str


THEMES = {
    "paper": ThemePreset(
        "paper", "paper", "standard", "with-reference", "closed", "y-only", "balanced"
    ),
    "accent": ThemePreset(
        "accent",
        "accent",
        "standard",
        "with-reference",
        "closed",
        "y-only",
        "accent-first",
    ),
    "mono": ThemePreset(
        "mono",
        "mono",
        "contrast",
        "with-dotted-grid",
        "open",
        "full-dotted",
        "highlight-best",
    ),
}


def theme(name: str = "paper") -> ThemePreset:
    return THEMES[name]


def palette(name: str) -> list[str]:
    return PALETTES[name]


def markers(name: str) -> tuple[str, ...]:
    return MARKER_PRESETS[name]


def line_styles(name: str) -> dict[str, str]:
    return LINE_PRESETS[name]


# CJK 兜底族：缺失的西文字形永远轮不到它们，CJK 字形则从西文条目穿透到
# 已安装的那一款（Linux/Mac/Win）。font.family 必须带具体清单：泛型别名
# （"serif"）只解析到单一字体，无逐字形回退，CJK 会渲成豆腐块。
_CJK_SERIF = [
    "Noto Serif CJK SC",
    "LXGW WenKai",
    "Songti SC",
    "SimSun",
]
_CJK_SANS = [
    "Noto Sans CJK SC",
    "PingFang SC",
    "Alibaba PuHuiTi 3.0",
    "Microsoft YaHei",
    "WenQuanYi Micro Hei",
]
_FONT_STACKS = {
    "serif": {
        "font.family": [
            "Times New Roman",
            "Times",
            "STIX Two Text",
            "STIXGeneral",
            "DejaVu Serif",
            *_CJK_SERIF,
        ],
        "mathtext.fontset": "stix",
    },
    "sans": {
        "font.family": [
            "DejaVu Sans",
            "Helvetica",
            "Arial",
            *_CJK_SANS,
        ],
        "mathtext.fontset": "stix",
    },
}


def font_rc(kind: str = "serif") -> dict:
    """字体栈的 rcParams 片段；apply_rc 与 fvspec 共用。"""
    stack = dict(_FONT_STACKS[kind])
    installed = {f.name for f in font_manager.fontManager.ttflist}
    stack["font.family"] = [n for n in stack["font.family"] if n in installed]
    return stack


# audit() 的 palette-overflow 按"当前主题"的调色板长度计容量——fvspec.render
# 每次渲染都先经 apply_rc，故模块级记录即所审图的主题；手写图可用
# audit(theme_name=...) 显式覆盖。
_ACTIVE_THEME = "paper"


def apply_rc(
    theme_name: str = "paper", *, font: str = "serif", fontsize: float | None = None
) -> ThemePreset:
    global _ACTIVE_THEME  # noqa: PLW0603
    _ACTIVE_THEME = theme_name
    current = theme(theme_name)
    plt.rcParams.update(
        {
            "figure.facecolor": NEUTRALS["paper"],
            "axes.facecolor": NEUTRALS["paper"],
            "savefig.facecolor": NEUTRALS["paper"],
            "svg.fonttype": "none",
            "axes.edgecolor": NEUTRALS["vink"],
            "axes.linewidth": 0.9,
            "axes.labelcolor": NEUTRALS["vink"],
            "xtick.color": NEUTRALS["vink"],
            "ytick.color": NEUTRALS["vink"],
            "text.color": NEUTRALS["vink"],
            "grid.color": NEUTRALS["vmist"],
            "legend.frameon": False,
            "hatch.color": "white",
            "hatch.linewidth": 1.2,
            **font_rc(font),
            # 小版面（紧凑多面板、嵌入式）整体缩字的唯一入口；tick/label
            # 的 'small'/'medium' 相对名都折算自 font.size
            **({"font.size": float(fontsize)} if fontsize is not None else {}),
        }
    )
    return current


def apply_frame(ax, frame: str) -> None:
    if frame == "open":
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return
    if frame == "minimal":
        for spine in ax.spines.values():
            spine.set_visible(False)
        return
    for spine in ax.spines.values():
        spine.set_visible(True)


def apply_grid(ax, grid: str, axis: str = "y") -> None:
    if grid == "y-only":
        ax.grid(True, axis=axis, linewidth=0.8, linestyle="--", alpha=0.5)
    elif grid == "full-dotted":
        ax.grid(True, linewidth=0.7, linestyle=":", alpha=0.6)
    else:
        ax.grid(False)


def series_colors(theme_name: str, n: int) -> list[str]:
    colors = palette(theme(theme_name).palette)
    return [colors[i % len(colors)] for i in range(n)]


def series_markers(theme_name: str, n: int) -> list[str]:
    mark = markers(theme(theme_name).markers)
    return [mark[i % len(mark)] for i in range(n)]


def save(
    fig: plt.Figure,
    filename: str,
    outdir: Path | str = ".",
    formats: list[str] | None = None,
    close: bool = True,
) -> Path | list[Path]:
    """把 fig 存到 outdir/filename（300dpi、tight bbox）。

    ``formats=['png','pdf']`` 按文件名 stem 每种格式各产一份；
    ``close`` 释放 figure——要继续画或自己另存格式时传 False。
    """
    out = Path(outdir) / filename
    fmts = list(formats) if formats else [out.suffix.lstrip(".") or "png"]
    stem = out.with_suffix("") if out.suffix.lstrip(".") in fmts else out
    saved = []
    for f in fmts:
        p = stem.with_suffix("." + f)
        fig.savefig(p, dpi=300, bbox_inches="tight")
        saved.append(p)
    if close:
        plt.close(fig)
    return saved[0] if len(saved) == 1 else saved


NEUTRAL_GID = "fv-neutral"  # audit 以 'fv-' 前缀识别中性 overlay artist


def mark_neutral(*artists) -> None:
    """把手写 overlay artist 标成审计中性（gid 'fv-neutral'）。

    与 fvspec._mark 同一约定：ref/span/手绘箭头/复合 glyph 等非系列元素
    不进入 series 计数、coverage 与一致性规则；颜色仍走 OFFPALETTE。
    复合 glyph 的每个成员都要标——漏标的成员会被当成匿名系列。
    """
    for a in artists:
        if a is not None:
            a.set_gid(NEUTRAL_GID)


def ramp_cmap(name=None):
    """语义色带 colormap：'seq' paper→vteal 单端序进；'div' vcoral→paper→
    vteal 发散（中心为 paper 白）；其余名字按 mpl 注册表解析。

    与 fvspec heat 系列的 cmap 约定一致；返回独立实例，set_bad/set_under
    就地修改不污染注册板。
    """
    if name in (None, "seq"):
        return LinearSegmentedColormap.from_list(
            "fv_heat_seq", [NEUTRALS["paper"], HUES["vteal"]]
        )
    if name == "div":
        return LinearSegmentedColormap.from_list(
            "fv_heat_div",
            [HUES["vcoral"], NEUTRALS["paper"], HUES["vteal"]],
        )
    try:
        return copy.copy(colormaps[name])
    except KeyError:
        raise ValueError(
            f"unknown cmap {name!r}: built-ins are 'seq'/'div', "
            "otherwise a registered colormap name"
        ) from None


# --- 审计 ------------------------------------------------------------------
# audit() 对渲染完成的 figure 做 artist 级检查，问题串以规则名开头。
# spec 侧 lint（empty-series、empty-legend、hex-literal、pred-indistinct、
# fill-ignored、scale-ignored、unknown-ignore、ignore-unscoped——即
# fvspec.LINT_NAMES）需要 spec 上下文，artist 层无法重建，由 fvspec 在渲染期
# 产出；这里的规则覆盖所有能在任意手写 plt 图上判定的部分。

RENDER_RULES = {
    "collide": "error",
    "offpalette": "error",
    "missing-glyph": "error",
    "log-nonpositive-data": "error",
    "bar-baseline-truncated": "error",
    "data-clipped-outside-limits": "warn",
    "marker-clipped": "warn",
    "size-negative": "warn",
    "same-field-xy": "warn",
    "shared-axis-misaligned": "warn",
    "facet-ylim-mismatch": "warn",
    "missing-axis-label": "warn",
    "twin-axis-unlabeled": "warn",
    "label-color-inconsistent": "warn",
    "label-marker-inconsistent": "warn",
    "legend-overlaps-data": "warn",
    "text-overlaps-data": "warn",
    "text-spills-axes": "warn",
    "text-outside-figure": "warn",
    "text-too-small": "warn",
    "cjk-in-mathtext": "warn",
    "low-contrast": "warn",
    "legend-coverage": "warn",
    "duplicate-legend-label": "warn",
    "tag-sequence": "warn",
    "hue-budget": "warn",
    "cvd-clash": "warn",
    "palette-overflow": "warn",
    "print-fit": "warn",
    "rb-text-outside": "warn",
    "rb-text-collide": "warn",
    "rb-label-diff": "warn",
}

# rb-* 是渲染后回读层（post-draw readback）：fig.canvas.draw() 之后用
# renderer 实测 device-px 包围盒再判，与声明式坐标检查互补——声明坐标
# 不等于渲染坐标（m07：mpl 量着没事、产物被裁；spec ax2 系列被图例
# 静默丢弃）。几何两条（rb-text-outside/rb-text-collide）对任意图有效；
# rb-label-diff 只在 audit(declared=...) 拿到声明文本集时才有意义
# （imperative 路径没有 spec，自动跳过）。语义细节见
# references/charts/readback.md。
RB_RULES = {n for n in RENDER_RULES if n.startswith("rb-")}

# 论文槽位物理宽（英寸），与 fvspec.SIZE_SLOTS 同值——fvstyle 不能反引
# fvspec（循环依赖），两份常量靠注释与 review 保持一致。
SIZE_SLOTS = {"full": 5.5, "half": 2.70, "third": 1.77}
PRINT_FIT_MIN_PT = 5.5  # 降采样后仍须可读的最小有效字号

# spec 层 colors.extend / registry / ramp 的合法色，经 register_colors() 或
# audit(extra_palette=...) 放行；项目色应注册而不是跟审计对抗。
PALETTE_EXTENSIONS: set[str] = set()

_TAG_RE = re.compile(r"^\(([a-zA-Z])\)")


def register_colors(*colors) -> None:
    """把 spec 层 extend 的 hex 注册进合法色集合，OFFPALETTE 放行。"""
    for c in colors:
        h = _hex(c)
        PALETTE_EXTENSIONS.add(h or str(c).lower())


def _hex(color) -> str | None:
    try:
        return to_hex(color).lower()
    except (ValueError, TypeError):
        return None


def _as_color_list(c) -> list:
    """get_*color() 可能返回 str、单个 RGBA tuple、或 (N,4) ndarray，统一成列表。"""
    if c is None or isinstance(c, str):
        return [c]
    arr = np.asarray(c, dtype=float)
    if arr.ndim == 1 and arr.size in (3, 4):
        return [tuple(arr)]
    if arr.ndim == 2 and arr.shape[1] in (3, 4):
        return [tuple(row) for row in arr]
    return []


def _palette_allowed(extra: set[str] | None = None) -> set[str]:
    """本次审计的合法 hex 集合（调色板 + 中性色 + 边色 + 注册扩展）。"""
    allowed = {v.lower() for v in HUES.values()}
    allowed |= {v.lower() for v in NEUTRALS.values()}
    allowed |= {v.lower() for v in EDGE.values()}
    allowed |= {c.lower() for pal in PALETTES.values() for c in pal}
    allowed |= {"#000000", "#ffffff"}
    allowed |= PALETTE_EXTENSIONS
    if extra:
        allowed |= extra
    return allowed


def _on_palette(color, allowed: set[str]) -> bool:
    """颜色（任意 matplotlib 可解析形式）是否在合法集合之内。"""
    if color is None:
        return True
    hexv = _hex(color)
    if hexv is None:
        return True
    return hexv in allowed


def _axes_cmap_samples(ax) -> list[np.ndarray]:
    """axes 上 array 映射 artist 的 cmap 可达 RGB 集（每项为 (N,3) 采样数组）。

    streamplot 的 FancyArrowPatch 等 cmap 化 artist 没有 get_array——颜色
    确实由活跃 cmap 产出，但接口上看不出映射关系；用它做 offpalette 的
    二级豁免（与 array 映射的既定豁免同一语义：颜色是数据映射产物，不是
    离板手选色）。
    """
    samples = []
    for m in itertools.chain(ax.collections, ax.images, ax.lines, ax.patches):
        get_arr = getattr(m, "get_array", None)
        get_cmap = getattr(m, "get_cmap", None)
        if get_arr is None or get_cmap is None:
            continue
        try:
            if get_arr() is None:
                continue
            cmap = get_cmap()
            samples.append(np.asarray(cmap(np.linspace(0, 1, 2048)))[:, :3])
        except Exception:
            continue
    return samples


_CMAP_TOL = 0.01  # cmap 曲线采样容差（每通道）；2048 点覆盖下误吞窗口极小


def _on_cmap(color, samples: list[np.ndarray]) -> bool:
    """颜色是否落在某个 cmap 的可达范围内（按 RGB 逐通道容差）。"""
    try:
        rgb = np.asarray(to_rgb(color), dtype=float)
    except (ValueError, TypeError):
        return False
    return any(bool((np.abs(s - rgb).max(axis=1) <= _CMAP_TOL).any()) for s in samples)


def _is_data_transform(art, ax) -> bool:
    """artist 是否画在数据坐标系（axhline/axvspan 等混合变换不算数据）。

    Patch 的 get_transform() 组合了 patch_transform（如 Rectangle 的单位方块
    →数据矩形映射），坐标系只看 Artist.get_transform() 的 set 变换；
    scatter 偏移点在 get_offset_transform() 上。两种都探针比对实际映射。
    """
    candidates = [Artist.get_transform(art)]
    off = getattr(art, "get_offset_transform", None)
    if off is not None:
        candidates.append(off())
    try:
        pts = np.array([[0.0, 0.0], [1.0, 1.0]])
        want = ax.transData.transform(pts)
    except Exception:
        return False
    for t in candidates:
        if t is None:
            continue
        if t is ax.transData:
            return True
        try:
            if np.allclose(t.transform(pts), want):
                return True
        except Exception:
            continue
    return False


def _fv_neutral(art) -> bool:
    """spec 层标记的中性 artist（gid 'fv-*'）：ref/span/note/band/pred 等
    依附 overlay 与图例装饰，不算数据系列，不进任何 series 语义规则。"""
    gid_fn = getattr(art, "get_gid", None)
    gid = gid_fn() if gid_fn is not None else None
    return isinstance(gid, str) and gid.startswith("fv-")


def _real_label(label) -> bool:
    return bool(label) and not str(label).startswith("_")


def _series(ax) -> list[tuple[str, str, object]]:
    """axes 上的数据系列：(kind, label, artist)，kind ∈ line/coll/bar/patch/img。

    gid 'fv-*' 的中性 overlay 一律不算；polar 轴上无标 artist（spoke、wedge、
    参考弧）视为结构元素也不算。img = ax.images 的栅格层——image 面板/叠图
    底图算内容承担者，使 image-only 轴不再被当成空轴。
    """
    polar = ax.name == "polar"
    out = []
    for ln in ax.lines:
        if (
            ln.get_visible()
            and not _fv_neutral(ln)
            and (not polar or _real_label(ln.get_label()))
            and _is_data_transform(ln, ax)
        ):
            out.append(("line", ln.get_label(), ln))
    for coll in ax.collections:
        if (
            coll.get_visible()
            and not _fv_neutral(coll)
            and (not polar or _real_label(coll.get_label()))
            and _is_data_transform(coll, ax)
        ):
            out.append(("coll", coll.get_label(), coll))
    boxed: set[int] = set()
    for cont in getattr(ax, "containers", []):
        if not isinstance(cont, BarContainer):
            continue
        boxed.update(id(p) for p in cont.patches)
        if _fv_neutral(cont) or (polar and not _real_label(cont.get_label())):
            continue
        out.append(("bar", cont.get_label(), cont))
    for p in ax.patches:
        if (
            isinstance(p, Rectangle)
            and p.get_visible()
            and id(p) not in boxed
            and not _fv_neutral(p)
            and (not polar or _real_label(p.get_label()))
            and _is_data_transform(p, ax)
        ):
            out.append(("patch", p.get_label(), p))
    for im in ax.images:
        if (
            im.get_visible()
            and not _fv_neutral(im)
            and (not polar or _real_label(im.get_label()))
            and _is_data_transform(im, ax)
        ):
            out.append(("img", im.get_label(), im))
    return out


def _first_color(colors) -> str | None:
    for c in _as_color_list(colors):
        h = _hex(c)
        if h is not None:
            return h
    return None


def _series_color(kind, art) -> str | None:
    if kind == "line":
        return _hex(art.get_color())
    if kind == "coll":
        return _first_color(art.get_facecolor()) or _first_color(art.get_edgecolor())
    if kind == "img":
        return None  # 栅格图无单一系列色（array-mapped 语义同 QuadMesh）
    patches = art.patches if kind == "bar" else [art]
    for p in patches:
        h = _hex(p.get_facecolor())
        if h is not None:
            return h
    return None


def _artist_any_color(art) -> str | None:
    for attr in ("get_color", "get_facecolor", "get_edgecolor", "get_markerfacecolor"):
        fn = getattr(art, attr, None)
        if fn is not None:
            c = _first_color(fn())
            if c is not None:
                return c
    return None


def _marker_key(art):
    """scatter marker 的路径顶点指纹；无路径返回 None。"""
    get = getattr(art, "get_paths", None)
    if get is None or not get():
        return None
    return tuple(np.round(get()[0].vertices, 3).ravel())


def _cat_ticklabels(ax) -> list[str]:
    """x/y 轴上的非数值刻度标签 = 类别名就地标注（box/violin 的分布名、
    bar 的类目）。数字/百分比/千分位都按数值处理不算身份标注。"""
    out = []
    for getter in (ax.get_xticklabels, ax.get_yticklabels):
        for t in getter():
            s = t.get_text().strip()
            if not s:
                continue
            try:
                float(s.replace("−", "-").rstrip("%").replace(",", ""))
            except ValueError:
                out.append(s)
    return out


def _cat_identifiable(items, ax) -> bool:
    """类别刻度能否充当就地身份标注：仅当全部 items 都是非散点 coll
    （violin 的 PolyCollection 身体、box 的复合线件）。bar/line/scatter
    的类别刻度定位的是轴位置而非系列身份，不能豁免 legend 义务。"""
    if not items or not _cat_ticklabels(ax):
        return False
    return all(
        kind == "coll" and not isinstance(art, PathCollection)
        for kind, _lab, art in items
    )


def _sibling_ylabel(ax) -> bool:
    """sharey 组内兄弟轴带非空 ylabel——非首位成员轴的 ylabel 被 sharey
    收起，但组内任一兄弟渲染出的标签即标注了全组的量纲（与
    missing-axis-label 的 _shared_label 同口径）。"""
    return any(
        s is not ax and s.get_ylabel().strip()
        for s in ax.get_shared_y_axes().get_siblings(ax)
    )


def _style_key(kind, art):
    if kind == "line":
        return (_series_color(kind, art), art.get_linestyle(), art.get_marker())
    if kind == "coll":
        return (_series_color(kind, art), _marker_key(art))
    if kind == "img":
        return (None, None)  # 栅格无样式指纹——同色同形自然不可区分
    patches = art.patches if kind == "bar" else [art]
    hatch = patches[0].get_hatch() if len(patches) else None
    return (_series_color(kind, art), hatch)


def _num_or_index(data) -> np.ndarray:
    """坐标数值化；类别轴（字符串等无法转 float 的取值）退化为位置 0..n-1。

    mpl 的类别 unit 把 str 类别画在整数位上，用位置索引与实际渲染一致，
    且绝不让审计在合法输入上抛 ValueError。
    """
    try:
        return np.asarray(data, dtype=float)
    except (ValueError, TypeError):
        return np.arange(len(data), dtype=float)


def _series_points(kind, art) -> np.ndarray:
    """系列的数据坐标顶点（Nx2）；bar/patch 取矩形对角点。"""
    pts = np.empty((0, 2))
    if kind == "line":
        x = _num_or_index(art.get_xdata())
        y = _num_or_index(art.get_ydata())
        n = min(len(x), len(y))
        pts = np.column_stack([x[:n], y[:n]])
    elif kind == "coll":
        # offsets 只在 PathCollection(scatter) 里是数据点；PolyCollection
        # (fill_between) 等会返回默认 [[0,0]]，必须走 get_paths 顶点。
        paths = art.get_paths()
        if isinstance(art, PathCollection) or not len(paths):
            off = np.asarray(art.get_offsets(), dtype=float)
            if off.size:
                pts = off.reshape(-1, 2)
        else:
            vs = [p.vertices for p in paths]
            pts = np.vstack(vs) if vs else pts
    elif kind == "img":
        x0, x1, y0, y1 = art.get_extent()
        pts = np.array([[x0, y0], [x1, y1]])
    else:
        patches = art.patches if kind == "bar" else [art]
        vs = []
        for p in patches:
            x, y = p.get_x(), p.get_y()
            w, h = p.get_width(), p.get_height()
            vs += [[x, y], [x + w, y + h]]
        pts = np.asarray(vs) if vs else pts
    if not len(pts):
        return pts
    return pts[np.isfinite(pts).all(axis=1)]


def _all_axes(fig) -> list:
    """fig 的全部 axes：fig.get_axes() + 各 axes 的 child_axes。

    inset_axes/secondary_*axis 只挂在宿主的 child_axes 上、不进 fig.axes；
    子轴追加在尾部，既有 fig axes 的索引保持稳定——audit 的
    ignore_axes/scoped_ignore int 索引覆盖扩展后的完整序列。
    """
    axes = list(fig.get_axes())
    i = 0
    while i < len(axes):
        for ch in getattr(axes[i], "child_axes", ()):
            if ch not in axes:
                axes.append(ch)
        i += 1
    return axes


def _container_texts(artists, skip=()):
    """artist 容器子树里携带的可见 Text（offsetbox 系：AnchoredOffsetbox/
    TextArea/HPacker…，Table 的单元格同理）。

    `ax.add_artist`/`fig.add_artist` 注入的文本不进 `ax.texts`/`fig.texts`——
    没有这层递归，collide/rb-*/offpalette/missing-glyph 全链对它们失明
    （audit-blindspot 实证；mpl≥3.9 里 `ax.add_artist(Text)` 会进 ax.texts，
    真正的盲区是 offsetbox 容器树）。

    不可见子树整支跳过：子节点的 device transform 只在祖先 draw 时才被定位，
    未定位子树会量出画布原点的假框。skip 为已由专用通道收割的容器（axes/
    figure 的 legend）——它们的文本经 get_legend()/fig.legends 拿到，不重复。
    """
    skip = set(skip)
    stack = [a for a in artists if a not in skip and a.get_visible()]
    while stack:
        node = stack.pop()
        if isinstance(node, Text):
            if node.get_visible():
                yield node
            continue
        get_vis = getattr(node, "get_visible", None)
        if get_vis is not None and not get_vis():
            continue
        get_ch = getattr(node, "get_children", None)
        if get_ch is not None:
            stack.extend(get_ch())


def _iter_texts(fig):
    """(ax, kind, Text)。kind ∈ xtick/ytick/label/text；ax 为 None 表示 figure 级。

    同一 Text 只出一次：mpl≥3.9 的 add_artist(Text) 会同时落进注册列表与
    容器树，重复产出会让 collide 把它跟自己配对。"""
    seen: set[int] = set()

    def _new(t):
        if id(t) in seen:
            return False
        seen.add(id(t))
        return True

    for ax in _all_axes(fig):
        for t in ax.get_xticklabels():
            yield ax, "xtick", t
        for t in ax.get_yticklabels():
            yield ax, "ytick", t
        yield ax, "label", ax.xaxis.label
        yield ax, "label", ax.yaxis.label
        yield ax, "label", ax.title
        for t in ax.texts:
            if _new(t):
                yield ax, "text", t
        leg = ax.get_legend()
        if leg is not None:
            for t in leg.get_texts():
                if _new(t):
                    yield ax, "text", t
        if ax.get_visible():
            for t in _container_texts(ax.artists, (leg,)):
                if _new(t):
                    yield ax, "text", t
    for t in fig.texts:
        if _new(t):
            yield None, "text", t
    fig_legs = list(getattr(fig, "legends", []))
    for leg in fig_legs:
        for t in leg.get_texts():
            if _new(t):
                yield None, "text", t
    for t in _container_texts(getattr(fig, "artists", ()), fig_legs):
        if _new(t):
            yield None, "text", t


def _text_boxes(fig: plt.Figure):
    """可见文本的 (s, bbox, kind, ax, Text)。

    视区外的刻度标签 mpl 绘制时剪掉，不算；共享轴的孪生 axes（twinx/twiny）
    会产生内容+位置完全相同的刻度文本，去重后只算一次。
    """
    renderer = fig.canvas.get_renderer()
    ax_bb = {}
    seen: set[tuple] = set()
    for ax, kind, t in _iter_texts(fig):
        s = t.get_text().strip()
        if not s or not t.get_visible():
            continue
        # Annotation.get_window_extent 返回文本+箭头的并集——审计各规则只认
        # 文本框（箭头跨线不是文字遮挡），直接调 Text 的实现量文本
        if isinstance(t, Annotation):
            check_xy = getattr(t, "_check_xy", None)
            if check_xy is not None and not check_xy(renderer):
                continue  # annotation_clip 吃掉、未绘制的文本没有墨迹
            bb = Text.get_window_extent(t, renderer)
        else:
            bb = t.get_window_extent(renderer=renderer)
        if not (bb.width > 0 and bb.height > 0):
            continue
        if kind in ("xtick", "ytick") and ax.name != "polar":
            # polar 刻度标签本就画在轴框外
            ab = ax_bb.setdefault(ax, ax.get_window_extent(renderer))
            lo, hi = (ab.x0, ab.x1) if kind == "xtick" else (ab.y0, ab.y1)
            mid = ((bb.x0 + bb.x1) / 2) if kind == "xtick" else ((bb.y0 + bb.y1) / 2)
            if not (lo - 2 <= mid <= hi + 2):
                continue  # 刻度在 view interval 之外，不会被画出
        key = (s, tuple(round(v, 1) for v in bb.bounds))
        if key in seen:
            continue
        seen.add(key)
        yield s[:24], bb, kind, ax, t


def _is_colorbar(ax) -> bool:
    return getattr(ax, "_colorbar", None) is not None


def _pos_key(ax, ndigits=3):
    p = ax.get_position()
    return (
        round(p.x0, ndigits),
        round(p.y0, ndigits),
        round(p.x1, ndigits),
        round(p.y1, ndigits),
    )


def _dedupe_positions(axes) -> list:
    """丢掉与更早 axes 位置完全相同的（twin/overlay），保留先创建的宿主。"""
    seen, out = set(), []
    for ax in axes:
        key = _pos_key(ax)
        if key not in seen:
            seen.add(key)
            out.append(ax)
    return out


def _inside_other(ax, all_axes) -> bool:
    """ax 的包围盒严格落在另一个 axes 内部 → inset/zoom axes。"""
    p = ax.get_position()
    for o in all_axes:
        if o is ax:
            continue
        q = o.get_position()
        if p.x0 > q.x0 and p.y0 > q.y0 and p.x1 < q.x1 and p.y1 < q.y1:
            return True
    return False


def _is_later_overlay(ax, all_axes) -> bool:
    """与更早创建的 axes 位置相同 → twinx/twiny 的孪生轴。"""
    for o in all_axes:
        if o is ax:
            return False
        if _pos_key(o) == _pos_key(ax):
            return True
    return False


def _is_array_mapped(art) -> bool:
    """colormap 数据映射（c=array/cmap/pcolormesh）——颜色由色条承担，不是系列色。"""
    get = getattr(art, "get_array", None)
    return get is not None and get() is not None


def _pos_overlap(ax, other) -> float:
    """两 axes 位置的交叠占比（交面积 / 较小者面积）。"""
    p, q = ax.get_position(), other.get_position()
    inter = max(0.0, min(p.x1, q.x1) - max(p.x0, q.x0)) * max(
        0.0, min(p.y1, q.y1) - max(p.y0, q.y0)
    )
    denom = min(p.width * p.height, q.width * q.height)
    return inter / denom if denom > 0 else 0.0


def _axes_joined(ax, other, dim) -> bool:
    """两 axes 是否共享 dim 轴（sharex/sharey 组）。"""
    grp = ax.get_shared_x_axes() if dim == "x" else ax.get_shared_y_axes()
    return grp.joined(ax, other)


def _is_secondary(ax, all_axes) -> bool:
    """secondary_xaxis/yaxis 的辅助刻度轴：mpl 的 SecondaryAxis 类，渲染后
    位置退化成贴着宿主脊线的细条（宽或高 ≈0）；类名对不上时退化位置 +
    child_axes 归属同样能认出来。"""
    if type(ax).__name__ == "SecondaryAxis":
        return True
    p = ax.get_position()
    return min(p.width, p.height) < 1e-3 and any(
        ax in getattr(o, "child_axes", ()) for o in all_axes if o is not ax
    )


def _twin_host(ax, all_axes):
    """ax 若是孪生/辅助刻度成员，返回更早创建的宿主 axes；否则 None。

    - twinx/twiny：共享一条轴且位置几乎重合（≥0.9 交叠）。宿主经 colorbar
      或手动 set_position 移位后 _is_later_overlay 的等位判定失效，交叠
      判定仍成立；严格内含宿主的是 inset，不算孪生
    - secondary_*axis：宿主 child_axes 里的成员（位置已退化，不靠交叠）
    """
    secondary = _is_secondary(ax, all_axes)
    for o in all_axes:
        if o is ax:
            return None
        if ax in getattr(o, "child_axes", ()):
            if secondary:
                return o
            continue  # 真 inset：宿主不是孪生对象
        if (
            (_axes_joined(ax, o, "x") or _axes_joined(ax, o, "y"))
            and _pos_overlap(ax, o) >= 0.9
            and not _inside_other(ax, (o,))
        ):
            return o
    return None


def _text_size_pt(t) -> float | None:
    """Text 的生效字号（pt）；'medium' 等相对名按 rcParams['font.size'] 折算。"""
    sz = t.get_size()
    if isinstance(sz, str):
        scale = font_manager.font_scalings.get(sz)
        if scale is None:
            return None
        return scale * float(plt.rcParams.get("font.size", 10.0))
    try:
        return float(sz)
    except (TypeError, ValueError):
        return None


def _rel_luminance(rgb) -> float:
    """sRGB 相对亮度（WCAG 系数，通道先线性化）。"""

    def _lin(c) -> float:
        c = float(c)
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb[:3]
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


# Machado et al. (2009) 100% 严重度矩阵，直接作用在未线性化的 sRGB 原色
# 上——社区广泛使用的轻量近似，不是完整色觉外观模型；只用来抓"模拟后
# 几乎不可区分"的系列色对，不声称复现真实色觉。
_CVD_MATRICES = {
    "protanopia": np.array(
        [
            [0.152286, 1.052583, -0.204868],
            [0.114503, 0.786281, 0.099216],
            [-0.003882, -0.048116, 1.051998],
        ]
    ),
    "deuteranopia": np.array(
        [
            [0.367322, 0.860646, -0.227968],
            [0.280085, 0.672501, 0.047413],
            [-0.011820, 0.042940, 0.968881],
        ]
    ),
}
# 调色板内最小模拟色差是 vrose-vgray ≈0.007（真冲突对），其次
# vteal-vviolet ≈0.057；阈值 0.05 只报近重合，不误伤既有调色板组合。
_CVD_DELTA = 0.05


def _cvd_delta(c1, c2) -> tuple[float, str]:
    """两色在 protanopia/deuteranopia 模拟下的最小色差与对应类型。"""
    v1 = np.asarray(to_rgb(c1), dtype=float)
    v2 = np.asarray(to_rgb(c2), dtype=float)
    best, name = np.inf, ""
    for kind, m in _CVD_MATRICES.items():
        d = float(np.linalg.norm(np.clip(m @ v1, 0, 1) - np.clip(m @ v2, 0, 1)))
        if d < best:
            best, name = d, kind
    return best, name


def _resolved_font_paths(prop) -> tuple[list[str], list[str]]:
    """按 Text fontproperties 的 family 链逐个解析字体文件。

    返回 (可解析的字体路径, 未命中的 family 名)；与 mpl 绘制时的
    _find_fonts_by_props 同语义——找不到的 family 被跳过而不是报错。
    """
    found: list[str] = []
    missing: list[str] = []
    for fam in prop.get_family():
        p = prop.copy()
        p.set_family(fam)
        try:
            path = font_manager.findfont(p, fallback_to_default=False)
        except Exception:
            missing.append(str(fam))
            continue
        if str(path) not in found:
            found.append(str(path))
    return found, missing


_FT2_CACHE: dict[str, object] = {}


def _font_has_glyph(path: str, ch: str) -> bool:
    """字体文件是否含某字符；字体打不开时按含有处理（mpl 绘制会自己报）。"""
    f = _FT2_CACHE.get(path)
    if f is None:
        try:
            f = FT2Font(path)
        except Exception:
            f = False
        _FT2_CACHE[path] = f
    if f is False:
        return True
    return f.get_char_index(ord(ch)) != 0


class _LogGrab(logging.Handler):
    """临时挂到 matplotlib logger 上收割 draw 期记录（findfont 告警走
    logging 不走 warnings）。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


# --- 文本四边形几何（旋转感知的相交判定） ------------------------------------
# get_window_extent 只给旋转后的轴对齐包围盒：旋转 30–60° 的刻度标签 AABB
# 天然相交、真实四边形未必（audit-blindspot 实测虚警）。统一用凸四边形做
# 相交判定——未旋转文本的四边形即 AABB，语义不变。


def _bbox_to_quad(bb) -> np.ndarray:
    """Bbox → 四角点（device px）。"""
    return np.array(
        [[bb.x0, bb.y0], [bb.x1, bb.y0], [bb.x1, bb.y1], [bb.x0, bb.y1]],
        dtype=float,
    )


def _text_quad(t, bb, renderer) -> np.ndarray:
    """文本的渲染四边形（device px）：经 _get_layout 的旋转角点与文本位置
    精确重建；私有 API 失灵时按 AABB+角度解内接矩形（45° 附近奇异跳过），
    再失灵退回 AABB 本身——宁可回到旧行为也不让审计抛错或缩小判定框。"""
    box = _bbox_to_quad(bb)
    try:
        angle = float(t.get_rotation())
    except (TypeError, ValueError):
        return box
    if not angle % 360:
        return box
    try:
        _lb, _info, descent = t._get_layout(renderer)
        (xc, yc), (w, h) = descent
        w, h = float(w), float(h)
        x, y = t.get_transform().transform(t.get_unitless_position())
        if w > 0 and h > 0:
            rad = np.deg2rad(angle)
            c, s = np.cos(rad), np.sin(rad)
            # (xc,yc) 是未旋转矩形 (xmin,ymin) 角旋转+对齐后的落点（相对
            # 文本位置）；其余角点 = 该角 + R(angle)·[(0,0),(0,h),(w,h),(w,0)]
            local = np.array([[0.0, 0.0], [0.0, h], [w, h], [w, 0.0]])
            rotm = np.array([[c, s], [-s, c]])
            q = local @ rotm + np.array([x + xc, y + yc])
            # 重建四边形的 AABB 必须等于量到的 bb——私有 API 语义漂移时
            # 在这里被拦下退回下一级，绝不放行缩水的判定框
            if np.allclose(
                [q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()],
                [bb.x0, bb.y0, bb.x1, bb.y1],
                atol=1.0,
            ):
                return q
    except (AttributeError, TypeError, ValueError):
        pass
    rad = np.deg2rad(angle)
    c, s = abs(np.cos(rad)), abs(np.sin(rad))
    det = c * c - s * s
    if abs(det) > 1e-3 and bb.width > 0 and bb.height > 0:
        w = (bb.width * c - bb.height * s) / det
        h = (bb.height * c - bb.width * s) / det
        if w > 0 and h > 0:
            cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
            c2, s2 = np.cos(rad), np.sin(rad)
            local = np.array(
                [
                    [-w / 2, -h / 2],
                    [-w / 2, h / 2],
                    [w / 2, h / 2],
                    [w / 2, -h / 2],
                ]
            )
            return local @ np.array([[c2, s2], [-s2, c2]]) + np.array([cx, cy])
    return box


def _quad_area(q) -> float:
    """多边形有向面积（shoelace）。"""
    x, y = q[:, 0], q[:, 1]
    return 0.5 * float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def _seg_isect(p0, p1, a, b):
    """段 p0p1 与直线 ab 的交点（Sutherland–Hodgman 裁剪用；调用方保证存在）。"""
    d = (p1[0] - p0[0], p1[1] - p0[1])
    e = (b[0] - a[0], b[1] - a[1])
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-15:
        return p0
    t = ((p0[0] - a[0]) * e[1] - (p0[1] - a[1]) * e[0]) / den
    return (p0[0] - t * d[0], p0[1] - t * d[1])


def _quad_intersection_area(q1, q2) -> float:
    """两凸四边形的相交面积；分离或仅贴边 = 0。"""
    clip = np.asarray(q2, dtype=float)
    if _quad_area(clip) < 0:
        clip = clip[::-1]
    subj = np.asarray(q1, dtype=float)
    if _quad_area(subj) < 0:
        subj = subj[::-1]
    poly = [tuple(p) for p in subj]
    for i in range(len(clip)):
        a = clip[i]
        b = clip[(i + 1) % len(clip)]
        e = (b[0] - a[0], b[1] - a[1])

        def inside(p, _a=a, _e=e):
            return _e[0] * (p[1] - _a[1]) - _e[1] * (p[0] - _a[0]) >= -1e-9

        out = []
        prev = poly[-1]
        for cur in poly:
            if inside(cur):
                if not inside(prev):
                    out.append(_seg_isect(prev, cur, a, b))
                out.append(cur)
            elif inside(prev):
                out.append(_seg_isect(prev, cur, a, b))
            prev = cur
        poly = out
        if not poly:
            return 0.0
    if len(poly) < 3:
        return 0.0
    return abs(_quad_area(np.asarray(poly)))


def _quads_touch_or_intersect(q1, q2) -> bool:
    """凸四边形相交或相切（SAT，贴边计为相交——与 Bbox.overlaps 同口径）。"""
    for q in (q1, q2):
        for i in range(len(q)):
            e = q[(i + 1) % len(q)] - q[i]
            n = np.array([-e[1], e[0]])
            p1 = q1 @ n
            p2 = q2 @ n
            if p1.max() < p2.min() - 1e-9 or p2.max() < p1.min() - 1e-9:
                return False
    return True


def _points_in_quad(pts, q, tol=1e-9) -> np.ndarray:
    """点集是否落在凸四边形内（含边）；q 顶点须同一环绕方向。"""
    pts = np.asarray(pts, dtype=float)
    if not len(pts):
        return np.zeros(0, dtype=bool)
    edges = np.roll(q, -1, axis=0) - q
    rel = pts[:, None, :] - q[None, :, :]
    cross = edges[None, :, 0] * rel[:, :, 1] - edges[None, :, 1] * rel[:, :, 0]
    return (cross >= -tol).all(axis=1) | (cross <= tol).all(axis=1)


def _seg_crosses_quad(p0, p1, q) -> bool:
    """线段是否触到凸四边形（端点在内、穿边、贴边均计）。

    先 AABB 粗筛，再端点在内 + 逐边 seg-seg 参数相交；平行/共线的贴边
    由端点在内覆盖。
    """
    if max(p0[0], p1[0]) < q[:, 0].min() or min(p0[0], p1[0]) > q[:, 0].max():
        return False
    if max(p0[1], p1[1]) < q[:, 1].min() or min(p0[1], p1[1]) > q[:, 1].max():
        return False
    if _points_in_quad(np.array([p0, p1]), q).any():
        return True
    d = p1 - p0
    for i in range(len(q)):
        a = q[i]
        e = q[(i + 1) % len(q)] - a
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        # p0 + t·d == a + u·e；t、u 同在 [0,1] 即相交（含贴边）
        t = ((a[0] - p0[0]) * e[1] - (a[1] - p0[1]) * e[0]) / den
        u = ((a[0] - p0[0]) * d[1] - (a[1] - p0[1]) * d[0]) / den
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            return True
    return False


def _quad_covers_artist(
    qbb, ax, kind, art, renderer, *, frac=0.0, seg_cross=False
) -> bool:
    """通用『框 vs 数据墨水』遮挡判定（legend-overlaps-data 与
    text-overlaps-data 共用）。qbb 为 device-px 凸四边形。

    - bar/patch：框与 patch 窗口盒求交——frac<=0 时相交（含贴边）即中；
      frac>0 时交面积须超过较小框的 frac（rb-text-collide 惯例）
    - QuadMesh/AxesImage/QuadContourSet：整幅栅格场，框必落其上——遮挡语义
      由色条承担，恒 False（clabel 压自身等值面是同义反复，不是压数据）
    - line/coll：顶点 + 段中点落入框内即中（scatter 按 offsets）；seg_cross
      时再查段边穿越（长段无采样点落框的穿透）与填充区覆盖（fill_between
      等多边形 coll 的框角点入 path）
    """
    if kind in ("bar", "patch"):
        patches = art.patches if kind == "bar" else [art]
        for p in patches:
            pq = _bbox_to_quad(p.get_window_extent(renderer))
            if frac <= 0:
                if _quads_touch_or_intersect(qbb, pq):
                    return True
            elif _quad_intersection_area(qbb, pq) > frac * min(
                abs(_quad_area(qbb)), abs(_quad_area(pq))
            ):
                return True
        return False
    if isinstance(art, (QuadMesh, AxesImage, QuadContourSet)):
        return False
    pts = _series_points(kind, art)
    if not len(pts):
        return False
    disp = ax.transData.transform(pts)
    disp = np.vstack([disp, (disp[:-1] + disp[1:]) / 2])
    if _points_in_quad(disp, qbb).any():
        return True
    if not seg_cross:
        return False
    segs = []
    if kind == "line":
        # disp 已混入段中点，真实段要用原始顶点重算
        d0 = ax.transData.transform(pts)
        segs = [(d0[i], d0[i + 1]) for i in range(len(d0) - 1)]
    elif not isinstance(art, PathCollection):
        # PolyCollection/LineCollection 等：逐 path 的真实边（scatter 的
        # offsets 之间没有连线墨水，不查段）；填充 coll 另查框角点入面
        tr = art.get_transform()
        for path in art.get_paths():
            dp = path.transformed(tr) if tr is not None else path
            vs = dp.vertices[np.isfinite(dp.vertices).all(axis=1)]
            if len(vs) >= 3 and dp.contains_points(qbb).any():
                return True
            segs += [(vs[i], vs[i + 1]) for i in range(len(vs) - 1)]
    return any(_seg_crosses_quad(p0, p1, qbb) for p0, p1 in segs)


# --- 渲染后回读（rb-* 与 print-fit 的测量原语） ------------------------------

_TAG_PREFIX_RE = re.compile(r"^\([a-zA-Z]\)\s*")
_WS_RE = re.compile(r"\s+")
_MATH_SPACING_RE = re.compile(r"\\[,;:! ]")
# ⺀–鿿 = 2E80–9FFF（部首/表意/假名大区），另加 CJK 标点 3000–303F
# 与全角区 FF00–FFEF——cjk-in-mathtext 的判定字符集
_CJK_RE = re.compile(r"[⺀-鿿　-〿＀-￯]")


def _norm_label(s) -> str:
    """标识文本的规范化比较口径：折叠空白、去 $ 定界与数学间距命令、
    去 '(a) ' 自动面板 tag、unicode minus 归一——声明串与渲染串同走。"""
    s = str(s).strip().replace("−", "-").replace("$", "")
    s = _MATH_SPACING_RE.sub("", s)
    s = _TAG_PREFIX_RE.sub("", s)
    return _WS_RE.sub(" ", s).strip()


def _artist_labels(fig) -> set[str]:
    """图上数据系列 artist 的已解析 label 集合（模板已展开、legend 旗标已
    应用）——这是声明文本集里'系列 label'那部分最可靠的来源。"""
    out = set()
    for ax in _all_axes(fig):
        for _kind, label, _art in _series(ax):
            if _real_label(label):
                out.add(str(label).strip())
    return out


def _rendered_texts(fig) -> tuple[set, set]:
    """渲染出的文本按身份分层：(all, identity)。

    all      = 图例条目与标题 + axes 标题 + 轴标签 + ax.texts + fig.texts
               （rb-label-diff 'missing' 的查找域；刻度标签不算——声明的
               标识文本不会躲进刻度里）。
    identity = 图例条目/图例标题 + axes 标题（'extra' 只查这层——轴标签与
               ax.texts 允许来自 raw 逃生舱与数据标注，不算未声明）。
    """
    renderer = fig.canvas.get_renderer()
    allt, ident = set(), set()

    def put(t, bucket):
        s = t.get_text() if t is not None else None
        if not s or not s.strip() or not t.get_visible():
            return
        try:
            bb = t.get_window_extent(renderer=renderer)
        except Exception:
            return
        if not (bb.width > 0 and bb.height > 0):
            return
        allt.add(s.strip())
        bucket.add(s.strip())

    def put_legend(leg):
        if leg is None or not leg.get_visible():
            return
        for t in leg.get_texts():
            put(t, ident)
        put(leg.get_title(), ident)

    for ax in _all_axes(fig):
        put_legend(ax.get_legend())
        put(ax.title, ident)
        put(ax.xaxis.label, allt)
        put(ax.yaxis.label, allt)
        for t in ax.texts:
            put(t, allt)
        if ax.get_visible():
            for t in _container_texts(ax.artists, (ax.get_legend(),)):
                put(t, allt)
    fig_legs = list(getattr(fig, "legends", []))
    for leg in fig_legs:
        put_legend(leg)
    for t in fig.texts:
        put(t, allt)
    for t in _container_texts(getattr(fig, "artists", ()), fig_legs):
        put(t, allt)
    return allt, ident


def _slot_inches(print_slot) -> float | None:
    """print_slot 解析：槽位名 | 英寸数 | None。"""
    if print_slot is None:
        return None
    if isinstance(print_slot, str):
        if print_slot not in SIZE_SLOTS:
            raise ValueError(
                f"audit: unknown print_slot {print_slot!r}; "
                f"valid: {sorted(SIZE_SLOTS)} or a float of inches"
            )
        return SIZE_SLOTS[print_slot]
    try:
        return float(print_slot)
    except (TypeError, ValueError):
        raise ValueError(
            f"audit: bad print_slot {print_slot!r}; "
            f"valid: {sorted(SIZE_SLOTS)} or a float of inches"
        ) from None


def audit(
    fig: plt.Figure,
    *,
    rules=None,
    ignore=(),
    scoped_ignore=(),
    ignore_axes=(),
    extra_palette=(),
    theme_name=None,
    print_slot=None,
    declared=None,
) -> list[str]:
    """渲染后审计：返回问题描述列表，空列表 = 通过。每条以规则名开头。

    - rules        只跑给定规则名集合（默认 RENDER_RULES 全部）；未知名抛
                   ValueError——打错字不该静默关掉检查
    - ignore       全局跳过的规则名
    - scoped_ignore  (规则名, axes 索引或 axes 对象) 对——只在该 axes 上豁免
                   该规则；关系型规则（facet-ylim-mismatch、label-*）把被豁免
                   axes 移出比较组，其余成员照常检查
    - ignore_axes  免于数据几何类检查的 axes（int 索引或对象）——刻意的 zoom
                   inset、非零基线、离群裁剪等合法设计在此声明，不静默；
                   豁免沿 child_axes 传递（inset 上的孙轴同样在豁免半径内）
    - extra_palette  本次额外放行的颜色（spec 层 registry/ramp/extend hex）
    - theme_name   palette-overflow 的容量口径：主题名或 ThemePreset；默认
                   跟随最近一次 apply_rc 的主题（fvspec.render 每次渲染都会
                   先 apply_rc）
    - print_slot   print-fit 的目标槽位：'full'|'half'|'third' 或英寸数；
                   None 时按「图宽超过 full 槽才会被缩印」自动取 full
    - declared     spec 侧声明的标识文本集（series label/title/legend
                   entry/caption……），启用 rb-label-diff 差集检查；图上
                   系列 artist 的已解析 label 自动并入。None（imperative
                   路径没有 spec）时该规则跳过

    axes int 索引按 _all_axes 扩展序列计：fig.get_axes() 在前，各 axes 的
    child_axes（inset/secondary）依次追加在后——既有 fig axes 索引不变。
    调用前需 fig.canvas.draw()（本函数内部也会先 draw 一次）。
    """
    if rules is not None:
        unknown = sorted(set(rules) - set(RENDER_RULES))
        if unknown:
            raise ValueError(
                f"audit: unknown rules {unknown}; valid: {sorted(RENDER_RULES)}"
            )
    scoped_pairs = list(scoped_ignore)
    bad_scoped = sorted({rn for rn, _ in scoped_pairs} - set(RENDER_RULES))
    if bad_scoped:
        raise ValueError(
            f"audit: unknown scoped_ignore rules {bad_scoped}; "
            f"valid: {sorted(RENDER_RULES)}"
        )

    problems: list[str] = []
    active = set(RENDER_RULES if rules is None else rules) - set(ignore)

    # draw 期收割：缺字形走 warnings.warn，findfont 告警走 logging——两条
    # 通道都抓。mpl 对 text layout 与 findfont 结果有缓存，收割只覆盖本次
    # draw 内重新计算的部分；missing-glyph 规则另有确定性探测兜底。
    grab = _LogGrab()
    logging.getLogger("matplotlib").addHandler(grab)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.canvas.draw()
    finally:
        logging.getLogger("matplotlib").removeHandler(grab)
    renderer = fig.canvas.get_renderer()
    all_axes = _all_axes(fig)
    ax_index = {id(ax): i for i, ax in enumerate(all_axes)}

    scoped: dict[str, set[int]] = defaultdict(set)
    for rn, ai in scoped_pairs:
        scoped[rn].add(ai if isinstance(ai, int) else ax_index.get(id(ai), -1))

    def _scoped(rule, ax) -> bool:
        """该规则在此 axes 上被 scoped_ignore 豁免。"""
        return ax_index[id(ax)] in scoped.get(rule, ())

    ignored = {all_axes[i] if isinstance(i, int) else i for i in ignore_axes}
    # 豁免半径含全部后代轴：inset 上的 secondary/孙 inset（孙轴）同样在豁免内
    ig = list(ignored)
    while ig:
        for ch in getattr(ig.pop(), "child_axes", ()):
            if ch not in ignored:
                ignored.add(ch)
                ig.append(ch)
    axes = [ax for ax in all_axes if ax not in ignored]
    geom_axes = [ax for ax in axes if not _is_colorbar(ax)]
    series_map = {ax: _series(ax) for ax in all_axes}
    extra_hex = {h for c in extra_palette if (h := _hex(c)) is not None}

    # collide/text-outside-figure/text-too-small/low-contrast/print-fit 与
    # rb 回读层共用同一份文本包围盒采集；三条 legend 规则共用同一份
    # legend 列表；offpalette 共用 allowed 集合。
    text_boxes = None
    if {
        "collide",
        "text-outside-figure",
        "text-too-small",
        "low-contrast",
        "print-fit",
        "rb-text-outside",
        "rb-text-collide",
        "text-overlaps-data",
        "text-spills-axes",
    } & active:
        text_boxes = list(_text_boxes(fig))
    legends = None
    if {"legend-overlaps-data", "legend-coverage", "duplicate-legend-label"} & active:
        legends = [leg for ax in all_axes if (leg := ax.get_legend()) is not None]
        legends += list(getattr(fig, "legends", []))
    leg_text_ids = None
    if {"text-overlaps-data", "text-spills-axes"} & active:
        # 图例条目文本以 kind="text" 进 text_boxes 但不归文本规则管——遮挡
        # 归 legend-overlaps-data；改成按身份排除后，ax.texts 之外的
        # offsetbox 注入文本照常受检。
        leg_text_ids = {
            id(t)
            for a in all_axes
            if (leg := a.get_legend()) is not None
            for t in leg.get_texts()
        }
        leg_text_ids |= {
            id(t) for leg in getattr(fig, "legends", []) for t in leg.get_texts()
        }

    # 旋转感知的文本四边形缓存：collide/rb-text-collide/text-overlaps-data
    # 共用；未旋转文本的四边形即 AABB
    quad_cache: dict[int, np.ndarray] = {}

    def _quad_of(tb):
        tid = id(tb[4])
        q = quad_cache.get(tid)
        if q is None:
            q = _text_quad(tb[4], tb[1], renderer)
            quad_cache[tid] = q
        return q

    if "collide" in active:
        for tb1, tb2 in itertools.combinations(text_boxes, 2):
            if _quads_touch_or_intersect(_quad_of(tb1), _quad_of(tb2)):
                problems.append(f"collide text '{tb1[0]}' x '{tb2[0]}'")

    if "offpalette" in active:
        allowed = _palette_allowed(extra_hex)
        seen: set[str] = set()
        for ax in all_axes:
            cmap_samples = None  # 懒算：只在出现离板候选色时才采样 cmap
            for art in list(ax.lines) + list(ax.collections) + list(ax.patches):
                get_arr = getattr(art, "get_array", None)
                if get_arr is not None and get_arr() is not None:
                    continue  # colormap 数据映射，不逐像素套调色板
                for attr in (
                    "get_color",
                    "get_edgecolor",
                    "get_facecolor",
                    "get_markerfacecolor",
                ):
                    fn = getattr(art, attr, None)
                    if fn is None:
                        continue
                    for c in _as_color_list(fn()):
                        h = c if isinstance(c, str) else _hex(c)
                        if h is not None and not _on_palette(h, allowed):
                            # 无 get_array 的 cmap 化 artist（streamplot 的
                            # FancyArrowPatch 等）：色由本轴活跃 cmap 产出即
                            # 豁免，语义等同 array 映射的既定豁免
                            if cmap_samples is None:
                                cmap_samples = _axes_cmap_samples(ax)
                            if _on_cmap(c, cmap_samples):
                                continue
                            seen.add(h)
        for _ax, _kind, t in _iter_texts(fig):
            if t.get_visible() and t.get_text().strip():
                h = _hex(t.get_color())
                if h is not None and not _on_palette(h, allowed):
                    seen.add(h)
        for c in sorted(seen):
            problems.append(f"offpalette {c}")

    if "missing-glyph" in active:
        seen_g: set[str] = set()
        for w in caught:
            m = str(w.message).strip()
            if re.search(r"Glyph .* missing from font", m):
                seen_g.add(m)
        for m in grab.messages:
            m = m.strip()
            # mathtext 缺字形走 _log.warning（'does not have a glyph … dummy
            # symbol'），与 Text 绘制期的 missing from font 措辞不同，都要抓
            if re.search(r"findfont.*not found", m) or re.search(
                r"missing from font|does not have a glyph", m
            ):
                seen_g.add(m)
        # 确定性兜底：mpl 对 text layout 与 findfont 结果有缓存，先 draw 过
        # 的图收割不到告警——直接对每个可见 text 解析字体链、查字符覆盖率。
        # 含 $ 的串走 mathtext 字体组，探测口径不同，交给上面的收割与
        # cjk-in-mathtext 的确定性检查覆盖。
        for _ax, _kind, t in _iter_texts(fig):
            s = t.get_text()
            if not s.strip() or not t.get_visible() or "$" in s:
                continue
            prop = t.get_fontproperties()
            found, missing = _resolved_font_paths(prop)
            if not found:
                # 整条 family 链落空 → mpl 静默退回默认字体，属真问题；
                # 部分落空是正常回退（serif 栈里 Times 缺席等），不报。
                seen_g.add(
                    f"text '{s[:24]}': no family in "
                    f"{[str(f) for f in prop.get_family()]} resolved; "
                    "falls back to default font"
                )
                try:
                    found = [
                        str(
                            font_manager.findfont(
                                font_manager.FontProperties(
                                    family=font_manager.fontManager.defaultFamily["ttf"]
                                )
                            )
                        )
                    ]
                except Exception:
                    found = []
            for ch in {c for c in s if ord(c) > 127}:
                if found and not any(_font_has_glyph(p, ch) for p in found):
                    seen_g.add(
                        f"text '{s[:24]}': U+{ord(ch):04X} '{ch}' missing "
                        "from all resolved fonts"
                    )
        for m in sorted(seen_g):
            problems.append(f"missing-glyph {m}")

    if "cjk-in-mathtext" in active:
        # 含 $ 的串整体走 mathtext 字体组（默认 stix，无 CJK 字形）——CJK
        # 混排进 $ 串渲染成 tofu。missing-glyph 收割依赖 draw 时序（mpl 有
        # layout 缓存，先 draw 过的图收割不到），此检查是确定性兜底。
        # 真进 mathtext 的口径：去 \$ 转义后须有成对 $——落单的 $ 按字面渲染
        seen_cm: set[str] = set()
        for _ax, _kind, t in _iter_texts(fig):
            s = t.get_text().strip()
            n_dollar = s.replace("\\$", "").count("$")
            if (
                not s
                or n_dollar < 2
                or n_dollar % 2
                or not t.get_visible()
                or not _CJK_RE.search(s)
                or (_ax is not None and _scoped("cjk-in-mathtext", _ax))
            ):
                continue
            where = f"axes {ax_index[id(_ax)]}" if _ax is not None else "figure"
            seen_cm.add(
                f"cjk-in-mathtext {where} '{s[:24]}': CJK + '$' goes wholly "
                "through mathtext (stix fontset has no CJK) — tofu"
            )
        problems.extend(sorted(seen_cm))

    if "log-nonpositive-data" in active:
        for ax in geom_axes:
            if _scoped("log-nonpositive-data", ax):
                continue
            dims = [("x", 0)] if ax.get_xscale() == "log" else []
            dims += [("y", 1)] if ax.get_yscale() == "log" else []
            for name, idx in dims:
                for kind, label, art in series_map[ax]:
                    pts = _series_points(kind, art)
                    n = int((pts[:, idx] <= 0).sum()) if len(pts) else 0
                    if n:
                        problems.append(
                            f"log-nonpositive-data axes {ax_index[id(ax)]} {name}: "
                            f"'{label or kind}' has {n} vertices <=0 — "
                            "mixed-sign data escapes via symlog: "
                            f"set_{name}scale('symlog', linthresh=…) / "
                            f"spec {name}axis.scale='symlog' + props.linthresh"
                        )

    if "bar-baseline-truncated" in active:
        for ax in geom_axes:
            if _scoped("bar-baseline-truncated", ax):
                continue
            rects = [
                p
                for p in ax.patches
                if isinstance(p, Rectangle)
                and p.get_visible()
                and not _fv_neutral(p)
                and _is_data_transform(p, ax)
            ]
            if len(rects) < 2:
                continue
            for vert, lim, scale in (
                (True, ax.get_ylim(), ax.get_yscale()),
                (False, ax.get_xlim(), ax.get_xscale()),
            ):
                if scale != "linear":
                    continue
                lo, hi = min(lim), max(lim)
                tol = 1e-6 * (hi - lo or 1.0)
                # 先按跨轴位置分栈：同 (x,宽)（横条同 (y,高)）的矩形属同一
                # 柱栈。堆叠柱的基线是栈整体的起锚边，不是单根柱段的底边；
                # 单根柱组里每栈恰一根矩形，栈基线即柱底边。
                stacks: dict[tuple, list] = defaultdict(list)
                for p in rects:
                    key = (
                        (round(p.get_x(), 6), round(p.get_width(), 6))
                        if vert
                        else (round(p.get_y(), 6), round(p.get_height(), 6))
                    )
                    stacks[key].append(p)
                extents = []  # 每栈的 (low, high) 覆盖区间
                edge_sets = []  # 每栈内各成员矩形的 (low, high) 边
                for members in stacks.values():
                    es = []
                    for p in members:
                        a, b = (
                            (p.get_y(), p.get_y() + p.get_height())
                            if vert
                            else (p.get_x(), p.get_x() + p.get_width())
                        )
                        es.append((min(a, b), max(a, b)))
                    edge_sets.append(es)
                    extents.append((min(e[0] for e in es), max(e[1] for e in es)))
                lows = [e[0] for e in extents]
                highs = [e[1] for e in extents]
                mode = None
                if max(lows) - min(lows) <= tol:
                    baseline, mode = min(lows), "up"
                elif max(highs) - min(highs) <= tol:
                    baseline, mode = max(highs), "down"
                else:
                    # 混合符号/发散堆叠柱组：基线是每个栈内某成员矩形的公共
                    # 锚边，它在一部分柱上是低边、在另一部分上是高边（典型
                    # 即 baseline 0）
                    cands = {v for es in edge_sets[0] for v in es}
                    for cand in cands:
                        if all(
                            any(min(abs(a - cand), abs(b - cand)) <= tol for a, b in es)
                            for es in edge_sets
                        ):
                            baseline, mode = cand, "mixed"
                            break
                if mode is None:
                    continue  # 无公共锚边（瀑布等），不是同基线柱组
                axis = "y" if vert else "x"
                if mode == "mixed":
                    outside = baseline < lo - tol or baseline > hi + tol
                elif mode == "up":
                    outside = baseline < lo - tol
                else:
                    outside = baseline > hi + tol
                if outside:
                    side = "below" if baseline < lo - tol else "above"
                    end = lo if baseline < lo - tol else hi
                    problems.append(
                        f"bar-baseline-truncated axes {ax_index[id(ax)]}: "
                        f"{axis} baseline {baseline:g} {side} "
                        f"{axis}lim {end:g}"
                    )

    if "data-clipped-outside-limits" in active:
        for ax in geom_axes:
            if _scoped("data-clipped-outside-limits", ax):
                continue
            xlim, ylim = sorted(ax.get_xlim()), sorted(ax.get_ylim())
            polar = ax.name == "polar"
            for kind, label, art in series_map[ax]:
                pts = _series_points(kind, art)
                if not len(pts):
                    continue
                # polar 的 theta 越界是回绕不是裁剪（雷达闭合缝落在
                # 首角 +2π），只有径向越界才真被剪掉
                outside = (pts[:, 1] < ylim[0]) | (pts[:, 1] > ylim[1])
                if not polar:
                    outside = outside | (pts[:, 0] < xlim[0]) | (pts[:, 0] > xlim[1])
                outside = outside.mean()
                if outside > 0.05:
                    problems.append(
                        f"data-clipped-outside-limits axes {ax_index[id(ax)]} "
                        f"'{label or kind}': {outside:.0%} vertices outside limits"
                    )

    if "marker-clipped" in active:
        # 数据点在限内但 marker 半径越过 axes 边：点没丢、glyph 被裁——比
        # data-clipped 更隐蔽的静默缺墨。clip_on=False 的系列本来就允许
        # 越界，跳过不误报。
        px_per_pt = fig.dpi / 72.0
        for ax in geom_axes:
            if _scoped("marker-clipped", ax) or ax.name == "polar":
                continue
            bb = ax.bbox
            for kind, label, art in series_map[ax]:
                if kind == "line":
                    if art.get_marker() in (None, "", "None", " "):
                        continue
                    r = art.get_markersize() / 2 * px_per_pt
                elif isinstance(art, PathCollection):
                    s = np.asarray(art.get_sizes(), dtype=float)
                    s = s[np.isfinite(s)]
                    if not len(s):
                        continue
                    r = np.sqrt(s.max() / np.pi) * px_per_pt
                else:
                    continue  # bar/patch/fill 无 marker glyph
                if not art.get_clip_on():
                    continue
                pts = _series_points(kind, art)
                if not len(pts):
                    continue
                disp = ax.transData.transform(pts)
                inside = (
                    (disp[:, 0] >= bb.x0)
                    & (disp[:, 0] <= bb.x1)
                    & (disp[:, 1] >= bb.y0)
                    & (disp[:, 1] <= bb.y1)
                )
                edge = np.minimum.reduce(
                    [
                        disp[:, 0] - bb.x0,
                        bb.x1 - disp[:, 0],
                        disp[:, 1] - bb.y0,
                        bb.y1 - disp[:, 1],
                    ]
                )
                n = int((inside & (edge < r)).sum())
                if n:
                    problems.append(
                        f"marker-clipped axes {ax_index[id(ax)]} "
                        f"'{label or kind}': {n} marker(s) touch the frame"
                    )

    if "size-negative" in active:
        for ax in geom_axes:
            if _scoped("size-negative", ax):
                continue
            for coll in ax.collections:
                if (
                    not isinstance(coll, PathCollection)
                    or not coll.get_visible()
                    or _fv_neutral(coll)
                ):
                    continue
                sizes = np.asarray(coll.get_sizes(), dtype=float)
                n = int((~np.isfinite(sizes) | (sizes <= 0)).sum())
                if n:
                    label = coll.get_label()
                    problems.append(
                        f"size-negative axes {ax_index[id(ax)]} "
                        f"'{label or 'scatter'}': {n}/{sizes.size} "
                        "nonpositive/non-finite sizes"
                    )

    if "same-field-xy" in active:
        for ax in geom_axes:
            if _scoped("same-field-xy", ax):
                continue
            for coll in ax.collections:
                if (
                    not isinstance(coll, PathCollection)
                    or not coll.get_visible()
                    or _fv_neutral(coll)
                ):
                    continue
                off = np.ma.filled(
                    np.ma.asarray(coll.get_offsets(), dtype=float), np.nan
                )
                if off.ndim != 2 or off.shape[1] != 2:
                    continue
                off = off[np.isfinite(off).all(axis=1)]
                # 单点 x==y 是巧合；>=2 个点逐元素相同是复制粘贴的信号
                if len(off) >= 2 and np.array_equal(off[:, 0], off[:, 1]):
                    label = coll.get_label()
                    problems.append(
                        f"same-field-xy axes {ax_index[id(ax)]} "
                        f"'{label or 'scatter'}': x and y offsets identical"
                    )

    if "facet-ylim-mismatch" in active:
        cand = _dedupe_positions(
            [
                ax
                for ax in geom_axes
                # 纯 img 轴是像素展示格——像素无可比较量纲，不算候选
                if any(it[0] != "img" for it in series_map[ax])
                and not _is_later_overlay(ax, all_axes)
                and _twin_host(ax, all_axes) is None
                and not _scoped("facet-ylim-mismatch", ax)
            ]
        )
        # 同一物理行且全靠外部共享 ylabel（labelouter 网格）→ 必须同刻度
        rows: dict[tuple, list] = defaultdict(list)
        for ax in cand:
            p = ax.get_position()
            rows[(round(p.y0, 2), round(p.height, 2))].append(ax)
        for members in rows.values():
            if len(members) < 2:
                continue
            # 成员各自声明不同量纲（>=2 种非空 ylabel）时不同 ylim 合法；
            # 全空/共享 labelouter 标签/同一文本都按可比较行对待
            if len({ax.get_ylabel().strip() for ax in members} - {""}) >= 2:
                continue
            ref = members[0].get_ylim()
            if any(
                not np.allclose(ax.get_ylim(), ref, rtol=1e-3) for ax in members[1:]
            ):
                ylims = {
                    tuple(round(float(v), 4) for v in ax.get_ylim()) for ax in members
                }
                problems.append(
                    f"facet-ylim-mismatch row of {len(members)} axes: ylims {sorted(ylims)}"
                )
        # 不同位置但共享 ylabel 文本（声明同量纲）→ 也必须同刻度
        by_label: dict[str, list] = defaultdict(list)
        for ax in cand:
            lab = ax.get_ylabel().strip()
            if lab:
                by_label[lab].append(ax)
        for lab, members in by_label.items():
            if len(members) < 2:
                continue
            ref = members[0].get_ylim()
            if any(
                not np.allclose(ax.get_ylim(), ref, rtol=1e-3) for ax in members[1:]
            ):
                ylims = {
                    tuple(round(float(v), 4) for v in ax.get_ylim()) for ax in members
                }
                problems.append(
                    f"facet-ylim-mismatch ylabel '{lab}': ylims {sorted(ylims)}"
                )

    if "missing-axis-label" in active:
        checked = [
            ax
            for ax in geom_axes
            # 纯 img 轴是像素展示格——像素图不需要量纲标签
            if any(it[0] != "img" for it in series_map[ax])
            and ax.name == "rectilinear"
            and not _is_later_overlay(ax, all_axes)
            and _twin_host(ax, all_axes) is None
            and not _inside_other(ax, all_axes)
            and not _scoped("missing-axis-label", ax)
        ]
        supx = getattr(fig, "_supxlabel", None)
        supy = getattr(fig, "_supylabel", None)
        supx_on = supx is not None and bool(supx.get_text().strip())
        supy_on = supy is not None and bool(supy.get_text().strip())

        def _shared_label(ax, dim) -> bool:
            """该轴与带标 sibling 共享此轴（sharex/sharey 组内只需一处标签）。"""
            grp = ax.get_shared_x_axes() if dim == "x" else ax.get_shared_y_axes()
            return any(
                s is not ax and getattr(s, f"get_{dim}label")().strip()
                for s in grp.get_siblings(ax)
            )

        def _categorical_ticks(ax, dim) -> bool:
            """该轴刻度全是非数值类别名（bar/donut 语义已自描述）。"""
            ticks = ax.get_xticklabels() if dim == "x" else ax.get_yticklabels()
            labs = [t.get_text().strip() for t in ticks if t.get_text().strip()]
            if not labs:
                return False
            for s in labs:
                try:
                    float(s.replace("−", "-"))  # mpl 默认 unicode minus
                    return False  # 有数值刻度 → 不是纯类别轴
                except ValueError:
                    continue
            return True

        for ax in checked:
            if (
                not ax.get_xlabel().strip()
                and not supx_on
                and not _shared_label(ax, "x")
                and not _categorical_ticks(ax, "x")
            ):
                problems.append(f"missing-axis-label axes {ax_index[id(ax)]} xlabel")
            if (
                not ax.get_ylabel().strip()
                and not supy_on
                and not _shared_label(ax, "y")
                and not _categorical_ticks(ax, "y")
            ):
                problems.append(f"missing-axis-label axes {ax_index[id(ax)]} ylabel")

    if "twin-axis-unlabeled" in active:
        for ax in geom_axes:
            host = _twin_host(ax, all_axes)
            if host is None or _scoped("twin-axis-unlabeled", ax):
                continue
            # 共享的那一维由宿主标注；孪生自己的独立维度必须自带标签
            if _axes_joined(ax, host, "x"):
                dim = "y"
            elif _axes_joined(ax, host, "y"):
                dim = "x"
            else:  # secondary：退化位置贴哪条脊线就对应哪条轴
                pos = ax.get_position()
                dim = "y" if pos.width <= pos.height else "x"
            ticks = ax.get_yticklabels() if dim == "y" else ax.get_xticklabels()
            has_ticks = any(t.get_text().strip() and t.get_visible() for t in ticks)
            if not series_map[ax] and not has_ticks:
                continue  # 无系列无刻度——不存在需要解释的第二量纲
            label = ax.get_ylabel() if dim == "y" else ax.get_xlabel()
            if not label.strip():
                problems.append(
                    f"twin-axis-unlabeled axes {ax_index[id(ax)]}: "
                    f"twin of axes {ax_index[id(host)]} lacks {dim}label"
                )

    if "label-color-inconsistent" in active:
        lab2col: dict[str, dict[int, set]] = defaultdict(lambda: defaultdict(set))
        for ax in geom_axes:
            if _scoped("label-color-inconsistent", ax):
                continue
            for kind, label, art in series_map[ax]:
                if _real_label(label):
                    c = _series_color(kind, art)
                    if c is not None:  # img 等无系列色的 artist 不参与异色判定
                        lab2col[label][ax_index[id(ax)]].add(c)
        for label, per_ax in lab2col.items():
            colors = {c for s in per_ax.values() for c in s}
            if len(per_ax) > 1 and len(colors) > 1:
                problems.append(
                    f"label-color-inconsistent '{label}': {sorted(colors)} across axes "
                    f"{sorted(per_ax)}"
                )

    if "label-marker-inconsistent" in active:
        lab2mk: dict[str, dict[int, set]] = defaultdict(lambda: defaultdict(set))
        for ax in geom_axes:
            if _scoped("label-marker-inconsistent", ax):
                continue
            for kind, label, art in series_map[ax]:
                if not _real_label(label) or kind not in ("line", "coll"):
                    continue
                mk = art.get_marker() if kind == "line" else _marker_key(art)
                if mk in (None, "", "None", "none"):
                    continue
                lab2mk[label][ax_index[id(ax)]].add(mk)
        for label, per_ax in lab2mk.items():
            marks = {m for s in per_ax.values() for m in s}
            if len(per_ax) > 1 and len(marks) > 1:
                problems.append(
                    f"label-marker-inconsistent '{label}': {len(marks)} markers across axes "
                    f"{sorted(per_ax)}"
                )

    if "legend-overlaps-data" in active:
        for leg in legends:
            lquad = _bbox_to_quad(leg.get_window_extent(renderer))
            hit = None
            for ax in geom_axes:
                if _scoped("legend-overlaps-data", ax):
                    continue
                for kind, label, art in series_map[ax]:
                    if _quad_covers_artist(lquad, ax, kind, art, renderer):
                        hit = (ax_index[id(ax)], label or kind)
                        break
                if hit:
                    break
            if hit:
                problems.append(f"legend-overlaps-data axes {hit[0]} '{hit[1]}'")

    if "text-overlaps-data" in active:
        # ax.texts（含 annotate 与 spec note）与 add_artist 注入的 offsetbox
        # 文本框 vs 本轴数据墨水——collide/rb-text-collide 只管文本-文本，
        # legend-overlaps-data 只管图例框，note 压线压点是 audit-blindspot
        # 实测的整类盲区。图例条目文本按身份排除、刻度/轴标签是结构元素，
        # 都不查；patch 墨水按较小框 20% 相交面积计（rb-text-collide 惯例），
        # 线/点墨水是二元触点判定。
        for s, bb, kind, ax, t in text_boxes:
            if (
                kind != "text"
                or ax is None
                or ax not in geom_axes
                or _scoped("text-overlaps-data", ax)
                or id(t) in leg_text_ids
            ):
                continue
            q = _quad_of((s, bb, kind, ax, t))
            for kind2, label, art in series_map[ax]:
                if _quad_covers_artist(
                    q, ax, kind2, art, renderer, frac=0.20, seg_cross=True
                ):
                    problems.append(
                        f"text-overlaps-data axes {ax_index[id(ax)]} "
                        f"'{s}' x '{label or kind2}'"
                    )
                    break

    if "text-outside-figure" in active:
        x0, y0, x1, y1 = fig.get_window_extent(renderer).bounds
        for s, bb, *_ in text_boxes:
            if bb.x0 < x0 - 1 or bb.y0 < y0 - 1 or bb.x1 > x1 + 1 or bb.y1 > y1 + 1:
                problems.append(f"text-outside-figure '{s}'")

    if "text-too-small" in active:
        # 小版面配小字号是合法设计：阈值取 6pt 与基准字号 70% 的较小者，
        # 只抓相对语境也偏小的文字（half-slot 里 5.8pt 标签不误报）
        base = float(plt.rcParams.get("font.size", 10.0) or 10.0)
        floor = min(6.0, 0.7 * base)
        for s, _bb, _kind, ax, t in text_boxes:
            if ax is not None and _scoped("text-too-small", ax):
                continue
            sz = _text_size_pt(t)
            if sz is not None and sz < floor:
                problems.append(f"text-too-small '{s}' {sz:g}pt < {floor:g}pt")

    if "low-contrast" in active:
        fig_bg = fig.get_facecolor()
        # 中性文本压在「非 axes 底色」上的轴集：colormap 场（heat 格注记）
        # 与 pie/donut 扇区（autopct 字色按扇底选过）——底色近似对它们失效
        tinted_axes = {
            id(ax)
            for ax in fig.axes
            if any(_is_array_mapped(c) for c in list(ax.collections) + list(ax.images))
            or any(isinstance(p, Wedge) for p in ax.patches)
        }
        for s, bb, _kind, ax, t in text_boxes:
            if ax is not None and _scoped("low-contrast", ax):
                continue
            try:
                fg = to_rgba(t.get_color())
            except (ValueError, TypeError):
                continue
            # 背景近似：文字中心落在某 axes 内 → 该 axes 底色，否则 figure
            # 底色；压在有色 mark 上的情形近似不掉，阈值 2.0 只拦"几乎读不出"
            bg = fig_bg
            if ax is not None:
                if _fv_neutral(t) and id(ax) in tinted_axes:
                    # spec 标的中性字压在有色底上（heat 格内注记、donut 扇区
                    # pct）——axes 底色近似在该场景必然错误，字色由渲染器
                    # 按格底/扇底选过
                    continue
                ab = ax.get_window_extent(renderer)
                cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
                if ab.x0 <= cx <= ab.x1 and ab.y0 <= cy <= ab.y1:
                    bg = ax.get_facecolor()
            alpha = fg[3]
            eff = tuple(alpha * fg[i] + (1 - alpha) * bg[i] for i in range(3))
            l1, l2 = _rel_luminance(eff), _rel_luminance(bg[:3])
            ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
            if ratio < 2.0:
                problems.append(f"low-contrast '{s}' ratio {ratio:.2f}")

    if "legend-coverage" in active:
        legend_texts = {t.get_text() for leg in legends for t in leg.get_texts()}
        legend_colors = set()
        for leg in legends:
            for h in getattr(leg, "legend_handles", []):
                c = _artist_any_color(h)
                if c is not None:
                    legend_colors.add(c)
        for ax in geom_axes:
            if _scoped("legend-coverage", ax):
                continue
            # 散落 Rectangle（高亮框等注释）与无标的 colormap 集合（色条即图例）
            # 不算图例义务里的"系列"；容器柱算
            items = [
                it
                for it in series_map[ax]
                if _real_label(it[1])
                or (it[0] != "patch" and not _is_array_mapped(it[2]))
            ]
            i = ax_index[id(ax)]
            if len(items) < 2:
                # 单系列面板只剩「这条系列可识别」一项义务：label 进了某个
                # legend、非空 ylabel、就地文字、或颜色被某 legend 幽灵覆盖，
                # 四者取一即合法；四者皆无才报——死 label（有 label 却进不了
                # 任何 legend）与匿名系列分开报
                if len(items) == 1:
                    kind, lab, art = items[0]
                    direct = (
                        bool(ax.get_ylabel().strip())
                        or _sibling_ylabel(ax)
                        or any(t.get_text().strip() for t in ax.texts)
                        or _cat_identifiable(items, ax)
                    )
                    if _real_label(lab):
                        if lab not in legend_texts and not direct:
                            problems.append(
                                f"legend-coverage '{lab}' (axes {i}) in no legend"
                            )
                    else:
                        c = _series_color(kind, art)
                        if c is not None and c not in legend_colors and not direct:
                            problems.append(
                                f"legend-coverage unlabeled {kind} (axes {i}) "
                                f"color {c} not ghost-covered"
                            )
                continue
            labeled = [it for it in items if _real_label(it[1])]
            unlabeled = [it for it in items if not _real_label(it[1])]
            if ax.get_legend() is None and not legends:
                # 直接标在图上的（每系列一个 text）不算缺 legend——如 pie/donut；
                # box/violin 家族的类别刻度标签同理是就地身份标注
                n_texts = sum(1 for t in ax.texts if t.get_text().strip())
                if n_texts < len(items) and not _cat_identifiable(items, ax):
                    problems.append(
                        f"legend-coverage axes {i}: {len(items)} series reachable by no legend"
                    )
                continue
            for kind, label, art in labeled:
                if label not in legend_texts:
                    problems.append(
                        f"legend-coverage '{label}' (axes {i}) in no legend"
                    )
            for kind, label, art in unlabeled:
                c = _series_color(kind, art)
                if c is not None and c not in legend_colors:
                    problems.append(
                        f"legend-coverage unlabeled {kind} (axes {i}) color {c} "
                        "not ghost-covered"
                    )

    if "duplicate-legend-label" in active:
        fig_legends = set(getattr(fig, "legends", []))
        for leg in legends:
            host = getattr(leg, "axes", None)  # figure 级 legend 为 None
            where = (
                "figure"
                if leg in fig_legends or host is None
                else f"axes {ax_index.get(id(host), '?')}"
            )
            if leg is None:
                continue
            for txt, n in Counter(t.get_text() for t in leg.get_texts()).items():
                if txt.strip() and n > 1:
                    problems.append(f"duplicate-legend-label '{txt}' x{n} in {where}")

    if "tag-sequence" in active:
        ordered = sorted(
            (ax for ax in all_axes if not _is_colorbar(ax)),
            key=lambda a: (-round(a.get_position().y0, 2), a.get_position().x0),
        )
        matched = [
            m.group(1).lower()
            for ax in ordered
            # SecondaryAxis 等辅助轴没有 get_title
            if (
                m := _TAG_RE.match(
                    ax.get_title().strip() if hasattr(ax, "get_title") else ""
                )
            )
        ]
        # 只有落在 a..a+n-1 窗口内的字母才算面板 tag——窗口外的 "(x) ..."
        # 标题按行文惯例（如 "(r) reward curve"）处理，不参与序列检查
        window = {chr(ord("a") + i) for i in range(len(matched))}
        tags = [ch for ch in matched if ch in window]
        if len(tags) >= 2:
            expected = [chr(ord("a") + i) for i in range(len(tags))]
            if tags != expected:
                problems.append(
                    f"tag-sequence panels tagged {tags}, expected {expected}"
                )

    if "hue-budget" in active:
        fam_of = {v.lower(): k for k, v in HUES.items()}
        fam_of |= {v.lower(): k.removesuffix("_edge") for k, v in EDGE.items()}
        fams = set()
        for ax in geom_axes:
            if _scoped("hue-budget", ax):
                continue
            for kind, label, art in series_map[ax]:
                fam = fam_of.get(_series_color(kind, art) or "")
                if fam is not None and fam != "vgray":
                    fams.add(fam)
        if len(fams) > 4:
            problems.append(f"hue-budget {len(fams)} hue families: {sorted(fams)}")

    if "palette-overflow" in active:
        # 容量跟随当前主题的实际调色板长度（paper 9 / accent 5 / mono 5）——
        # accent/mono 下第 6 条系列色会回绕撞衫
        if isinstance(theme_name, ThemePreset):
            pal_label, pal_cap = theme_name.name, len(palette(theme_name.palette))
        else:
            active_theme = theme(theme_name or _ACTIVE_THEME)
            pal_label = active_theme.name
            pal_cap = len(palette(active_theme.palette))
        for ax in geom_axes:
            if _scoped("palette-overflow", ax):
                continue
            items = [
                it
                for it in series_map[ax]
                if _real_label(it[1])
                or (it[0] != "patch" and not _is_array_mapped(it[2]))
            ]
            i = ax_index[id(ax)]
            # 依附 overlay（band/pred 等无标 artist）不算独立系列：
            # 颜色已被同 axes 有标系列认领的无标 artist 不消耗调色板名额
            claimed = {_series_color(k, a) for k, lab, a in items if _real_label(lab)}
            counted = [
                it
                for it in items
                if _real_label(it[1]) or _series_color(it[0], it[2]) not in claimed
            ]
            if len(counted) > pal_cap:
                problems.append(
                    f"palette-overflow axes {i}: {len(counted)} series > "
                    f"{pal_label} palette {pal_cap}"
                )
            seen: dict[tuple, str] = {}
            for kind, label, art in items:
                if not _real_label(label):
                    continue
                key = (kind, _style_key(kind, art))
                if key in seen and seen[key] != label:
                    problems.append(
                        f"palette-overflow axes {i}: '{seen[key]}' vs '{label}' "
                        "indistinguishable style"
                    )
                    break
                seen[key] = label

    if "cvd-clash" in active:
        for ax in geom_axes:
            if _scoped("cvd-clash", ax):
                continue
            items = [
                it
                for it in series_map[ax]
                if _real_label(it[1])
                or (it[0] != "patch" and not _is_array_mapped(it[2]))
            ]
            # 与 palette-overflow 同口径：颜色被有标系列认领的无标 artist
            # 是依附 overlay，不参与"可区分性"比较；完全同色的对子由
            # palette-overflow 的 indistinguishable-style 负责，这里只查
            # 色盲模拟下近重合的不同色
            claimed = {_series_color(k, a) for k, lab, a in items if _real_label(lab)}
            reps: dict[str, str] = {}
            for kind, label, art in items:
                c = _series_color(kind, art)
                if c is None or (not _real_label(label) and c in claimed):
                    continue
                if c not in reps or _real_label(label):
                    reps[c] = label or kind
            clashes = []
            for c1, c2 in itertools.combinations(sorted(reps), 2):
                d, sim = _cvd_delta(c1, c2)
                if d < _CVD_DELTA:
                    clashes.append(
                        f"'{reps[c1]}' {c1} vs '{reps[c2]}' {c2} (Δ{d:.3f} {sim})"
                    )
            for msg in clashes[:3]:
                problems.append(f"cvd-clash axes {ax_index[id(ax)]}: {msg}")
            if len(clashes) > 3:
                problems.append(
                    f"cvd-clash axes {ax_index[id(ax)]}: "
                    f"+{len(clashes) - 3} more near-identical pairs"
                )

    # --- 渲染后回读层（rb-*）与 print-fit -----------------------------------
    # 声明坐标 ≠ 渲染坐标：这一层只用 draw 后 renderer 实测的 device-px 几何，
    # 全部 warn 级。见 references/charts/readback.md。

    if "print-fit" in active:
        # 交付物理宽取 tightbbox（产物按 tight 裁剪能裁到的最大画布）；比
        # canvas 更保守——图例外挂的 legend/文本也会让产物变宽、在槽位里被
        # 缩得更小。目标槽：print_slot 显式指定，否则图宽一旦超过 full 槽
        # 就注定按 full 缩印（更小的槽由调用方显式声明意图）。
        target = _slot_inches(print_slot)
        # get_tightbbox 返回值已是英寸（TransformedBbox 内建 1/dpi 变换）；
        # None 或零宽时退回 figwidth
        tbb = fig.get_tightbbox(renderer)
        w_in = (
            float(tbb.width)
            if tbb is not None and tbb.width > 0
            else float(fig.get_figwidth())
        )
        if target is None and w_in > SIZE_SLOTS["full"]:
            target = SIZE_SLOTS["full"]
        if target is not None and w_in > target * 1.02:
            scale = target / w_in
            small = []
            for s, _bb, _kind, ax, t in text_boxes:
                if ax is not None and _scoped("print-fit", ax):
                    continue
                sz = _text_size_pt(t)
                if sz is not None and sz * scale < PRINT_FIT_MIN_PT:
                    small.append((sz * scale, s))
            if small:
                eff, worst = min(small)
                problems.append(
                    f"print-fit {len(small)} text(s) <{PRINT_FIT_MIN_PT:g}pt "
                    f"after x{scale:.2f} downscale to {target:g}in slot "
                    f"(figure {w_in:g}in wide); worst '{worst}' {eff:g}pt"
                )

    if "rb-text-outside" in active:
        # text-outside-figure 的回读版：同一越界判定，但消息给出越界量的
        # 图宽归一化读数（dpi 无关）——先知道越了多少再决定是移动文字还是
        # 扩画布。
        fx0, fy0, fx1, fy1 = fig.get_window_extent(renderer).bounds
        fw = max(fx1 - fx0, 1.0)
        for s, bb, _kind, ax, _t in text_boxes:
            if ax is not None and _scoped("rb-text-outside", ax):
                continue
            over = max(fx0 - bb.x0, fy0 - bb.y0, bb.x1 - fx1, bb.y1 - fy1)
            if over > 1:
                problems.append(
                    f"rb-text-outside '{s}' {over:.0f}px beyond canvas "
                    f"({over / fw:.1%} of figure width)"
                )

    if "rb-text-collide" in active:
        # collide（error，任何相交即报）的宽量版：真实四边形相交面积 >
        # 较小框 20% 才报——legend 行、邻排 tick 天然贴合（边贴边不算交，
        # 相交才算），真压字才有面积占比。旋转文本按 _text_quad 重建的
        # 四边形判定，AABB 虚警已消除。
        pool = [
            tb
            for tb in text_boxes
            if tb[3] is None or not _scoped("rb-text-collide", tb[3])
        ]
        for tb1, tb2 in itertools.combinations(pool, 2):
            q1, q2 = _quad_of(tb1), _quad_of(tb2)
            ia = _quad_intersection_area(q1, q2)
            if ia <= 1e-9:
                continue  # 贴合不相交
            ratio = ia / min(abs(_quad_area(q1)), abs(_quad_area(q2)))
            if ratio > 0.20:
                problems.append(
                    f"rb-text-collide '{tb1[0]}' x '{tb2[0]}' "
                    f"{ratio:.0%} of the smaller box"
                )

    if "rb-label-diff" in active and declared is not None:
        # 声明 vs 渲染差集：声明了却没出现的标识报 missing（抓 spec ax2
        # 系列被图例静默丢弃那类），身份层渲染出未声明文本报 extra。
        dmap = {}
        for d in list(declared) + sorted(_artist_labels(fig)):
            n = _norm_label(d)
            if n:
                dmap.setdefault(n, str(d).strip())
        rendered_all, rendered_id = _rendered_texts(fig)
        rmap = {}
        for s in rendered_all:
            n = _norm_label(s)
            if n:
                rmap.setdefault(n, s)
        for n in sorted(set(dmap) - set(rmap)):
            problems.append(f"rb-label-diff missing '{dmap[n]}'")
        for n in sorted({_norm_label(s) for s in rendered_id} - {""} - set(dmap)):
            problems.append(f"rb-label-diff extra '{rmap.get(n, n)}'")

    if "shared-axis-misaligned" in active:
        # sharex 组同列成员的 x 边、sharey 组同行成员的 y 边在 device px 上
        # 必须对齐——aspect:'equal' 与竖排 sharex 共存时主面板横向内缩
        # （diag-calibration 实锤 ~30px/侧），共享轴错位却无任何规则出声。
        # 但跨行/跨列的共享组本来就物理错位：sharey 跨 2 行时 y 差=行距、
        # sharex:'row'/'all' 跨列时 x 差=列距（layout-facet 假阳性实锤）。
        # 因此先按共享方向自身的中心把组成员聚成带（sharex 按 x 中心聚
        # 列带、sharey 按 y 中心聚行带，带容差 4px），只在 ≥2 成员的带内
        # 比边缘 spread（容差 2px）；单成员带无从错位，跳过。
        # secondary/colorbar/被 ignore_axes 或 scoped 豁免的成员移出比较组。
        seen_groups: set[tuple] = set()
        geom_set = {
            ax
            for ax in axes
            if not _is_colorbar(ax) and not _is_secondary(ax, all_axes)
        }
        for ax in axes:
            if ax not in geom_set:
                continue
            for dim in ("x", "y"):
                grp = ax.get_shared_x_axes() if dim == "x" else ax.get_shared_y_axes()
                members = [
                    m
                    for m in grp.get_siblings(ax)
                    if m in geom_set and not _scoped("shared-axis-misaligned", m)
                ]
                if len(members) < 2:
                    continue
                key = (dim, frozenset(id(m) for m in members))
                if key in seen_groups:
                    continue
                seen_groups.add(key)
                bbs = {m: m.get_window_extent(renderer) for m in members}
                ctr = {
                    m: (getattr(bb, dim + "0") + getattr(bb, dim + "1")) / 2
                    for m, bb in bbs.items()
                }
                bands: list[list] = []
                for m in sorted(members, key=lambda m: ctr[m]):
                    if (
                        bands
                        and abs(
                            ctr[m] - sum(ctr[b] for b in bands[-1]) / len(bands[-1])
                        )
                        <= 4.0
                    ):
                        bands[-1].append(m)
                    else:
                        bands.append([m])
                for band in bands:
                    if len(band) < 2:
                        continue
                    lo = [getattr(bbs[m], dim + "0") for m in band]
                    hi = [getattr(bbs[m], dim + "1") for m in band]
                    d0, d1 = max(lo) - min(lo), max(hi) - min(hi)
                    if max(d0, d1) > 2.0:
                        idx = sorted(ax_index[id(m)] for m in band)
                        problems.append(
                            f"shared-axis-misaligned share{dim} axes {idx}: "
                            f"{dim}0 spread {d0:.0f}px, {dim}1 spread {d1:.0f}px"
                        )

    if "text-spills-axes" in active:
        # 锚点声明在轴内、字盒墨迹却显著越出轴框（diag-paired 实锤：表头
        # note 越右缘 26px，spec 侧 note-outside-axes 只看锚点）。
        # 锚点在轴外的不报——那归 note-outside-axes/clip 语义管；轴标题与
        # 轴标签锚点本就在轴外（kind=label），天然豁免；图例条目同例排除。
        # 无可视边框的轴不报：frameon=False（pie）、axis("off")（axison=False）
        # 或四 spine 全隐形（sankey/treemap 裸画布）——"越 spine"无从谈起；
        # 只画左/下 spine 的双 spine 风格仍按几何数据边界全向检查。
        # 容差 ~2pt 换算 device px；越过量报四个方向里的最大者。
        tol = 2.0 * fig.dpi / 72.0
        for s, bb, kind, ax, t in text_boxes:
            if (
                kind != "text"
                or ax is None
                or ax not in geom_axes
                or not ax.get_frame_on()
                or not ax.axison
                or not any(s.get_visible() for s in ax.spines.values())
                or _scoped("text-spills-axes", ax)
                or id(t) in leg_text_ids
            ):
                continue
            try:
                axp, ayp = t.get_transform().transform(t.get_unitless_position())
            except (TypeError, ValueError, AttributeError):
                continue
            ab = ax.get_window_extent(renderer)
            if not (ab.x0 - 1 <= axp <= ab.x1 + 1 and ab.y0 - 1 <= ayp <= ab.y1 + 1):
                continue
            sides = {
                "left": ab.x0 - bb.x0,
                "bottom": ab.y0 - bb.y0,
                "right": bb.x1 - ab.x1,
                "top": bb.y1 - ab.y1,
            }
            side, over = max(sides.items(), key=lambda kv: kv[1])
            if over > tol:
                problems.append(
                    f"text-spills-axes axes {ax_index[id(ax)]} '{s}' "
                    f"{over:.0f}px past {side} spine"
                )

    return problems


def problem_severity(problem: str) -> str:
    """audit() 条目的严重度：首 token 即规则名，查 RENDER_RULES；
    未识别按 'error'——无法归类的条目必须响亮失败，不静默降级。"""
    return RENDER_RULES.get(problem.split(" ", 1)[0], "error")


def format_audit_lines(problems) -> list[str]:
    """统一审计行：'ERR <rule>: <msg>' / 'warn <rule>: <msg>'。"""
    out = []
    for p in problems:
        rule, _, msg = p.partition(" ")
        head = "ERR" if problem_severity(p) == "error" else "warn"
        out.append(f"{head} {rule}: {msg}" if msg else f"{head} {rule}")
    return out


def overlay(fig: plt.Figure, path, *, dpi=None) -> Path:
    """渲染后几何覆盖层：把 axes 框/legend 框/每个文本的 window-extent
    画成调色板色细框，存成 PNG 诊断图。

    框色：画布 vink、axes vteal、legend vgold、文本 vcoral。坐标用
    IdentityTransform（device px）——与 rb-* 回读同一套测量，声明坐标
    不参与。按 tight 外扩落盘，画布外的越界框也看得见；写入前加、写完
    摘下，不改动传入的 figure。
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    rects = [(fig.get_window_extent(renderer), NEUTRALS["vink"], 1.2)]
    for ax in _all_axes(fig):
        rects.append((ax.get_window_extent(renderer), HUES["vteal"], 0.9))
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            rects.append((leg.get_window_extent(renderer), HUES["vgold"], 0.9))
    for leg in getattr(fig, "legends", []):
        if leg is not None and leg.get_visible():
            rects.append((leg.get_window_extent(renderer), HUES["vgold"], 0.9))
    for _s, bb, _kind, _ax, _t in _text_boxes(fig):
        rects.append((bb, HUES["vcoral"], 0.6))
    patches = []
    for bb, color, lw in rects:
        r = Rectangle(
            (bb.x0, bb.y0),
            bb.width,
            bb.height,
            transform=IdentityTransform(),
            fill=False,
            edgecolor=color,
            linewidth=lw,
            clip_on=False,
            zorder=100,
        )
        fig.add_artist(r)
        patches.append(r)
    try:
        fig.savefig(
            path,
            dpi=dpi or fig.dpi,
            bbox_inches="tight",
            pad_inches=0.02,
            facecolor=fig.get_facecolor(),
        )
    finally:
        for r in patches:
            r.remove()
    return Path(path)
