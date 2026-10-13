"""雷达图最小模板：少量维度 profile 对比。uv run --with matplotlib --with numpy python radar_demo.py"""
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

DIMS = ["math", "code", "reason", "knowledge", "long-ctx"]
PROFILES = {
    "method": [0.82, 0.74, 0.79, 0.66, 0.71],
    "baseline": [0.70, 0.68, 0.62, 0.63, 0.58],
}
THEME = "paper"


def main() -> int:
    current = fv.apply_rc(THEME)
    colors = fv.series_colors(THEME, len(PROFILES))
    angles = np.linspace(0, 2 * np.pi, len(DIMS), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(5.6, 5.2), subplot_kw={"polar": True})
    for idx, (name, vals) in enumerate(PROFILES.items()):
        v = vals + vals[:1]
        ax.plot(angles, v, color=colors[idx], linewidth=1.8, label=name)
        ax.fill(angles, v, color=colors[idx], alpha=0.12)
    ax.set_xticks(angles[:-1], DIMS)
    ax.set_ylim(0, 1)
    ax.set_title("Capability profile")
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1))
    fv.apply_grid(ax, current.grid)
    fig.tight_layout()
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "radar-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
