from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    "bar_demo.py",
    "donut_demo.py",
    "line_demo.py",
    "radar_demo.py",
    "scatter_demo.py",
]


def main() -> None:
    for name in FILES:
        subprocess.run([sys.executable, str(ROOT / name)], check=True)
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
