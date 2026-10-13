#!/usr/bin/env python3
"""test_spec_image.py — image 系列（图版 / heat 叠图底图）的隔离测试。

- 三源互斥：path 字面文件（.npy/.png）、rgb 字面数组、file 列名
  （路径/数组格值混排、None → mist 占位 + missing-rows、整列缺失 SpecError）
- badge 角标：文本/fmt/角位锚定/半透明黑底/fv-neutral gid；缺字段行计
  missing-rows；path/rgb 形、坏 fmt/corner、缺 field → SpecError
- extent：get_extent 回读 + heat 叠图（半透明覆盖面下不报
  occluded-by-heat；不透明仍报）
- 图版放宽：全 image 面板网格 >8 格放行（≤64 格/边≤16），混入非
  image 面板或超限仍 SpecError
- 纯 image 面板默认：刻度收掉、grid none、frame closed；显式 ticks/grid
  钉回
- cmap 三件套：2-D 数组 seq/div+vcenter/cbar 落盘；3-D/通道数异常 → SpecError
- audit 侧 ax.images 算内容承担者：_series 收 img、有标 image 索
  legend-coverage、纯像素轴不索 missing-axis-label、badge 不吃
  text-overlaps-data、跨轴同 label 不炸 label-color-inconsistent

运行：uv run --with matplotlib --with numpy python scripts/test_spec_image.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np

SKILL_DIR = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="fvimg-"))


def render(spec, base_dir=None):
    return fvspec.render(spec, base_dir=TMP if base_dir is None else base_dir)


def audit_of(fig):
    return fvspec.audit_fig(fig)


def expect_error(name, spec, *substrings):
    try:
        render(spec)
    except fvspec.SpecError as e:
        msg = str(e)
        missing = [s for s in substrings if s not in msg]
        check(f"err:{name}", not missing, f"missing {missing} in: {msg}")
        return
    except Exception as e:
        check(f"err:{name}", False, f"wrong exc {type(e).__name__}: {e}")
        return
    check(f"err:{name}", False, "no SpecError raised")


def expect_lint(name, spec, lint, present=True):
    fig = render(spec)
    hits = [w for w in warnings_of(fig) if w.startswith(lint)]
    check(f"lint:{name}", bool(hits) == present, f"warnings={warnings_of(fig)}")
    plt.close(fig)


def rules_of(probs):
    return {p.split(" ", 1)[0] for p in probs}


def audit_rules(fig):
    probs = fv.audit(fig)
    plt.close(fig)
    return probs, rules_of(probs)


META = {"ledger": "l", "caption": "c"}

# --- fixtures：TMP 下 .npy 灰度/RGB 与 .png ------------------------------- #
GRAY = np.linspace(0.0, 1.0, 12).reshape(3, 4)
GRAY2 = np.flipud(GRAY)
RGB = np.zeros((4, 5, 3), dtype=np.uint8)
RGB[..., 0] = 200
RGB[..., 1] = np.arange(20).reshape(4, 5) * 10
np.save(TMP / "a.npy", GRAY)
np.save(TMP / "b.npy", GRAY2)
np.save(TMP / "rgb.npy", RGB)
plt.imsave(TMP / "c.png", RGB)


def image_forms():
    # --- path 字面形：.npy 2-D 落 seq cmap ---
    spec = {
        "version": 1,
        "series": [{"kind": "image", "path": "a.npy"}],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("path-npy", len(ax.images) == 1, f"{len(ax.images)}")
    if ax.images:
        check(
            "path-npy-arr",
            np.allclose(np.asarray(ax.images[0].get_array()), GRAY),
            f"{np.asarray(ax.images[0].get_array()).shape}",
        )
    plt.close(fig)

    # --- path 字面形：png（RGB）---
    spec["series"] = [{"kind": "image", "path": "c.png"}]
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "path-png",
        len(ax.images) == 1 and np.asarray(ax.images[0].get_array()).ndim == 3,
        f"{len(ax.images)}",
    )
    plt.close(fig)

    # --- rgb 字面形：2-D 与 3-D ---
    spec["series"] = [{"kind": "image", "rgb": GRAY.tolist()}]
    fig = render(spec)
    im = fig.get_axes()[0].images[0]
    check(
        "rgb-2d",
        np.allclose(np.asarray(im.get_array()), GRAY),
        f"{np.asarray(im.get_array()).shape}",
    )
    plt.close(fig)

    spec["series"] = [{"kind": "image", "rgb": RGB.tolist()}]
    fig = render(spec)
    im = fig.get_axes()[0].images[0]
    check(
        "rgb-3d",
        np.asarray(im.get_array()).ndim == 3,
        f"{np.asarray(im.get_array()).shape}",
    )
    plt.close(fig)

    # --- file 列名形：路径/数组格值混排 + None → mist 占位 ---
    rows = [
        {"src": "a.npy", "score": 0.94},
        {"src": GRAY2, "score": 0.51},
        {"src": None, "score": 0.12},
    ]
    spec = {
        "version": 1,
        "data": {"d": rows},
        "series": [
            {
                "kind": "image",
                "file": "src",
                "from": "d",
                "badge": {"field": "score"},
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("file-3img", len(ax.images) == 3, f"{len(ax.images)}")
    warns = warnings_of(fig)
    check(
        "file-mist-lint",
        any(w.startswith("missing-rows") for w in warns),
        f"{warns}",
    )
    if len(ax.images) == 3:
        mist = np.asarray(ax.images[2].get_array())
        check("file-mist-cell", mist.shape == (1, 1, 3), f"{mist.shape}")
        texts = [t.get_text() for t in ax.texts]
        check("file-badge-2", texts == ["0.94", "0.51"], f"{texts}")
    plt.close(fig)

    # --- file 形 0 行 → empty-series，无图 ---
    spec["series"][0]["where"] = {"score": {"$gt": 9}}
    expect_lint("image-empty", spec, "empty-series")


def image_badge():
    spec = {
        "version": 1,
        "data": {"d": [{"src": "a.npy", "score": 0.94}]},
        "series": [
            {
                "kind": "image",
                "file": "src",
                "from": "d",
                "badge": {"field": "score"},
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("badge-text", [t.get_text() for t in ax.texts] == ["0.94"])
    t = ax.texts[0]
    check("badge-gid", t.get_gid() == "fv-neutral", f"{t.get_gid()!r}")
    bb = t.get_bbox_patch()
    check(
        "badge-box",
        bb is not None and 0 < bb.get_facecolor()[3] < 1,
        f"{bb.get_facecolor() if bb is not None else None}",
    )
    # extent 缺省 → transAxes 左下角锚点
    check(
        "badge-anchor-bl",
        t.get_transform() is ax.transAxes
        and np.allclose(t.get_position(), (0.04, 0.05)),
        f"{t.get_position()}",
    )
    plt.close(fig)

    # --- corner/fmt 变体 ---
    spec["series"][0]["badge"] = {"field": "score", "fmt": "{v:.1%}", "corner": "tr"}
    fig = render(spec)
    t = fig.get_axes()[0].texts[0]
    check("badge-fmt", t.get_text() == "94.0%", f"{t.get_text()!r}")
    check(
        "badge-anchor-tr",
        np.allclose(t.get_position(), (0.96, 0.95)),
        f"{t.get_position()}",
    )
    plt.close(fig)

    # --- extent 形下 badge 用数据坐标 ---
    spec["series"][0]["extent"] = [0, 4, 3, 0]
    spec["series"][0]["badge"] = {"field": "score", "corner": "bl"}
    fig = render(spec)
    t = fig.get_axes()[0].texts[0]
    check(
        "badge-anchor-extent",
        t.get_transform() is not fig.get_axes()[0].transAxes
        and np.allclose(t.get_position(), (0.16, 2.85)),
        f"{t.get_position()}",
    )
    plt.close(fig)

    # --- 缺 badge 字段行 → 不画 + missing-rows ---
    spec["data"] = {"d": [{"src": "a.npy", "score": None}]}
    spec["series"][0].pop("extent")
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("badge-miss-draw", len(ax.texts) == 0, f"{len(ax.texts)}")
    check(
        "badge-miss-lint",
        any(w.startswith("missing-rows") for w in warnings_of(fig)),
        f"{warnings_of(fig)}",
    )
    plt.close(fig)


def image_extent_overlay():
    # --- extent 回读 ---
    spec = {
        "version": 1,
        "series": [{"kind": "image", "rgb": GRAY.tolist(), "extent": [0, 4, 3, 0]}],
        "meta": META,
    }
    fig = render(spec)
    im = fig.get_axes()[0].images[0]
    check(
        "extent-readback",
        tuple(im.get_extent()) == (0, 4, 3, 0),
        f"{im.get_extent()}",
    )
    plt.close(fig)

    # --- heat 叠图：image 垫底 + 半透明 heat → 不报 occluded-by-heat ---
    spec = {
        "version": 1,
        "series": [
            {"kind": "image", "rgb": GRAY.tolist(), "extent": [0, 4, 3, 0]},
            {
                "kind": "heat",
                "matrix": [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]],
                "alpha": 0.5,
                "cbar": False,
            },
        ],
        "meta": META,
    }
    fig = render(spec)
    warns = warnings_of(fig)
    check(
        "underlay-quiet",
        not any(w.startswith("occluded-by-heat") for w in warns),
        f"{warns}",
    )
    plt.close(fig)

    # --- 不透明 heat → 真盖死 → 报 ---
    spec["series"][1].pop("alpha")
    fig = render(spec)
    warns = warnings_of(fig)
    check(
        "underlay-opaque-warn",
        any(w.startswith("occluded-by-heat") for w in warns),
        f"{warns}",
    )
    plt.close(fig)


def image_cmap():
    # --- 2-D + seq 默认：autoscale，无 norm ---
    spec = {
        "version": 1,
        "series": [{"kind": "image", "rgb": GRAY.tolist(), "cbar": False}],
        "meta": META,
    }
    fig = render(spec)
    im = fig.get_axes()[0].images[0]
    check("cmap-seq", im.get_cmap() is not None, "no cmap")
    plt.close(fig)

    # --- div + vcenter → TwoSlopeNorm ---
    spec["series"][0].update({"cmap": "div", "vcenter": 0.5})
    fig = render(spec)
    im = fig.get_axes()[0].images[0]
    check(
        "cmap-div-norm",
        type(im.norm).__name__ == "TwoSlopeNorm" and abs(im.norm.vcenter - 0.5) < 1e-9,
        f"{type(im.norm).__name__}",
    )
    plt.close(fig)

    # --- cbar 默认 true → 多一个 colorbar 轴 ---
    spec["series"][0] = {"kind": "image", "rgb": GRAY.tolist()}
    fig = render(spec)
    check("cbar-default", len(fig.get_axes()) == 2, f"{len(fig.get_axes())}")
    plt.close(fig)


def _plate_panels(n):
    return {
        f"p{i}": {"series": [{"kind": "image", "rgb": RGB.tolist()}]} for i in range(n)
    }


def image_plate_layout():
    # --- 3x4=12 全 image 面板 → 图版放宽放行 ---
    spec = {
        "version": 1,
        "layout": {"shape": [3, 4], "tags": False},
        "panels": _plate_panels(12),
        "meta": META,
    }
    fig = render(spec)
    check("plate-3x4", len(fig.get_axes()) == 12, f"{len(fig.get_axes())}")
    plt.close(fig)

    # --- 5x5=25 全 image → 放行；9x9=81 与 1x17 → 超 cap ---
    spec["layout"]["shape"] = [5, 5]
    spec["panels"] = _plate_panels(25)
    fig = render(spec)
    check("plate-5x5", len(fig.get_axes()) == 25, f"{len(fig.get_axes())}")
    plt.close(fig)

    spec["layout"]["shape"] = [9, 9]
    spec["panels"] = _plate_panels(81)
    expect_error("plate-81", spec, "exceeds 64 cells")

    spec["layout"]["shape"] = [1, 17]
    spec["panels"] = _plate_panels(17)
    expect_error("plate-dim17", spec, "max dim 16")

    # --- 混入非 image 面板 → 普通 8 格 cap ---
    panels = _plate_panels(11)
    panels["chart"] = {
        "from": "d",
        "series": [{"kind": "line", "x": "x", "y": "y"}],
    }
    spec["layout"]["shape"] = [3, 4]
    spec["panels"] = panels
    spec["data"] = {"d": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}
    expect_error("plate-mixed", spec, "exceeds 8 cells", "image-plate")


def image_panel_defaults():
    spec = {
        "version": 1,
        "series": [{"kind": "image", "path": "rgb.npy"}],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "img-tickless",
        len(ax.get_xticks()) == 0 and len(ax.get_yticks()) == 0,
        f"{list(ax.get_xticks())} {list(ax.get_yticks())}",
    )
    check(
        "img-frame-closed",
        all(s.get_visible() for s in ax.spines.values()),
        f"{[s.get_visible() for s in ax.spines.values()]}",
    )
    gridlines = list(ax.get_xgridlines()) + list(ax.get_ygridlines())
    check(
        "img-grid-none",
        all(not gl.get_visible() for gl in gridlines),
        f"{[gl.get_visible() for gl in gridlines]}",
    )
    plt.close(fig)

    # --- 显式 ticks/grid/frame 钉回（网格线跟刻度走，y 格线要 y 刻度）---
    spec["xaxis"] = {"ticks": [1, 2, 3]}
    spec["yaxis"] = {"ticks": [0, 2, 4]}
    spec["grid"] = "y-only"
    spec["frame"] = "open"
    fig = render(spec)
    ax = fig.get_axes()[0]
    check(
        "img-ticks-pinned",
        list(ax.get_xticks()) == [1, 2, 3],
        f"{list(ax.get_xticks())}",
    )
    check(
        "img-grid-pinned",
        any(gl.get_visible() for gl in ax.get_ygridlines()),
        "no y gridline",
    )
    check(
        "img-frame-pinned",
        not ax.spines["top"].get_visible(),
        "top spine still on",
    )
    plt.close(fig)

    # --- image + note 混合 cell 仍享图版默认（中性 overlay 不算杂）---
    spec = {
        "version": 1,
        "series": [
            {"kind": "image", "path": "rgb.npy"},
            {"kind": "note", "at": [0.5, 0.5], "units": "axes", "text": "n"},
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("img-note-tickless", len(ax.get_xticks()) == 0)
    plt.close(fig)


def image_errors():
    base = {
        "version": 1,
        "data": {"d": [{"src": "a.npy", "score": 0.9}]},
        "series": [{"kind": "image", "file": "src", "from": "d"}],
        "meta": META,
    }
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        s.update(kw)
        return s

    def ser(ss):
        return mod(series=ss)

    expect_error("image-no-source", ser([{"kind": "image"}]), "missing source")
    expect_error(
        "image-two-sources",
        ser([{"kind": "image", "path": "a.npy", "rgb": [[1.0]]}]),
        "mutually",
    )
    expect_error(
        "image-of",
        ser(
            [
                {"kind": "line", "id": "l", "x": "score", "y": "score"},
                {"kind": "image", "file": "src", "of": "l"},
            ]
        ),
        "does not apply",
    )
    expect_error(
        "image-by",
        ser([{"kind": "image", "file": "src", "by": "score"}]),
        "does not apply",
    )
    expect_error(
        "image-color",
        ser([{"kind": "image", "file": "src", "color": "vteal"}]),
        "does not apply",
    )
    expect_error(
        "image-file-noncol",
        ser([{"kind": "image", "file": "ghost_col"}]),
        "not a data column",
    )
    expect_error(
        "image-file-type",
        ser([{"kind": "image", "file": 3}]),
        "must name a data column",
    )
    expect_error(
        "image-path-type",
        ser([{"kind": "image", "path": 3}]),
        "must be a file path string",
    )
    expect_error(
        "image-path-missing",
        ser([{"kind": "image", "path": "ghost.png"}]),
        "cannot read",
    )
    expect_error(
        "image-path-from",
        ser([{"kind": "image", "path": "a.npy", "from": "d"}]),
        "belongs to the 'file'",
    )
    expect_error(
        "image-path-where",
        ser([{"kind": "image", "path": "a.npy", "where": {"score": 1}}]),
        "belongs to the 'file'",
    )
    expect_error(
        "image-rgb-1d",
        ser([{"kind": "image", "rgb": [1.0, 2.0]}]),
        "2-D or 3-D",
    )
    expect_error(
        "image-rgb-channels",
        ser([{"kind": "image", "rgb": [[[0.1], [0.2]]]}]),
        "3 or 4 channels",
    )
    expect_error(
        "image-rgb-scalar",
        ser([{"kind": "image", "rgb": 5}]),
        "2-D or 3-D",
    )
    expect_error(
        "image-extent-shape",
        ser([{"kind": "image", "rgb": [[1.0]], "extent": [0, 1, 0]}]),
        "extent' must be",
    )
    expect_error(
        "image-extent-type",
        ser([{"kind": "image", "rgb": [[1.0]], "extent": "wide"}]),
        "extent' must be",
    )
    expect_error(
        "image-badge-path",
        ser(
            [
                {
                    "kind": "image",
                    "path": "a.npy",
                    "badge": {"field": "score"},
                }
            ]
        ),
        "needs data rows",
    )
    expect_error(
        "image-badge-nofield",
        ser([{"kind": "image", "file": "src", "badge": {"fmt": "{v}"}}]),
        "badge.field",
    )
    expect_error(
        "image-badge-corner",
        ser(
            [
                {
                    "kind": "image",
                    "file": "src",
                    "badge": {"field": "score", "corner": "cc"},
                }
            ]
        ),
        "badge.corner",
    )
    expect_error(
        "image-badge-fmt",
        ser(
            [
                {
                    "kind": "image",
                    "file": "src",
                    "badge": {"field": "score", "fmt": "{v:q%}"},
                }
            ]
        ),
        "badge.fmt",
    )
    expect_error(
        "image-cmap-rgb",
        ser([{"kind": "image", "rgb": [[[0.5, 0.2, 0.1]]], "cmap": "seq"}]),
        "needs a scalar",
    )
    expect_error(
        "image-cmap-on-rgbfile",
        mod(
            data={"d": [{"src": "rgb.npy"}]},
            series=[{"kind": "image", "file": "src", "from": "d", "cmap": "seq"}],
        ),
        "needs a scalar",
    )
    expect_error(
        "image-on-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            series=[{"kind": "image", "path": "a.npy"}],
        ),
        "not allowed in",
        "panel",
    )
    expect_error(
        "image-file-nodata",
        mod(data=None, series=[{"kind": "image", "file": "src"}]),
        "no 'from'",
    )
    expect_error(
        "image-bad-key",
        ser([{"kind": "image", "file": "src", "bogus": 1}]),
        "unknown keys",
    )


def image_lints():
    # badge.field 整列缺席 → unknown-field（且行级 missing-rows 兜底）
    spec = {
        "version": 1,
        "data": {"d": [{"src": "a.npy", "score": 0.9}]},
        "series": [
            {
                "kind": "image",
                "file": "src",
                "from": "d",
                "badge": {"field": "ghost"},
            }
        ],
        "meta": META,
    }
    expect_lint("badge-unknown-field", spec, "unknown-field")


def audit_side():
    """fvstyle 侧：ax.images 收进 _series 当内容承担者。"""
    fig, ax = plt.subplots(figsize=(3, 2))
    im = ax.imshow(GRAY, cmap="gray")
    ser = fv._series(ax)
    check(
        "audit-img-series",
        [k for k, _, _ in ser] == ["img"] and ser[0][2] is im,
        f"{ser}",
    )
    check("audit-img-color", fv._series_color("img", im) is None)
    pts = fv._series_points("img", im)
    check("audit-img-pts", pts.shape == (2, 2), f"{pts}")
    plt.close(fig)

    # 有标 image、无 label/legend/文本 → legend-coverage 索覆盖；
    # 纯 img 轴同时免 missing-axis-label
    fig, ax = plt.subplots(figsize=(3, 2))
    ax.imshow(GRAY, cmap="gray", label="cam")
    probs, rules = audit_rules(fig)
    check(
        "audit-img-coverage",
        "legend-coverage" in rules and "missing-axis-label" not in rules,
        f"{probs}",
    )

    # 角标式文本压图 → AxesImage 豁免，不报 text-overlaps-data
    fig, ax = plt.subplots(figsize=(3, 2))
    ax.imshow(GRAY, cmap="gray")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.text(
        0.5,
        0.5,
        "0.94",
        transform=ax.transAxes,
        bbox={"facecolor": "black", "alpha": 0.55, "pad": 1.4},
    )
    probs, rules = audit_rules(fig)
    check("audit-img-text-ok", "text-overlaps-data" not in rules, f"{probs}")

    # 跨轴同 label：img 无系列色 → label-color-inconsistent 不炸不报
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(6, 2))
    a0.imshow(GRAY, cmap="gray", label="cam")
    a0.set_xlabel("x")
    a0.set_ylabel("y")
    a1.plot([0, 1], [0, 1], color=fv.HUES["vteal"], label="cam")
    a1.set_xlabel("x")
    a1.set_ylabel("y")
    a0.legend()
    a1.legend()
    probs, rules = audit_rules(fig)
    check("audit-img-labcol", "label-color-inconsistent" not in rules, f"{probs}")


def spec_plate_audit():
    """2x2 file 形图版 + badge：spec 渲染与 audit 双干净。"""
    cells = [
        ("a.npy", 0.94),
        ("b.npy", 0.51),
        ("a.npy", 0.88),
        ("b.npy", 0.72),
    ]
    rows = [{"cell": i, "src": src, "score": s} for i, (src, s) in enumerate(cells)]
    panels = {
        f"p{i}": {
            "series": [
                {
                    "kind": "image",
                    "file": "src",
                    "from": "d",
                    "where": {"cell": i},
                    "badge": {"field": "score"},
                    "cbar": False,
                }
            ]
        }
        for i in range(4)
    }
    spec = {
        "version": 1,
        "data": {"d": rows},
        "layout": {"shape": [2, 2], "tags": False},
        "panels": panels,
        "meta": META,
    }
    fig = render(spec)
    warns = warnings_of(fig)
    check("plate-warn-clean", not warns, f"{warns}")
    axes = fig.get_axes()
    check(
        "plate-cells",
        len(axes) == 4 and all(len(ax.images) == 1 for ax in axes),
        f"{len(axes)} {[len(ax.images) for ax in axes]}",
    )
    check(
        "plate-badges",
        [t.get_text() for ax in axes for t in ax.texts]
        == ["0.94", "0.51", "0.88", "0.72"],
        f"{[t.get_text() for ax in axes for t in ax.texts]}",
    )
    probs = audit_of(fig)
    bad = {
        "missing-axis-label",
        "text-overlaps-data",
        "low-contrast",
        "legend-coverage",
    }
    check(
        "plate-audit-clean",
        not [p for p in probs if p.split(" ", 1)[0] in bad],
        f"{probs}",
    )
    plt.close(fig)


def main() -> int:
    image_forms()
    image_badge()
    image_extent_overlay()
    image_cmap()
    image_plate_layout()
    image_panel_defaults()
    image_errors()
    image_lints()
    audit_side()
    spec_plate_audit()
    print(f"--- spec_image: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
