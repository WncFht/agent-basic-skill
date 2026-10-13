from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from style_presets import apply_rc, save_example, series_colors

AXES = ["Math", "Code", "Vision", "Tool", "Planning", "Reasoning"]
SERIES = {
    "Method A": [0.74, 0.70, 0.59, 0.65, 0.72, 0.76],
    "Method B": [0.61, 0.66, 0.55, 0.57, 0.63, 0.68],
}
THEME = "tableau-paper"


def close(values):
    return np.concatenate([values, [values[0]]])


def main() -> None:
    apply_rc(THEME)
    colors = series_colors(THEME, len(SERIES))
    angles = np.linspace(0, 2 * np.pi, len(AXES), endpoint=False)
    fig, ax = plt.subplots(figsize=(6.6, 5.8), subplot_kw={"projection": "polar"})
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_xticks(angles, AXES)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8], [])
    for idx, (name, values) in enumerate(SERIES.items()):
        radii = np.array(values)
        ax.plot(
            close(angles),
            close(radii),
            color=colors[idx],
            linewidth=2.2 if idx == 0 else 1.6,
            label=name,
        )
        ax.fill(close(angles), close(radii), color=colors[idx], alpha=0.16)
    ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.28)
    ax.set_title("Radar chart for multi-axis profile")
    ax.legend(loc="upper right", bbox_to_anchor=(1.20, 1.12))
    fig.tight_layout()
    save_example(fig, "radar-demo.png")


if __name__ == "__main__":
    main()
