"""矩形树图（treemap）配方示例：两级层级组成，面积 ∝ 份额。

spec 无 treemap kind：imperative 路径下空间填充布局交给 PyPI `squarify`
轮（`uv run --with squarify` 即装）；squarify 只铺一层，两级层级由调用
方预算坐标——组块 `padded_squarify`（自带 1 单位内缩留白）→ 顶条
HEADER_H 组头带 → 体块内递归 `squarify` 铺叶。包缺席时回落到文件内
`_squarify_local`（同算法兜底：test_all 的 demo 冒烟不带 --with
squarify，输出几何等价）。标签走 fit-degrade：renderer 实测文本框 →
文案×字号逐级降级 → 装不进放弃（小叶不标是 treemap 惯例，不留溢出
文字）；已装文本登记包围盒，候选与之相交即跳过——文本碰撞在装填期
就不存在，不靠事后审计兜底。

语义台账：叶矩形 = 一个预训练数据子域的 token 份额（%，和=100）；
组 = 一级数据域，组面积 = 子域份额之和。色相 = 一级域；组内 tint
阶梯（hue 向 paper 的明度 ramp）= 组内份额排名，不携带额外变量。
tint hex 经 `fv.register_colors` 注册进 palette_ext，OFFPALETTE 放行
（spec 侧 colors.ramp/registry 同一口径）。

几何台账：画布 0..100 × 0..62，aspect equal（数据单位=显示单位，
squarify 的纵横比在屏幕空间成立）。叶间分隔用 paper 色描边，不缩
叶面积；组头带满铺组宽放组名，组体不够高时组名退回组内居中试装。

依赖：matplotlib + squarify（布局轮；缺席走同算法兜底，输出等价）。
运行：uv run --with matplotlib --with squarify python treemap_demo.py
"""
# ruff: noqa: E402  —— fvlocate.ensure() 之后的 import 是刻意的路径门控

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fvlocate

fvlocate.ensure()  # assets/mpl 加入 sys.path

import fvstyle as fv
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex, to_rgb
from matplotlib.patches import Rectangle
from matplotlib.transforms import Bbox

try:
    import squarify
except ModuleNotFoundError:  # 布局轮缺席 → _layout 走 _squarify_local 兜底
    squarify = None

THEME = "paper"
W, H = 100.0, 62.0  # 画布数据坐标
HEADER_H = 3.6  # 组头带高；体块低于 MIN_HEADER_BODY 时组名退回组内居中
MIN_HEADER_BODY = 9.0
TINTS = (0.92, 0.70, 0.52, 0.40, 0.32)  # 组内明度 ramp：rank 越深越浅
MIN_FS = 6.4  # fit-degrade 字号下限（audit text-too-small 地板 6pt 上方）

# LLM 预训练混合（合成但真实感，Dolma 式域划分）：(组id, 组名, [(子域名, 份额%)])
MIXTURE = [
    ("web", "Web crawl", [("common-crawl", 34.0), ("refined-web", 13.0)]),
    ("code", "Code", [("github", 11.0), ("stack", 4.5), ("docs", 2.5)]),
    ("sci", "Scientific", [("arxiv", 7.0), ("pes2o", 4.0)]),
    ("books", "Books", [("books3", 6.0), ("gutenberg", 2.0)]),
    ("convo", "Conversational", [("reddit", 5.0), ("forums", 2.5)]),
    ("other", "Other", [("math", 3.5), ("wiki", 2.0), ("news", 1.5), ("misc", 1.5)]),
]

# treemap 惯例 vs 规则字面的结构性豁免，逐条声明、不静默：
#   missing-axis-label  无轴图型（ticks/spines 全关），无 xlabel/ylabel 可填
#   low-contrast        白字压深色 tile——规则按 axes 底色近似，看不到 tile
#   text-overlaps-data  叶内直标=就地身份标注（donut 同惯例），压的是自身 tile
SCOPED_IGNORE = [
    ("missing-axis-label", 0),
    ("low-contrast", 0),
    ("text-overlaps-data", 0),
]


