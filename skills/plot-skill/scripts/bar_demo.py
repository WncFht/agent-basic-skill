from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from style_presets import apply_frame, apply_grid, apply_rc, save_example, series_colors


LABELS = ["A", "B", "C", "D"]
SERIES = {
    "Baseline": [62, 66, 64, 69],
    "Method": [71, 74, 73, 78],
}
THEME = "tableau-accent"


def main() -> None:
    current = apply_rc(THEME)
    colors = series_colors(THEME, len(SERIES))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    x = np.arange(len(LABELS))
    width = 0.36
    for idx, (name, values) in enumerate(SERIES.items()):
        offset = (idx - 0.5) * width
        hatch = "//" if current.emphasis == "accent-first" and idx == 0 else None
        ax.bar(x + offset, values, width=width, label=name, color=colors[idx], edgecolor="white", hatch=hatch, alpha=0.92)
    ax.set_xticks(x, LABELS)
    ax.set_ylabel("Score")
    ax.set_title("Grouped bar with shared preset")
    apply_frame(ax, current.frame)
    apply_grid(ax, current.grid, axis="y")
    ax.legend(ncol=2, loc="upper left")
    fig.tight_layout()
    save_example(fig, "bar-demo.png")


if __name__ == "__main__":
    main()
