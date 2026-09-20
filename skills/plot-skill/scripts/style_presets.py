from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

TABLEAU_10 = {
    "blue": "#4E79A7",
    "orange": "#F28E2B",
    "red": "#E15759",
    "teal": "#76B7B2",
    "green": "#59A14F",
    "yellow": "#EDC948",
    "purple": "#B07AA1",
    "pink": "#FF9DA7",
    "brown": "#9C755F",
    "gray": "#BAB0AB",
}

EDGE_COLORS = {
    "blue": "#355C8A",
    "orange": "#C56F1F",
    "red": "#B74244",
    "teal": "#4E8B86",
    "green": "#3E7A36",
    "yellow": "#BD9E2F",
    "purple": "#855A79",
    "pink": "#D77986",
    "brown": "#6F5747",
    "gray": "#8B837E",
}

NEUTRALS = {
    "ink": "#2F2F2F",
    "axis": "#4B5563",
    "grid": "#D8DDE3",
    "baseline": "#6B7280",
    "muted": "#8D99AE",
    "soft_fill": "#F6F7F9",
    "page": "#FFFFFF",
}

PALETTES = {
    "tableau-paper": [
        TABLEAU_10["blue"],
        TABLEAU_10["orange"],
        TABLEAU_10["green"],
        TABLEAU_10["red"],
        TABLEAU_10["teal"],
    ],
    "tableau-accent": [
        TABLEAU_10["red"],
        TABLEAU_10["gray"],
        "#D6D3D1",
        "#E7E5E4",
        "#F5F5F4",
    ],
    "mono-paper": [
        "#374151",
        "#6B7280",
        "#9CA3AF",
        "#D1D5DB",
        "#E5E7EB",
    ],
}

MARKER_PRESETS = {
    "standard": ("o", "s", "^", "D", "P"),
    "paper-contrast": ("o", "^", "D", "X", "*"),
}

LINE_PRESETS = {
    "solid-primary": {"primary": "-", "secondary": "-", "reference": "--", "grid": "-"},
    "with-reference": {
        "primary": "-",
        "secondary": "-",
        "reference": "--",
        "grid": "--",
    },
    "with-dotted-grid": {
        "primary": "-",
        "secondary": "-",
        "reference": "--",
        "grid": ":",
    },
}


@dataclass(frozen=True)
class ThemePreset:
    name: str
    palette: str
    markers: str
    line_preset: str
    frame: str
    grid: str
    emphasis: str


THEMES = {
    "tableau-paper": ThemePreset(
        name="tableau-paper",
        palette="tableau-paper",
        markers="standard",
        line_preset="with-reference",
        frame="closed",
        grid="y-only",
        emphasis="balanced",
    ),
    "tableau-accent": ThemePreset(
        name="tableau-accent",
        palette="tableau-accent",
        markers="standard",
        line_preset="with-reference",
        frame="closed",
        grid="y-only",
        emphasis="accent-first",
    ),
    "mono-paper": ThemePreset(
        name="mono-paper",
        palette="mono-paper",
        markers="paper-contrast",
        line_preset="with-dotted-grid",
        frame="open",
        grid="full-dotted",
        emphasis="highlight-best",
    ),
}

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"


def theme(name: str = "tableau-paper") -> ThemePreset:
    return THEMES[name]


def palette(name: str) -> list[str]:
    return PALETTES[name]


def markers(name: str) -> tuple[str, ...]:
    return MARKER_PRESETS[name]


def line_styles(name: str) -> dict[str, str]:
    return LINE_PRESETS[name]


def apply_rc(theme_name: str = "tableau-paper") -> ThemePreset:
    current = theme(theme_name)
    plt.rcParams.update(
        {
            "figure.facecolor": NEUTRALS["page"],
            "axes.facecolor": NEUTRALS["page"],
            "savefig.facecolor": NEUTRALS["page"],
            "svg.fonttype": "none",
            "axes.edgecolor": NEUTRALS["axis"],
            "axes.linewidth": 0.9,
            "axes.labelcolor": NEUTRALS["ink"],
            "xtick.color": NEUTRALS["ink"],
            "ytick.color": NEUTRALS["ink"],
            "grid.color": NEUTRALS["grid"],
            "legend.frameon": False,
            "hatch.color": "white",
            "hatch.linewidth": 1.2,
        }
    )
    return current


def apply_frame(ax, frame: str) -> None:
    if frame == "open":
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(True)
        ax.spines["bottom"].set_visible(True)
        return
    if frame == "minimal":
        for spine in ax.spines.values():
            spine.set_visible(False)
        return
    for spine in ax.spines.values():
        spine.set_visible(True)


def apply_grid(ax, grid: str, axis: str = "y") -> None:
    if grid == "none":
        ax.grid(False)
        return
    if grid == "y-only":
        ax.grid(True, axis=axis, linewidth=0.8, linestyle="--", alpha=0.26)
        return
    if grid == "full-dotted":
        ax.grid(True, linewidth=0.7, linestyle=":", alpha=0.28)
        return
    ax.grid(False)


def series_colors(theme_name: str, n: int) -> list[str]:
    colors = palette(theme(theme_name).palette)
    if n <= len(colors):
        return colors[:n]
    return [colors[idx % len(colors)] for idx in range(n)]


def series_markers(theme_name: str, n: int) -> list[str]:
    mark = markers(theme(theme_name).markers)
    if n <= len(mark):
        return list(mark[:n])
    return [mark[idx % len(mark)] for idx in range(n)]


def save_example(fig: plt.Figure, filename: str) -> Path:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    out = EXAMPLES_DIR / filename
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out