def _worst(row, side):
    """squarify 行内最差纵横比（side = 行铺设所沿短边长）。"""
    s = sum(row)
    if s <= 0 or side <= 0:
        return float("inf")
    mx, mn = max(row), min(row)
    return max(side * side * mx / (s * s), s * s / (side * side * mn))


def _squarify_local(values, x, y, w, h, pad):
    """squarify 包的本地兜底（Bruls et al. 2000），签名同 _layout 语义。"""
    vals = [max(float(v), 0.0) for v in values]
    total = sum(vals)
    out = [[x, y, 0.0, 0.0] for _ in vals]
    if total > 0 and w > 0 and h > 0:
        areas = [v * w * h / total for v in vals]
        order = sorted(range(len(vals)), key=lambda i: -areas[i])
        cx, cy, cw, ch = x, y, w, h
        i = 0
        while i < len(order):
            side = min(cw, ch)
            row = [order[i]]
            i += 1
            while i < len(order):
                trial = [*row, order[i]]
                if _worst([areas[j] for j in trial], side) < _worst(
                    [areas[j] for j in row], side
                ):
                    row = trial
                    i += 1
                else:
                    break
            rowsum = sum(areas[j] for j in row)
            if cw >= ch:  # 沿短边铺一列
                rw = rowsum / ch if ch else 0.0
                ry = cy
                for j in row:
                    rh = areas[j] / rw if rw else 0.0
                    out[j] = [cx, ry, rw, rh]
                    ry += rh
                cx += rw
                cw -= rw
            else:  # 沿短边铺一行
                rh = rowsum / cw if cw else 0.0
                rx = cx
                for j in row:
                    rw = areas[j] / rh if rh else 0.0
                    out[j] = [rx, cy, rw, rh]
                    rx += rw
                cy += rh
                ch -= rh
    rects = []
    for rx, ry, rw, rh in out:  # pad 语义同 squarify.pad_rectangle：各边内缩 1
        if pad:
            if rw > 2:
                rx, rw = rx + 1, rw - 2
            if rh > 2:
                ry, rh = ry + 1, rh - 2
        rects.append((rx, ry, rw, rh))
    return rects


def _layout(values, x, y, w, h, pad=False):
    """一层 squarified 布局 → (x, y, w, h) 元组列，与 values 同序。

    squarify 包在场走包；缺席走 _squarify_local（同算法兜底）。
    """
    if squarify is None:
        return _squarify_local(values, x, y, w, h, pad)
    sizes = squarify.normalize_sizes(values, w, h)
    lay = squarify.padded_squarify if pad else squarify.squarify
    return [(r["x"], r["y"], r["dx"], r["dy"]) for r in lay(sizes, x, y, w, h)]


def _tint(hue, t):
    """hue 向 paper 混 (1-t) 的 tint hex——组内明度 ramp 的一个档位。"""
    return to_hex(tuple(t * c + (1 - t) for c in to_rgb(hue)))


