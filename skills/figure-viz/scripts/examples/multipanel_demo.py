"""1x4 多面板实验图模板：共享 numerics → 聚合表 → 一致配色 → 共享 legend + audit。

多臂对比实验的主力图型。流水线纪律：
  run_experiment() 只产聚合行（median/IQR/逐点值），make_figure(rows)
  不再接触原始实验状态——这正是 spec.json 的 data.rows 边界，本文件
  就是 spec 路径的 imperative 对照实现。
  一个 arm 一色到底（ARM_COLORS 注册表），跨面板不变；
  每个可见元素只在它该出现的面板出现，legend 全图共享一份；
  savefig 前必跑 fv.audit(fig)。

运行：uv run --with matplotlib --with numpy python multipanel_demo.py
"""
# ruff: noqa: E402  —— fvlocate.ensure() 之后的 import 是刻意的路径门控

import sys
from pathlib import Path

# fvlocate.py 在本仓 scripts/；vendored 用法把它拷到脚本旁，此行可省
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fvlocate

fvlocate.ensure()  # assets/mpl 加入 sys.path

import fvagg
import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import NullLocator

THEME = "paper"
FIGW_FULL = 5.5  # 整版宽 slot（spec size.slot:"full"）：按放置尺寸绘制

ARMS = ["frozen", "live-B", "live-A"]
ARM_PARAMS = {
    "frozen": {"rate": 0.006, "floor": 0.30, "spread": 0.10},
    "live-B": {"rate": 0.012, "floor": 0.21, "spread": 0.07},
    "live-A": {"rate": 0.009, "floor": 0.25, "spread": 0.08},
}
N_RUNS = 12
STEPS = np.linspace(0, 400, 41)
KS = [2, 4, 8, 16, 32, 64, 128, 256]


def paper_rc(base=7.6):
    """放置尺寸字号：图按最终排版尺寸绘制，字体不再二次缩放。

    spec 路径下由 rc:{font,base} 字段完成同一件事（serif/STIX 栈）。
    """
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [
                "Times New Roman",
                "Times",
                "STIX Two Text",
                "STIXGeneral",
                "DejaVu Serif",
            ],
            "mathtext.fontset": "stix",
            "font.size": base,
            "axes.titlesize": base,
            "axes.labelsize": base,
            "xtick.labelsize": base - 1.2,
            "ytick.labelsize": base - 1.2,
            "legend.fontsize": base - 1.2,
            "axes.linewidth": 0.6,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "lines.linewidth": 1.1,
            "lines.markersize": 3.2,
        }
    )


# ------------------------------------------------------------- 数值
def run_experiment():
    """合成实验 → 聚合行。make_figure 的唯一输入，等价于 spec 的 data.rows。

    聚合全部走 fvagg：原始记录（每 run 一行）进 agg_rows，派生列走
    add_field——脚本里不再手写 quantile/group-by。
    """
    rng = np.random.default_rng(23)

    raw_traj, finals = [], {}
    for arm, p in ARM_PARAMS.items():
        runs = []
        for _ in range(N_RUNS):
            start = 0.9 * (1 + 0.1 * rng.normal())
            floor = p["floor"] * (1 + 0.1 * rng.normal())
            rate = p["rate"] * (1 + 0.15 * rng.normal())
            kl = floor + (start - floor) * np.exp(-rate * STEPS)
            runs.append(
                np.maximum(kl * (1 + p["spread"] * rng.normal(size=STEPS.shape)), 1e-3)
            )
        arr = np.asarray(runs)
        finals[arm] = arr[:, -1]
        for run in runs:
            raw_traj += [
                {"arm": arm, "t": float(t), "kl": float(v)} for t, v in zip(STEPS, run)
            ]
    traj_rows = fvagg.agg_rows(
        raw_traj,
        keys=["arm", "t"],
        aggs={
            "med": ("kl", "median"),
            "q25": ("kl", "q25"),
            "q75": ("kl", "q75"),
        },
    )

    raw_grid, exact_of = [], {}
    for arm, p in ARM_PARAMS.items():
        exact_of[arm] = float(np.median(finals[arm]) * 0.82)  # dense-K 参考线
        for k in KS:
            leak = 0.55 * p["floor"] * (8.0 / k) ** 0.6
            for v in (p["floor"] + leak) * (1 + 0.08 * rng.normal(size=N_RUNS)):
                raw_grid.append({"arm": arm, "K": k, "v": float(v)})
    grid_rows = fvagg.add_field(
        fvagg.agg_rows(
            raw_grid,
            keys=["arm", "K"],
            aggs={
                "med": ("v", "median"),
                "q25": ("v", "q25"),
                "q75": ("v", "q75"),
            },
        ),
        "exact",
        lambda r: exact_of[r["arm"]],
    )

    anchor = 1.0 / np.arange(1, 401) ** 1.1  # arm 无关：只随 anchor 分布
    anchor /= anchor.sum()
    cov_rows = [{"K": k, "U": float(np.sum(anchor * (1 - anchor) ** k))} for k in KS]

    scan_rows = fvagg.add_field(
        [{"arm": arm, "klpT": float(v)} for arm, vals in finals.items() for v in vals],
        "klTp",
        lambda r: r["klpT"] * 0.6 * abs(1 + 0.2 * rng.normal()),
    )
    return traj_rows, grid_rows, cov_rows, scan_rows


def _rows(rows, arm):
    return [r for r in rows if r["arm"] == arm]


