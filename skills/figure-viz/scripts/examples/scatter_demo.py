"""散点图最小模板：类别色 + alpha + audit。uv run --with matplotlib --with numpy python scatter_demo.py"""
# ruff: noqa: E402  —— fvlocate.ensure() 之后的 import 是刻意的路径门控

import sys
from pathlib import Path

# fvlocate.py 在本仓 scripts/；vendored 用法把它拷到脚本旁，此行可省
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fvlocate

fvlocate.ensure()  # assets/mpl 加入 sys.path

import fvstyle as fv
import matplotlib.pyplot as plt
import numpy as np

THEME = "paper"


def main() -> int:
    rng = np.random.default_rng(7)
    current = fv.apply_rc(THEME)
    clusters = {
        "method-a": (0.4, 0.6),
        "method-b": (0.7, 0.35),
        "baseline": (0.55, 0.5),
    }
    colors = fv.series_colors(THEME, len(clusters))
    marks = fv.series_markers(THEME, len(clusters))
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    for idx, (name, (cx, cy)) in enumerate(clusters.items()):
        pts = rng.normal([cx, cy], 0.07, size=(40, 2))
        ax.scatter(
            pts[:, 0],
            pts[:, 1],
            s=26,
            color=colors[idx],
            marker=marks[idx],
            alpha=0.75,
            edgecolor="white",
            linewidth=0.4,
            label=name,
        )
    ax.set_xlabel("Throughput")
    ax.set_ylabel("Quality")
    ax.set_title("Scatter with cluster colors")
    fv.apply_frame(ax, current.frame)
    fv.apply_grid(ax, "full-dotted")
    ax.legend(loc="upper right")
    fig.tight_layout()
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "scatter-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