def _lum(hexcolor):
    """sRGB 相对亮度（线性化）：<0.32 用白字，否则墨字。"""

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = to_rgb(hexcolor)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _fit_labels(ax, items):
    """fit-degrade 装填：每项 (x, y, w, h, [(文案, 字号)…], 字色)。

    候选按序试装：实测文本框超出宿主矩形（留边）或与已占位框相交即
    换下一候选，全部失败不标——装填期保证零文本碰撞。
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed = []
    for x, y, w, h, candidates, color in items:
        box = ax.transData.transform_bbox(Bbox([(x, y), (x + w, y + h)]))
        for text, fs in candidates:
            t = ax.text(
                x + w / 2,
                y + h / 2,
                text,
                ha="center",
                va="center",
                fontsize=fs,
                color=color,
                zorder=4,
                linespacing=1.15,
            )
            bb = t.get_window_extent(renderer=renderer)
            fits = bb.width <= box.width * 0.94 and bb.height <= box.height * 0.9
            if fits and not any(bb.overlaps(p) for p in placed):
                placed.append(bb)
                break
            t.remove()


def draw_treemap(ax, mixture, hues, ink, paper):
    """在 ax 上画两级 treemap；调用方负责 rc/注册色/审计/落盘。"""
    totals = [sum(v for _, v in leaves) for _, _, leaves in mixture]
    grects = _layout(totals, 0, 0, W, H, pad=True)  # 组块自带 1 单位组间留白
    items = []  # fit-degrade 候选：(x, y, w, h, [(文案, 字号)…], 字色)
    for (_gid, gname, leaves), (gx, gy, gw, gh), hue in zip(mixture, grects, hues):
        # 组边界与组头带是结构元素：fv-* gid 标中性，不进系列口径
        ax.add_patch(
            Rectangle(
                (gx, gy),
                gw,
                gh,
                facecolor="none",  # 不渲染也不留 C0 残值给 offpalette 读
                edgecolor=hue,
                linewidth=1.6,
                zorder=3,
                gid="fv-treemap-group",
            )
        )
        has_header = gh - HEADER_H >= MIN_HEADER_BODY
        bh = gh - HEADER_H if has_header else gh
        if has_header:
            ax.add_patch(
                Rectangle(
                    (gx, gy + bh),
                    gw,
                    HEADER_H,
                    facecolor=hue,
                    edgecolor="none",
                    zorder=2.5,
                    gid="fv-treemap-group",
                )
            )
            hcol = "#FFFFFF" if _lum(hue) < 0.32 else ink
            items.append(
                (
                    gx + 0.3,
                    gy + bh,
                    gw - 0.6,
                    HEADER_H,
                    [(gname, 8.2), (gname, 7.0), (gname, 6.4)],
                    hcol,
                )
            )
        else:  # 组体太矮放不下头带：组名退回组内居中试装
            items.append(
                (gx + 0.3, gy, gw - 0.6, gh, [(gname, 7.5), (gname, 6.6)], ink)
            )
        for k, ((lname, val), (lx, ly, lw, lh)) in enumerate(
            zip(leaves, _layout([v for _, v in leaves], gx, gy, gw, bh))
        ):
            tint = _tint(hue, TINTS[min(k, len(TINTS) - 1)])
            ax.add_patch(
                Rectangle(
                    (lx, ly),
                    lw,
                    lh,
                    facecolor=tint,
                    edgecolor=paper,  # 叶间分隔靠描边，不缩叶面积
                    linewidth=1.3,
                    zorder=2,
                )
            )
            tcol = "#FFFFFF" if _lum(tint) < 0.32 else ink
            fs = min(11.0, max(7.0, 3.2 + 0.9 * (lw * lh) ** 0.25))
            items.append(
                (
                    lx,
                    ly,
                    lw,
                    lh,
                    [
                        (f"{lname}\n{val:g}%", fs),
                        (lname, max(MIN_FS, fs - 0.7)),
                        (f"{val:g}%", max(MIN_FS, fs - 1.4)),
                    ],
                    tcol,
                )
            )
    _fit_labels(ax, items)


def main() -> int:
    fv.apply_rc(THEME)
    hues = fv.series_colors(THEME, len(MIXTURE))
    # tint ramp 的非板 hex 先注册进 palette_ext（registry 通道），
    # OFFPALETTE 放行——与审计对抗不如先声明。
    fv.register_colors(*(_tint(h, t) for h in hues for t in TINTS))
    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    ax.set_position([0.02, 0.09, 0.96, 0.89])  # 无轴图型：ax 吃满画布
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    draw_treemap(ax, MIXTURE, hues, fv.NEUTRALS["vink"], fv.NEUTRALS["paper"])
    fig.text(
        0.5,
        0.025,
        "area proportional to token share; hue = data domain",
        ha="center",
        fontsize=7.5,
        color=fv.HUES["vgray"],
    )
    # 结构豁免 SCOPED_IGNORE 见顶部声明；raw 计数只打 note 行（demo 冒烟
    # 契约：输出不得出现 'ERR '/'warn ' 起头的审计行），存活问题照打。
    raw = fv.audit(fig)
    suppressed = Counter(p.partition(" ")[0] for p in raw)
    if suppressed:
        print(f"note scoped-out by SCOPED_IGNORE: {dict(suppressed)}")
    problems = fv.audit(fig, scoped_ignore=SCOPED_IGNORE)
    errs = 0
    for p in problems:  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "treemap-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
