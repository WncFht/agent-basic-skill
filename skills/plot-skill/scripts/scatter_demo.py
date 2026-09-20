from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from style_presets import apply_frame, apply_grid, apply_rc, save_example, series_colors

THEME = "tableau-paper"


def main() -> None:
    current = apply_rc(THEME)
    colors = series_colors(THEME, 3)
    rng = np.random.default_rng(7)
    clusters = [
        ("Group A", rng.normal(loc=(-1.2, 1.0), scale=0.35, size=(40, 2)), colors[0]),
        ("Group B", rng.normal(loc=(0.8, 0.1), scale=0.32, size=(40, 2)), colors[1]),
        ("Group C", rng.normal(loc=(1.6, 1.4), scale=0.28, size=(34, 2)), colors[2]),
    ]
    fig, ax = plt.subplots(figsize=(6.8, 5.0))
    for name, points, color in clusters:
        ax.scatter(
            points[:, 0],
            points[:, 1],
            s=28,
            alpha=0.62,
            color=color,
            label=name,
            linewidths=0,
        )
    ax.set_xlabel("Component 1")
    ax.set_ylabel("Component 2")
    ax.set_title("Scatter chart with cluster coloring")
    apply_frame(ax, current.frame)
    apply_grid(ax, current.grid, axis="both")
    ax.legend(loc="upper left")
    fig.tight_layout()
    save_example(fig, "scatter-demo.png")


if __name__ == "__main__":
    main()
