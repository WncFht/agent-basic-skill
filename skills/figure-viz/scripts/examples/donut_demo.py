"""环形图最小模板：直接标百分比。uv run --with matplotlib --with numpy python donut_demo.py"""
# ruff: noqa: E402  —— fvlocate.ensure() 之后的 import 是刻意的路径门控

import sys
from pathlib import Path

# fvlocate.py 在本仓 scripts/；vendored 用法把它拷到脚本旁，此行可省
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fvlocate

fvlocate.ensure()  # assets/mpl 加入 sys.path

import fvstyle as fv
import matplotlib.pyplot as plt

SHARES = {"pretrain": 46, "sft": 22, "rlvr": 18, "eval": 14}
THEME = "paper"


def main() -> int:
    fv.apply_rc(THEME)
    colors = fv.series_colors(THEME, len(SHARES))
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.pie(
        SHARES.values(),
        labels=SHARES.keys(),
        colors=colors,
        autopct="%1.0f%%",
        pctdistance=0.78,
        startangle=100,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.2},
        textprops={"fontsize": 10},
    )
    ax.set_title("Compute share by stage")
    fig.tight_layout()
    errs = 0
    for p in fv.audit(fig):  # 统一审计行：'ERR <rule>: msg' / 'warn <rule>: msg'
        rule, _, msg = p.partition(" ")
        sev = "ERR" if fv.RENDER_RULES.get(rule, "error") == "error" else "warn"
        errs += sev == "ERR"
        print(f"{sev} {rule}: {msg}")
    fv.save(fig, "donut-demo.png")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
