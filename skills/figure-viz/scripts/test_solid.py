#!/usr/bin/env python3
"""test_solid.py — solid 伪 3D 方言回归：vizstyle 新样式编译 + 堆叠审计规则。

正例：ziso/ssolid/vshadow 三块堆叠 + AABB(inside=/overlap=) + vzwire 厚度线
      —— render_tex.py 必须 exit 0 且 check_audit 报 all invariants hold。
反例：同一图去掉堆叠重叠声明 —— 必须报 COLLIDE（exit 1），证明 AABB 相交
      断言真的咬合在审计上而不是摆设。

    python3 scripts/test_solid.py

xelatex 不在时 SKIP（exit 0）。只依赖 stdlib。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RENDER = SCRIPTS / "render_tex.py"

DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage[UTF8,fontset=fandol]{ctex}
\usepackage{amsmath,amssymb}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,calc,decorations.pathreplacing,fit}
\input{vizstyle}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}[ziso]
  \begin{pgfonlayer}{bg}
    \fill[vshadow] (0.4cm,0.18cm) ellipse (2.8 and 1.05);
  \end{pgfonlayer}
  \coordinate (N1) at (0,0);
  \pic[ssw=2.4,ssd=1.6,sst=0.7] at (N1)      {ssolid=vteal};
  \pic[ssw=1.8,ssd=1.2,sst=0.5] at (0,0,0.7) {ssolid=vblue};
  \pic[ssw=1.8,ssd=1.2,sst=0.5] at (0,0,1.2) {ssolid=vviolet};
  \node[vsym, text=vink, vaudit={inside=bk1,inside=bk2,inside=bk3}]
    at (0,-0.6,1.45) {top};
  \vzbbox{bk1}{($(N1)+(-2.4cm,0cm)$)}{($(N1)+(1.6cm,2.7cm)$)}%OVERLAP1%
  \vzbbox{bk2}{($(0,0,0.7)+(-1.8cm,0cm)$)}{($(0,0,0.7)+(1.2cm,2.0cm)$)}%INSIDE%
  \vzbbox{bk3}{($(0,0,1.2)+(-1.8cm,0cm)$)}{($(0,0,1.2)+(1.2cm,2.0cm)$)}%OVERLAP2%
  \coordinate (w1a) at (-2.85,1.2);
  \coordinate (w1b) at (-2.85,1.9);
  \draw[{Stealth[length=2.4mm]}-{Stealth[length=2.4mm]}, line width=0.5pt,
        draw=black!55] (w1a) -- (w1b) node[midway, left, vshape] {$c$};
  \vzwire{dimc}{w1a;w1b}{}
\end{tikzpicture}
\end{document}
"""

# %TAG% 占位：正例补声明、反例留空
CLEAN = (
    DOC.replace("%OVERLAP1%", "[overlap=bk3]")
    .replace("%INSIDE%", "[inside=bk1]")
    .replace("%OVERLAP2%", "[overlap=bk2]")
)
DIRTY = (
    DOC.replace("%OVERLAP1%", "")
    .replace("%INSIDE%", "[inside=bk1]")
    .replace("%OVERLAP2%", "")
)


def render(src_text: str, stem: str):
    """write tex, run render_tex.py, return (rc, stdout+stderr, audit_path)."""
    td = Path(tempfile.mkdtemp(prefix="fvsolid-"))
    src = td / f"{stem}.tex"
    src.write_text(src_text)
    proc = subprocess.run(
        [sys.executable, str(RENDER), str(src), "--outdir", str(td)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr, td / f"{stem}.audit"


def main() -> int:
    if shutil.which("xelatex") is None:
        print("SKIP solid-smoke (no xelatex)")
        return 0
    fails = 0

    rc, out, audit = render(CLEAN, "solid_clean")
    bad = []
    if rc != 0:
        bad.append(f"clean case exit {rc}")
    if "all invariants hold" not in out:
        bad.append("clean case missing 'all invariants hold'")
    if not audit.exists():
        bad.append("clean case produced no .audit")
    print(("PASS" if not bad else "FAIL"), "solid-clean", bad or "")
    if bad:
        print(out[-1500:])
    fails += bool(bad)

    rc, out, _ = render(DIRTY, "solid_dirty")
    bad = []
    if rc == 0:
        bad.append("dirty case unexpectedly exit 0")
    if "ERR COLLIDE" not in out:
        bad.append("dirty case missing ERR COLLIDE")
    print(("PASS" if not bad else "FAIL"), "solid-dirty", bad or "")
    if bad:
        print(out[-1500:])
    fails += bool(bad)

    print(f"--- 2 cases, {fails} failed ---")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
