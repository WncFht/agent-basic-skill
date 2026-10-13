#!/usr/bin/env python3
"""fvlocate.py — 定位 figure-viz 安装中可 import 的 ``assets/mpl`` 目录。

两种用法：

- CLI：``python3 fvlocate.py`` 打印解析出的目录（``--skill`` 改打印
  skill 根目录）。配合
  ``PYTHONPATH=$(python3 .../fvlocate.py) uv run --with matplotlib --with numpy python fig.py`` 使用。
- 内嵌：把本文件拷到项目的绘图脚本旁（仅依赖 stdlib），然后::

      import fvlocate
      fvlocate.ensure()       # sys.path <- assets/mpl
      import fvstyle as fv
      import fvspec

解析顺序（首个含 ``fvstyle.py`` 的目录胜出）：

1. ``$FIGURE_VIZ_MPL``                             — mpl 目录显式指定
2. ``$FIGURE_VIZ_HOME/assets/mpl``                 — skill 根显式指定
3. ``~/.agents/skills/figure-viz/assets/mpl``      — 已安装 skill
4. ``~/.agents/incubator/figure-viz/assets/mpl``   — 孵化中 checkout
5. ``~/.codex/skills/figure-viz/assets/mpl``       — codex 布局
6. 本文件自己的 ``../assets/mpl``                  — skill 内 vendored
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HOME = Path.home()


def _candidates() -> list[Path]:
    out = []
    env_mpl = os.environ.get("FIGURE_VIZ_MPL")
    if env_mpl:
        out.append(Path(env_mpl).expanduser())
    env_home = os.environ.get("FIGURE_VIZ_HOME")
    if env_home:
        out.append(Path(env_home).expanduser() / "assets" / "mpl")
    out += [
        _HOME / ".agents/skills/figure-viz/assets/mpl",
        _HOME / ".agents/incubator/figure-viz/assets/mpl",
        _HOME / ".codex/skills/figure-viz/assets/mpl",
        Path(__file__).resolve().parents[1] / "assets" / "mpl",
    ]
    return out


def mpl_dir() -> Path:
    """首个含 ``fvstyle.py`` 的候选目录；均无则抛 FileNotFoundError。"""
    for d in _candidates():
        if (d / "fvstyle.py").is_file():
            return d
    tried = "\n  ".join(str(d) for d in _candidates())
    raise FileNotFoundError(
        f"no figure-viz assets/mpl dir (with fvstyle.py) found; tried:\n  {tried}"
    )


def ensure() -> Path:
    """把解析出的目录插到 sys.path[0] 并返回它。"""
    d = mpl_dir()
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    return d


def main() -> int:
    try:
        d = mpl_dir()
    except FileNotFoundError as e:
        print(f"fvlocate: {e}", file=sys.stderr)
        return 1
    # assets/mpl 上两级即 skill 根目录
    print(d.parent.parent if "--skill" in sys.argv else d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
