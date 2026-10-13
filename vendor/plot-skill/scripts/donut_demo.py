from __future__ import annotations

import matplotlib.pyplot as plt

from style_presets import NEUTRALS, apply_rc, save_example, series_colors


LABELS = ["Alpha", "Beta", "Gamma", "Delta"]
VALUES = [38, 27, 21, 14]
THEME = "tableau-paper"


def main() -> None:
    apply_rc(THEME)
    colors = series_colors(THEME, len(VALUES))
    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    wedges, _, autotexts = ax.pie(
        VALUES,
        labels=LABELS,
        colors=colors,
        startangle=110,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.1},
        autopct="%1.0f%%",
        pctdistance=0.78,
    )
    for text in autotexts:
        text.set_color(NEUTRALS["ink"])
    ax.set_title("Donut chart with direct percentages")
    ax.set_aspect("equal")
    fig.tight_layout()
    save_example(fig, "donut-demo.png")


if __name__ == "__main__":
    main()
