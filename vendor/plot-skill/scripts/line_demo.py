from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from style_presets import NEUTRALS, apply_frame, apply_grid, apply_rc, line_styles, save_example, series_colors, series_markers


X = np.array([1, 2, 3, 4, 5, 6])
SERIES = {
    "Focal": np.array([52, 57, 61, 66, 71, 75]),
    "Reference": np.array([49, 53, 56, 60, 63, 66]),
}
THEME = "tableau-paper"


def main() -> None:
    current = apply_rc(THEME)
    colors = series_colors(THEME, len(SERIES))
    marks = series_markers(THEME, len(SERIES))
    styles = line_styles(current.line_preset)
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for idx, (name, values) in enumerate(SERIES.items()):
        linestyle = styles["primary"] if idx == 0 else styles["secondary"]
        ax.plot(X, values, color=colors[idx], marker=marks[idx], linewidth=2.0 if idx == 0 else 1.7, linestyle=linestyle, label=name)
    ax.axhline(58, color=NEUTRALS["baseline"], linewidth=1.1, linestyle=styles["reference"], label="Baseline")
    ax.set_xlabel("Step")
    ax.set_ylabel("Score")
    ax.set_title("Line chart with marker and reference preset")
    apply_frame(ax, current.frame)
    apply_grid(ax, current.grid, axis="y")
    ax.legend(loc="upper left")
    fig.tight_layout()
    save_example(fig, "line-demo.png")


if __name__ == "__main__":
    main()