# ------------------------------------------------------------- 面板
def _panel_traj(ax, traj_rows, colors):
    for arm in ARMS:
        rs = _rows(traj_rows, arm)
        x = [r["t"] for r in rs]
        ax.plot(x, [r["med"] for r in rs], color=colors[arm], lw=1.2, label=arm)
        ax.fill_between(
            x,
            [r["q25"] for r in rs],
            [r["q75"] for r in rs],
            color=colors[arm],
            alpha=0.13,
            lw=0,
        )
    ax.axvspan(120, 160, color=fv.HUES["vteal"], alpha=0.10, lw=0)  # resync 窗口
    ax.set_ylim(bottom=0)
    ax.margins(y=0.15)  # 顶部留白，最高刻度不贴 title
    ax.set_xlabel("step")
    ax.set_ylabel(r"$\mathrm{KL}(p\Vert T)$")
    ax.set_title("(a) anchored KL decay")


def _categorical_log_x(ax):
    """离散网格值走 log 轴：刻度 = 全部网格，标签只留每两位防压字。"""
    ax.set_xscale("log")
    ax.set_xticks(KS)
    ax.set_xticklabels([str(k) if k in (2, 8, 32, 128) else "" for k in KS])
    ax.xaxis.set_minor_locator(NullLocator())


def _panel_kgrid(ax, grid_rows, colors):
    for arm in ARMS:
        rs = _rows(grid_rows, arm)
        x = [r["K"] for r in rs]
        ax.plot(x, [r["med"] for r in rs], "-o", color=colors[arm], ms=3, lw=1.0)
        ax.fill_between(
            x,
            [r["q25"] for r in rs],
            [r["q75"] for r in rs],
            color=colors[arm],
            alpha=0.13,
            lw=0,
        )
        ax.axhline(rs[0]["exact"], color=colors[arm], ls=":", lw=0.8)  # 同色参考线
    _categorical_log_x(ax)
    ax.set_yscale("log")
    ax.yaxis.set_minor_locator(NullLocator())  # minor:'off'，decade 标签不越界
    ax.set_xlabel("$K$ (tokens per sync)")
    ax.set_ylabel(r"final $\mathrm{KL}(p\Vert T)$")
    ax.set_title("(b) sampled budget")


def _panel_coverage(ax, cov_rows):
    x = [r["K"] for r in cov_rows]
    ax.plot(x, [r["U"] for r in cov_rows], color=fv.NEUTRALS["vink"], lw=1.2)
    ax.axhline(0.05, color=fv.NEUTRALS["baseline"], ls="--", lw=0.8)
    _categorical_log_x(ax)
    ax.set_yscale("log")
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xlabel("$K$")
    ax.set_ylabel("uncovered $U(K)$")
    ax.set_title("(c) anchor coverage")


def _panel_scatter(ax, scan_rows, colors):
    for arm in ARMS:
        rs = _rows(scan_rows, arm)
        ax.scatter(
            [r["klTp"] for r in rs],
            [r["klpT"] for r in rs],
            s=11,
            color=colors[arm],
            alpha=0.8,
            linewidths=0,
        )
    star = (0.045, 0.075)  # dense-K 最优点
    ax.scatter(*star, marker="*", s=48, color=fv.NEUTRALS["vink"], zorder=5)
    ax.annotate(
        "dense",
        xy=star,
        xytext=(4, 1),
        textcoords="offset points",
        fontsize=6.0,
        color=fv.NEUTRALS["vink"],
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.03, 0.6)  # 显式限界，log 轴 minor 标签不画出界
    ax.set_ylim(0.05, 0.8)
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xlabel(r"$\mathrm{KL}(T\Vert p^{*})$")
    ax.set_ylabel(r"$\mathrm{KL}(p^{*}\Vert T)$")
    ax.set_title("(d) coverage–precision")


def make_figure(traj_rows, grid_rows, cov_rows, scan_rows):
    colors = dict(zip(ARMS, fv.series_colors(THEME, len(ARMS))))  # 注册表：一臂一色
    fig, axes = plt.subplots(1, 4, figsize=(FIGW_FULL, 1.9))
    _panel_traj(axes[0], traj_rows, colors)
    _panel_kgrid(axes[1], grid_rows, colors)
    _panel_coverage(axes[2], cov_rows)
    _panel_scatter(axes[3], scan_rows, colors)
    for ax in axes:
        fv.apply_frame(ax, "closed")
        fv.apply_grid(ax, "y-only")
    fv.apply_grid(axes[3], "y-only", axis="both")

    handles = [
        Line2D([], [], color=colors[a], lw=1.2, marker="o", ms=3, label=a) for a in ARMS
    ] + [
        Line2D([], [], color=fv.HUES["vgray"], ls=":", lw=0.8, label="exact"),
        Patch(facecolor=fv.HUES["vgray"], alpha=0.25, lw=0, label="IQR"),
        # ghost：图上有颜色就必须有 legend 覆盖（legend-coverage 规则）
        Line2D(
            [], [], color=fv.NEUTRALS["vink"], marker="*", ms=6, lw=0, label="dense"
        ),
    ]
    fig.legend(
        handles=handles,
        ncol=6,
        loc="lower center",
        fontsize=6,
        columnspacing=0.8,
        handletextpad=0.4,
    )
    fig.tight_layout(rect=[0, 0.10, 1, 1])  # 给共享 legend 让位
    return fig


def main() -> int:
    fv.apply_rc(THEME)
    paper_rc()
    fig = make_figure(*run_experiment())
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "multipanel-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
