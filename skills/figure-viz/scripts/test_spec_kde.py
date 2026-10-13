#!/usr/bin/env python3
"""test_spec_kde.py — kde 系列与 scatter jitter 的隔离测试。

- kde：scott/silverman/显式带宽、bw_adjust、grid int/array、clip 截窗、
  fill 下层填充、by 扇出、audit 干净；对照独立重算的 gaussian KDE
- kde SpecError 面：缺 x、坏 bw/bw_adjust/grid/clip/fill、radar、
  退化带宽（常数列/单点组）、clip+array 滤空
- kde-min-points lint：触发 / audit_ignore 抑制 / 足量静默
- scatter jitter：窗界、对称/单侧、axis:'y'（含 cat_y 槽位）、确定性、
  seed 覆盖、errbar 锚定一致、radar/坏形态/非数值轴 SpecError
- _heat_cmap 薄壳（fv.ramp_cmap）行为不变冒烟

运行：uv run --with matplotlib --with numpy python scripts/test_spec_kde.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import matplotlib as mpl
from testkit import FAILS, check, warnings_of

mpl.use("Agg")

import fvspec
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection, PolyCollection
from matplotlib.container import ErrorbarContainer

SKILL_DIR = Path(__file__).resolve().parents[1]


def render(spec):
    return fvspec.render(spec, base_dir=SKILL_DIR / "scripts" / "examples")


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


def _rows(vals, g=None):
    rows = []
    for i, v in enumerate(vals):
        r = {"v": float(v)}
        if g is not None:
            r["g"] = g[i] if isinstance(g, (list, tuple)) else g
        rows.append(r)
    return rows


def _ref_kde(xs, grid, h):
    """独立重算的 gaussian KDE（与实现同一公式，验证接线而非重推导）。"""
    xs = np.asarray(xs, dtype=float)
    z = (np.asarray(grid, dtype=float)[:, None] - xs[None, :]) / h
    return np.exp(-0.5 * z * z).sum(axis=1) / (len(xs) * h * np.sqrt(2.0 * np.pi))


META = {"ledger": "l", "caption": "c"}


def kde_kinds():
    rng = np.random.default_rng(20260924)
    xs = np.concatenate([rng.normal(0.4, 0.06, 40), rng.normal(0.7, 0.05, 30)])

    # --- 基本渲染：audit 零问题零 lint ---
    spec = {
        "version": 1,
        "data": {"d": _rows(xs)},
        "xaxis": {"label": "score"},
        "yaxis": {"label": "density"},
        "series": [{"kind": "kde", "from": "d", "x": "v", "label": "kde"}],
        "meta": META,
        "legend": {"loc": "upper left"},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    probs, warns = audit_of(fig), warnings_of(fig)
    check("kde-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    ys_line = ax.lines[0].get_ydata()
    check("kde-nonneg", np.all(ys_line >= 0), f"min={ys_line.min()}")
    plt.close(fig)

    # --- scott 带宽：drawn 曲线 == 独立重算 ---
    n = xs.size
    h_scott = float(np.std(xs, ddof=1)) * n**-0.2
    fig = render(spec)
    ax = fig.get_axes()[0]
    gx, gy = ax.lines[0].get_xdata(), ax.lines[0].get_ydata()
    check(
        "kde-scott",
        np.allclose(gy, _ref_kde(xs, gx, h_scott), rtol=1e-10, atol=1e-12),
        f"max dev {np.abs(gy - _ref_kde(xs, gx, h_scott)).max():.3g}",
    )
    # 默认窗 = 数据两端各延 3·bw
    lo, hi = xs.min() - 3 * h_scott, xs.max() + 3 * h_scott
    check(
        "kde-default-window",
        abs(gx[0] - lo) < 1e-9 and abs(gx[-1] - hi) < 1e-9 and gx.size == 200,
        f"[{gx[0]},{gx[-1]}] vs [{lo},{hi}] n={gx.size}",
    )
    # 宽窗内积分 ≈ 1（scott 带宽尾巴泄漏很小）
    mass = np.trapezoid(gy, gx)
    check("kde-mass", abs(mass - 1.0) < 0.02, f"mass={mass}")
    plt.close(fig)

    # --- silverman / 显式 bw / bw_adjust ---
    h_silv = float(np.std(xs, ddof=1)) * (0.75 * n) ** -0.2
    spec["series"] = [{"kind": "kde", "from": "d", "x": "v", "bw": "silverman"}]
    fig = render(spec)
    gy = fig.get_axes()[0].lines[0].get_ydata()
    gx = fig.get_axes()[0].lines[0].get_xdata()
    check(
        "kde-silverman",
        np.allclose(gy, _ref_kde(xs, gx, h_silv), rtol=1e-10, atol=1e-12),
        f"max dev {np.abs(gy - _ref_kde(xs, gx, h_silv)).max():.3g}",
    )
    plt.close(fig)

    spec["series"] = [
        {"kind": "kde", "from": "d", "x": "v", "bw": 0.05, "bw_adjust": 1.5}
    ]
    fig = render(spec)
    gy = fig.get_axes()[0].lines[0].get_ydata()
    gx = fig.get_axes()[0].lines[0].get_xdata()
    check(
        "kde-bw-adjust",
        np.allclose(gy, _ref_kde(xs, gx, 0.075), rtol=1e-10, atol=1e-12),
        f"max dev {np.abs(gy - _ref_kde(xs, gx, 0.075)).max():.3g}",
    )
    plt.close(fig)

    # --- 单点 + 显式带宽：密度即 N(x0, h)（n=1 触发 min-points，抑制之）---
    spec = {
        "version": 1,
        "data": {"d": [{"v": 0.5}]},
        "series": [{"kind": "kde", "from": "d", "x": "v", "bw": 0.1}],
        "audit_ignore": ["kde-min-points"],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    gx, gy = ax.lines[0].get_xdata(), ax.lines[0].get_ydata()
    want = np.exp(-0.5 * ((gx - 0.5) / 0.1) ** 2) / (0.1 * np.sqrt(2 * np.pi))
    check(
        "kde-single-gauss",
        np.allclose(gy, want, rtol=1e-10, atol=1e-12),
        f"max dev {np.abs(gy - want).max():.3g}",
    )
    plt.close(fig)

    # --- grid 显式数组 与 clip 截窗 ---
    spec = {
        "version": 1,
        "data": {"d": _rows(xs)},
        "series": [{"kind": "kde", "from": "d", "x": "v", "grid": [0.1, 0.4, 0.9]}],
        "meta": META,
    }
    fig = render(spec)
    gx = fig.get_axes()[0].lines[0].get_xdata()
    check("kde-grid-array", list(gx) == [0.1, 0.4, 0.9], f"{list(gx)}")
    plt.close(fig)

    spec["series"][0]["clip"] = [0.0, 0.5]
    fig = render(spec)
    gx = fig.get_axes()[0].lines[0].get_xdata()
    check(
        "kde-grid-array-clip",
        list(gx) == [0.1, 0.4],
        f"{list(gx)}",
    )
    plt.close(fig)

    spec["series"][0] = {
        "kind": "kde",
        "from": "d",
        "x": "v",
        "clip": [0.0, 1.0],
        "grid": 101,
    }
    fig = render(spec)
    gx = fig.get_axes()[0].lines[0].get_xdata()
    check(
        "kde-clip-window",
        gx.size == 101 and gx[0] == 0.0 and gx[-1] == 1.0,
        f"n={gx.size} [{gx[0]},{gx[-1]}]",
    )
    plt.close(fig)

    # --- fill：下层半透明填充，fv-neutral 标记 ---
    spec["series"][0] = {"kind": "kde", "from": "d", "x": "v", "fill": 0.2}
    fig = render(spec)
    ax = fig.get_axes()[0]
    polys = [c for c in ax.collections if isinstance(c, PolyCollection)]
    check("kde-fill-drawn", len(polys) == 1, f"{len(polys)}")
    if polys:
        fc = polys[0].get_facecolor()
        check(
            "kde-fill-alpha",
            len(fc) and abs(fc[0][3] - 0.2) < 1e-6,
            f"alpha={fc[0][3] if len(fc) else None}",
        )
        check(
            "kde-fill-neutral",
            polys[0].get_gid() == "fv-neutral",
            f"gid={polys[0].get_gid()!r}",
        )
    plt.close(fig)

    # --- by 扇出：两组两线、组色不同、图例标签 ---
    rows = _rows(rng.normal(0.3, 0.05, 30), "a") + _rows(rng.normal(0.7, 0.05, 30), "b")
    spec = {
        "version": 1,
        "data": {"d": rows},
        "series": [
            {
                "kind": "kde",
                "from": "d",
                "x": "v",
                "by": "g",
                "label": {"a": "arm A", "b": "arm B"},
            }
        ],
        "meta": META,
        "xaxis": {"label": "score"},
        "yaxis": {"label": "density"},
        "legend": {"loc": "upper left"},
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    check("kde-by-lines", len(ax.lines) == 2, f"{len(ax.lines)}")
    check(
        "kde-by-colors",
        len({ln.get_color() for ln in ax.lines}) == 2,
        f"{[ln.get_color() for ln in ax.lines]}",
    )
    probs, warns = audit_of(fig), warnings_of(fig)
    check("kde-by-clean", not probs and not warns, f"{probs[:2]} {warns[:2]}")
    plt.close(fig)


def kde_errors():
    base = {
        "version": 1,
        "data": {"d": _rows(np.linspace(0, 1, 20))},
        "series": [{"kind": "kde", "from": "d", "x": "v"}],
    }
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        s.update(kw)
        return s

    expect_error("kde-missing-x", mod(series=[{"kind": "kde"}]), "missing required 'x'")
    expect_error(
        "kde-bw-name",
        mod(series=[{"kind": "kde", "x": "v", "bw": "nope"}]),
        "bw must be",
    )
    expect_error(
        "kde-bw-zero",
        mod(series=[{"kind": "kde", "x": "v", "bw": 0}]),
        "bw must be",
    )
    expect_error(
        "kde-bw-adjust",
        mod(series=[{"kind": "kde", "x": "v", "bw_adjust": -1}]),
        "bw_adjust must be",
    )
    expect_error(
        "kde-grid-small",
        mod(series=[{"kind": "kde", "x": "v", "grid": 1}]),
        "grid must be",
    )
    expect_error(
        "kde-grid-float",
        mod(series=[{"kind": "kde", "x": "v", "grid": 2.5}]),
        "grid must be",
    )
    expect_error(
        "kde-grid-order",
        mod(series=[{"kind": "kde", "x": "v", "grid": [0.5, 0.2, 0.9]}]),
        "grid array must be",
    )
    expect_error(
        "kde-clip-bad",
        mod(series=[{"kind": "kde", "x": "v", "clip": [1.0, 0.0]}]),
        "clip must be",
    )
    expect_error(
        "kde-fill-high",
        mod(series=[{"kind": "kde", "x": "v", "fill": 1.5}]),
        "fill must be",
    )
    expect_error(
        "kde-bad-key",
        mod(series=[{"kind": "kde", "x": "v", "y": "v"}]),
        "unknown keys",
    )
    expect_error(
        "kde-on-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            series=[{"kind": "kde", "x": "v"}],
        ),
        "not allowed in",
        "panel",
    )
    # 退化带宽：常数列与单点组
    expect_error(
        "kde-constant",
        mod(
            data={"d": [{"v": 0.5} for _ in range(20)]},
            audit_ignore=["kde-min-points"],
        ),
        "degenerate bandwidth",
    )
    expect_error(
        "kde-single-scott",
        mod(data={"d": [{"v": 0.5}]}, audit_ignore=["kde-min-points"]),
        "degenerate bandwidth",
    )
    # clip 把显式 grid 滤空
    expect_error(
        "kde-clip-empty",
        mod(series=[{"kind": "kde", "x": "v", "grid": [0.8, 0.9], "clip": [0.0, 0.5]}]),
        "leaves <2 grid points",
    )


def kde_lints():
    # kde-min-points：<10 点组触发；audit_ignore 抑制；>=10 不触发
    few = {
        "version": 1,
        "data": {"d": _rows(np.linspace(0, 1, 8))},
        "series": [{"kind": "kde", "x": "v"}],
    }
    expect_lint("kde-min-points", few, "kde-min-points")
    expect_lint(
        "kde-min-points-suppressed",
        dict(few, audit_ignore=["kde-min-points"]),
        "kde-min-points",
        present=False,
    )
    expect_lint(
        "kde-enough-quiet",
        dict(few, data={"d": _rows(np.linspace(0, 1, 30))}),
        "kde-min-points",
        present=False,
    )


def jitter_kinds():
    rng = np.random.default_rng(7)
    base_x = [1.0] * 40 + [2.0] * 40
    rows = [
        {"pos": x, "v": float(v), "g": "a" if x == 1.0 else "b"}
        for x, v in zip(base_x, rng.normal(0.5, 0.15, 80))
    ]

    # --- raincloud 场景：位置列 + {w, at} 单侧窗 ---
    spec = {
        "version": 1,
        "data": {"d": rows},
        "series": [
            {
                "kind": "scatter",
                "from": "d",
                "x": "pos",
                "y": "v",
                "by": "g",
                "jitter": {"w": 0.14, "at": 0.08},
                "s": 5,
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    scats = [c for c in ax.collections if isinstance(c, PathCollection)]
    check("jitter-groups", len(scats) == 2, f"{len(scats)}")
    off = np.concatenate([c.get_offsets()[:, 0] for c in scats])
    lo = np.where(off < 1.5, 1.0, 2.0)
    disp = off - lo
    check(
        "jitter-window",
        np.all(disp >= 0.08 - 1e-9) and np.all(disp <= 0.22 + 1e-9),
        f"range [{disp.min():.4f},{disp.max():.4f}]",
    )
    plt.close(fig)

    # --- 确定性：两次渲染位移逐点一致 ---
    fig2 = render(spec)
    scats2 = [
        c for c in fig2.get_axes()[0].collections if isinstance(c, PathCollection)
    ]
    off2 = np.concatenate([c.get_offsets()[:, 0] for c in scats2])
    check("jitter-deterministic", np.array_equal(off, off2), "offsets differ")
    plt.close(fig2)

    # --- 标量 jitter：±j/2 对称窗 ---
    spec["series"][0]["jitter"] = 0.2
    fig = render(spec)
    scats = [c for c in fig.get_axes()[0].collections if isinstance(c, PathCollection)]
    off = np.concatenate([c.get_offsets()[:, 0] for c in scats])
    disp = off - np.where(off < 1.5, 1.0, 2.0)
    check(
        "jitter-scalar-symmetric",
        np.all(np.abs(disp) <= 0.1 + 1e-9),
        f"max |d|={np.abs(disp).max():.4f}",
    )
    plt.close(fig)

    # --- axis:'y'：y 位移、x 原值 ---
    spec["series"][0]["jitter"] = {"w": 0.3, "at": -0.15, "axis": "y"}
    fig = render(spec)
    scats = [c for c in fig.get_axes()[0].collections if isinstance(c, PathCollection)]
    offs = np.concatenate([c.get_offsets() for c in scats])
    xs_seen = set(np.round(offs[:, 0], 9))
    check("jitter-y-xfixed", xs_seen <= {1.0, 2.0}, f"{sorted(xs_seen)}")
    plt.close(fig)

    # --- cat_y + axis:'y'：类别槽位附近的位移 ---
    rows_y = [{"x": float(i % 5), "cat": "a" if i < 12 else "b"} for i in range(24)]
    spec = {
        "version": 1,
        "data": {"d": rows_y},
        "series": [
            {
                "kind": "scatter",
                "x": "x",
                "y": "cat",
                "jitter": {"w": 0.2, "at": -0.1, "axis": "y"},
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    scats = [c for c in fig.get_axes()[0].collections if isinstance(c, PathCollection)]
    offs = np.concatenate([c.get_offsets() for c in scats])
    frac = offs[:, 1] - np.round(offs[:, 1])
    check(
        "jitter-cat-y",
        np.all(np.abs(frac) <= 0.1 + 1e-9) and set(np.round(offs[:, 1])) <= {0, 1},
        f"frac range [{frac.min():.3f},{frac.max():.3f}]",
    )
    plt.close(fig)

    # --- seed 覆盖：不同 seed 不同位移；同 seed 相同 ---
    spec = {
        "version": 1,
        "data": {"d": _rows(rng.normal(0, 1, 30))},
        "series": [
            {"kind": "scatter", "x": "v", "y": "v", "jitter": {"w": 0.1, "seed": 1}}
        ],
        "meta": META,
    }
    fig = render(spec)
    a = fig.get_axes()[0].collections[0].get_offsets()[:, 0]
    plt.close(fig)
    spec["series"][0]["jitter"]["seed"] = 2
    fig = render(spec)
    b = fig.get_axes()[0].collections[0].get_offsets()[:, 0]
    plt.close(fig)
    check("jitter-seed", not np.array_equal(a, b), "seeds produced equal offsets")

    # --- errbar 锚定：误差棒与点同受 jitter ---
    rows_e = [{"x": 1.0, "v": float(v), "e": 0.05} for v in rng.normal(0, 1, 15)]
    spec = {
        "version": 1,
        "data": {"d": rows_e},
        "series": [
            {
                "kind": "scatter",
                "x": "x",
                "y": "v",
                "yerr": "e",
                "jitter": {"w": 0.2, "at": 0.05},
            }
        ],
        "meta": META,
    }
    fig = render(spec)
    ax = fig.get_axes()[0]
    scat = next(c for c in ax.collections if isinstance(c, PathCollection))
    eb = next(c for c in ax.containers if isinstance(c, ErrorbarContainer))
    # fmt='none' 的误差棒只有 barcols LineCollection——每段竖线的 x 即锚点
    seg_x = sorted({round(p[0][0], 9) for p in eb.lines[2][0].get_segments()})
    check(
        "jitter-errbar-anchored",
        np.allclose(sorted(scat.get_offsets()[:, 0]), seg_x),
        f"scatter {sorted(scat.get_offsets()[:, 0])} vs errbar {seg_x}",
    )
    plt.close(fig)


def jitter_errors():
    base = {
        "version": 1,
        "data": {"d": [{"x": float(i), "v": float(i % 3)} for i in range(10)]},
        "series": [{"kind": "scatter", "x": "x", "y": "v"}],
    }
    import json as _j

    def mod(**kw):
        s = _j.loads(_j.dumps(base))
        s.update(kw)
        return s

    def jit(v):
        return mod(series=[{"kind": "scatter", "x": "x", "y": "v", "jitter": v}])

    expect_error("jitter-zero", jit(0), "must be > 0")
    expect_error("jitter-neg", jit(-0.2), "must be > 0")
    expect_error("jitter-str", jit("wide"), "must be a number or")
    expect_error("jitter-list", jit([0.1, 0.2]), "must be a number or")
    expect_error("jitter-w-missing", jit({"at": 0.1}), "'w' must be")
    expect_error("jitter-w-zero", jit({"w": 0}), "'w' must be")
    expect_error("jitter-at-str", jit({"w": 0.1, "at": "x"}), "'at' must be")
    expect_error("jitter-axis", jit({"w": 0.1, "axis": "z"}), "axis must be")
    expect_error("jitter-seed-neg", jit({"w": 0.1, "seed": -1}), "seed must be")
    expect_error("jitter-seed-float", jit({"w": 0.1, "seed": 1.5}), "seed must be")
    expect_error("jitter-bad-key", jit({"w": 0.1, "zz": 1}), "unknown keys")
    expect_error(
        "jitter-on-line",
        mod(series=[{"kind": "line", "x": "x", "y": "v", "jitter": 0.1}]),
        "unknown keys",
    )
    expect_error(
        "jitter-on-radar",
        mod(
            kind="radar",
            dims=["a", "b"],
            data={"d": [{"x": "a", "v": 1.0}, {"x": "b", "v": 2.0}]},
            series=[{"kind": "scatter", "x": "x", "y": "v", "jitter": 0.1}],
        ),
        "jitter unsupported on radar",
    )
    # 类别 x + jitter：无结构所有者时消费型类别表兜底建槽位——蜂群
    # 是合法图型，位移落在槽位 0 的 ±j/2 窗内（旧语义报 numeric）
    spec = mod(
        data={"d": [{"x": "c", "v": 1.0} for _ in range(5)]},
        series=[{"kind": "scatter", "x": "x", "y": "v", "jitter": 0.1}],
    )
    fig = render(spec)
    scats = [c for c in fig.get_axes()[0].collections if isinstance(c, PathCollection)]
    offs = np.concatenate([c.get_offsets() for c in scats])
    check(
        "jitter-cat-x",
        np.all(np.abs(offs[:, 0]) <= 0.05 + 1e-9),
        f"x range [{offs[:, 0].min():.3f},{offs[:, 0].max():.3f}]",
    )
    plt.close(fig)


def heat_cmap_shell():
    """_heat_cmap 薄壳化（fv.ramp_cmap）行为不变：seq/div/mpl 名照常，
    未知名 SpecError（prepare 先拦）。"""
    mat = [[1.0, 2.0], [3.0, 4.0]]
    for cmap in ("seq", "div", "viridis"):
        spec = {
            "version": 1,
            "series": [{"kind": "heat", "matrix": mat, "cmap": cmap}],
            "meta": META,
        }
        try:
            fig = render(spec)
        except Exception as e:
            check(f"heat-cmap-{cmap}", False, f"{type(e).__name__}: {e}")
            continue
        check(f"heat-cmap-{cmap}", True)
        plt.close(fig)
    expect_error(
        "heat-cmap-unknown",
        {"version": 1, "series": [{"kind": "heat", "matrix": mat, "cmap": "nope"}]},
        "unknown cmap",
    )


def main() -> int:
    kde_kinds()
    kde_errors()
    kde_lints()
    jitter_kinds()
    jitter_errors()
    heat_cmap_shell()
    print(f"--- spec_kde: {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
