"""折线图最小模板：marker + reference line + audit。uv run --with matplotlib --with numpy python line_demo.py"""
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

X = np.array([1, 2, 3, 4, 5, 6])
SERIES = {
    "Focal": np.array([52, 57, 61, 66, 71, 75]),
    "Reference": np.array([49, 53, 56, 60, 63, 66]),
}
THEME = "paper"


def main() -> int:
    current = fv.apply_rc(THEME)
    colors = fv.series_colors(THEME, len(SERIES))
    marks = fv.series_markers(THEME, len(SERIES))
    styles = fv.line_styles(current.line_preset)
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for idx, (name, values) in enumerate(SERIES.items()):
        linestyle = styles["primary"] if idx == 0 else styles["secondary"]
        ax.plot(
            X,
            values,
            color=colors[idx],
            marker=marks[idx],
            linewidth=2.0 if idx == 0 else 1.7,
            linestyle=linestyle,
            label=name,
        )
    ax.axhline(
        58,
        color=fv.NEUTRALS["baseline"],
        linewidth=1.1,
        linestyle=styles["reference"],
        label="Baseline",
    )
    ax.set_xlabel("Step")
    ax.set_ylabel("Score")
    ax.set_title("Line chart with marker and reference preset")
    fv.apply_frame(ax, current.frame)
    fv.apply_grid(ax, current.grid)
    ax.legend(loc="upper left")
    fig.tight_layout()
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "line-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
