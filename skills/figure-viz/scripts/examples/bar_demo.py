"""分组柱状图最小模板：paper/accent 主题 + audit。uv run --with matplotlib --with numpy python bar_demo.py"""
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

LABELS = ["A", "B", "C", "D"]
SERIES = {
    "Method": [71, 74, 73, 78],
    "Baseline": [62, 66, 64, 69],
}
THEME = "accent"


def main() -> int:
    current = fv.apply_rc(THEME)
    colors = fv.series_colors(THEME, len(SERIES))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    x = np.arange(len(LABELS))
    width = 0.36
    for idx, (name, values) in enumerate(SERIES.items()):
        offset = (idx - 0.5) * width
        hatch = "//" if current.emphasis == "accent-first" and idx == 0 else None
        ax.bar(
            x + offset,
            values,
            width=width,
            label=name,
            color=colors[idx],
            edgecolor="white",
            hatch=hatch,
            alpha=0.92,
        )
    ax.set_xticks(x, LABELS)
    ax.set_xlabel("group")
    ax.set_ylabel("Score")
    ax.set_title("Grouped bar with shared preset")
    fv.apply_frame(ax, current.frame)
    fv.apply_grid(ax, current.grid)
    ax.legend(ncol=2, loc="upper left")
    fig.tight_layout()
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "bar-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
