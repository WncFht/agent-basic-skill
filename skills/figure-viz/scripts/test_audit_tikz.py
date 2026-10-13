#!/usr/bin/env python3
"""test_audit_tikz.py — TikZ 轨审计自检：合成 .audit fixtures + xelatex 冒烟。

每条新检查造正/反 fixture 喂给 check_audit.py 子进程，断言退出码与规则名；
xelatex 在场时另做真实编译冒烟（vizaudit.tex 的 TeX 侧行为：vaudit 记录
自己节点、rotate 真 AABB、vzbbox 标签、vzwire 行、非 node 路径警告）。

另有三件套自检：check_coverage.py 静态覆盖扫描（纯 stdlib）、
check_readback_tex.py 渲染回读（xelatex + pdftotext）、
render_tex.py --overlay 调试覆盖图冒烟（xelatex）。

    python3 scripts/test_audit_tikz.py

任一 FAIL → 退出 1。只依赖 stdlib；xelatex 冒烟无 xelatex 时 SKIP。
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHECK = SCRIPTS / "check_audit.py"
COVERAGE = SCRIPTS / "check_coverage.py"
READBACK = SCRIPTS / "check_readback_tex.py"
RENDER_TEX = SCRIPTS / "render_tex.py"
VIZAUDIT = SCRIPTS.parent / "assets" / "tikz" / "vizaudit.tex"

sys.path.insert(0, str(SCRIPTS))
import check_readback_tex as rb  # noqa: E402


def run_audit(text, *flags):
    """写 fixture、跑 check_audit，返回 (rc, stdout)。"""
    with tempfile.TemporaryDirectory(prefix="fva-") as td:
        f = Path(td) / "fig.audit"
        f.write_text(text)
        proc = subprocess.run(
            [sys.executable, str(CHECK), str(f), *flags],
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout


def has(out, rule, severity=None):
    """输出中是否出现 `ERR rule:`/`warn rule:`（或任意级别规则）行。"""
    for line in out.splitlines():
        line = line.strip()
        for sev in (severity,) if severity else ("ERR", "warn"):
            if line.startswith(f"{sev} {rule}:"):
                return True
    return False


def warn_lines(out, rule):
    """检查器输出中的全部 `warn <rule>:` 行（已 strip）。"""
    return [
        ln.strip() for ln in out.splitlines() if ln.strip().startswith(f"warn {rule}:")
    ]


# --- 合成 .audit fixtures ----------------------------------------------
# 坐标写裸数（pt 后缀可选）；全文单位一律 pt。

# 列：名字、fixture、期望规则(ERR)、期望规则(warn)、禁止规则、旗标
CASES = [
    # -- 合并语义 ------------------------------------------------------
    (
        "merge-clean",
        "node A | 0 0 10 10 | class=x\nnode A | 0 0 10 10 | square\n",
        [],
        [],
        ["merge", "tag"],
        [],
    ),
    (
        "merge-tag-conflict",
        "node A | 0 0 10 10 | class=a\nnode A | 0 0 10 10 | class=b\n",
        ["tag"],
        [],
        [],
        [],
    ),
    (
        "merge-drift-warn",
        "node A | 0 0 10 10 | square\nnode A | 0 0 10 14 | class=x\n",  # 同名不同盒
        [],
        ["merge"],
        [],
        [],
    ),
    (
        "vaudit-append-union",  # \path \vaudit{A}{..} 模式：tag 累积
        "node A | 0 0 10 10 | class=c\n"
        "node A | 0 0 10 10 | inside=P\n"
        "node P | -5 -5 15 15 |\n"
        "node B | 50 0 60 10 | class=c\n",
        [],
        [],
        ["NEST"],
        [],
    ),
    # -- inside= 已校验 -----------------------------------------------------
    (
        "inside-ok",
        "node P | 0 0 100 100 |\nnode C | 10 10 20 20 | inside=P\n",
        [],
        [],
        [],
        [],
    ),
    (
        "inside-unaudited",
        "node C | 10 10 20 20 | inside=ZZ\n",
        ["inside"],
        [],
        [],
        [],
    ),
    (
        "inside-escaped",  # 声明了但几何为假 → ERR，不静默
        # （逃逸 ERR 已覆盖该对——不再叠 COLLIDE）
        "node P | 0 0 100 100 |\nnode C | 90 90 120 120 | inside=P\n",
        ["inside"],
        [],
        ["NEST", "COLLIDE"],
        [],
    ),
    (
        "inside-undeclared",
        "node P | 0 0 100 100 |\nnode C | 10 10 20 20 |\n",
        [],
        ["NEST"],
        [],
        [],
    ),
    (
        "multi-inside-ok",  # 多祖先：两个 parent 都得包含
        "node P1 | 0 0 100 100 |\n"
        "node P2 | 0 0 100 50 | inside=P1\n"
        "node C | 10 10 20 20 | inside=P1,inside=P2\n",
        [],
        [],
        [],
        [],
    ),
    (
        "multi-inside-fail",  # P2 不含 C → 即使 P1 含也 ERR
        # （C–P2 逃逸去重其 COLLIDE；一次逃逸一条 error）
        "node P1 | 0 0 100 100 |\n"
        "node P2 | 0 0 50 50 | inside=P1\n"
        "node C | 10 10 80 20 | inside=P1,inside=P2\n",
        ["inside"],
        [],
        ["COLLIDE"],
        [],
    ),
    (
        "multi-inside-rows",  # 经两条合并行（vaudit 重打 tag）同效
        "node P1 | 0 0 100 100 |\n"
        "node P2 | 0 0 100 50 | inside=P1\n"
        "node C | 10 10 20 20 | inside=P1\n"
        "node C | 10 10 20 20 | inside=P2\n",
        [],
        [],
        [],
        [],
    ),
    # -- \vzbbox [tags]（带 tags 的 region 行）-----------------------------
    (
        "vzbbox-tags-ok",  # region 作 inside 目标 + region 套 region
        "region outer | 0 0 200 200 |\n"
        "region lane | 10 10 100 60 | inside=outer\n"
        "node card | 20 20 40 40 | inside=lane,inside=outer\n",
        [],
        [],
        [],
        [],
    ),
    (
        "vzbbox-class",  # region 参与 class 相等
        "region b0 | 0 0 50 20 | class=band\n"
        "region b1 | 60 0 110 20 | class=band\n"
        "region b2 | 120 0 170 30 | class=band\n",
        ["class"],
        [],
        [],
        [],
    ),
    # -- \vzwire / WIRE-CROSS --------------------------------------------------
    (
        "wire-clean",  # connector A->B 只碰自己端点
        "node A | 0 0 10 10 |\n"
        "node B | 60 0 70 10 |\n"
        "wire w | 10 5 60 5 | endpoint=A,B\n",
        [],
        [],
        ["CROWD"],
        ["--gap", "30"],  # A-B 间距 50 > 任何合理 gap
    ),
    (
        "wire-cross",  # 中段进入未声明的 box
        "node A | 0 0 10 10 |\n"
        "node M | 20 0 30 10 |\n"
        "node B | 60 0 70 10 |\n"
        "wire w | 10 5 60 5 | endpoint=A,B\n",
        ["WIRE-CROSS"],
        [],
        [],
        ["--gap", "1"],
    ),
    (
        "wire-via-exempt",  # via= 使穿越合法
        "node A | 0 0 10 10 |\n"
        "node M | 20 0 30 10 |\n"
        "node B | 60 0 70 10 |\n"
        "wire w | 10 5 60 5 | endpoint=A,B via=M\n",
        [],
        [],
        [],
        ["--gap", "1"],
    ),
    (
        "wire-waypoint-inside",  # 途经点扎进外部 box
        "node A | 0 0 10 10 |\n"
        "node M | 20 0 40 20 |\n"
        "node B | 60 0 70 10 |\n"
        "wire w | 10 5 30 10 60 5 | endpoint=A,B\n",
        ["WIRE-CROSS"],
        [],
        [],
        ["--gap", "1"],
    ),
    (
        "wire-endpoint-unaudited",  # 端点拼错：warn + B 不豁免 → cross
        "node A | 0 0 10 10 |\n"
        "node B | 60 0 70 10 |\n"
        "wire w | 10 5 65 5 | endpoint=A,nope\n",
        ["WIRE-CROSS"],
        ["wire"],
        [],
        ["--gap", "1"],
    ),
    (
        "wire-graze-ok",  # 贴盒边的段（弦深 ~0）不算 cross
        "node A | 0 0 10 10 |\n"
        "node M | 20 0 30 5 |\n"
        "node B | 60 0 70 10 |\n"
        "wire w | 10 5 60 5 | endpoint=A,B\n",  # 沿 M 顶边 y=5 走
        [],
        [],
        [],
        ["--gap", "1"],
    ),
    # -- CROWD / adjacent= -----------------------------------------------------
    (
        "crowd-warn",  # 未声明邻居相距 5pt
        "node A | 0 0 10 10 |\nnode B | 15 0 25 10 |\n",
        [],
        ["CROWD"],
        [],
        [],
    ),
    (
        "crowd-gap-flag",  # 同一对，--gap 收紧到间距之下
        "node A | 0 0 10 10 |\nnode B | 15 0 25 10 |\n",
        [],
        [],
        ["CROWD"],
        ["--gap", "3"],
    ),
    (
        "crowd-adjacent-ok",  # 声明相邻抑制 CROWD
        "node A | 0 0 10 10 | adjacent=B\nnode B | 15 0 25 10 |\n",
        [],
        [],
        [],
        [],
    ),
    (
        "crowd-adjacent-reverse",  # 任一侧声明都抑制
        "node A | 0 0 10 10 |\nnode B | 15 0 25 10 | adjacent=A\n",
        [],
        [],
        [],
        [],
    ),
    (
        "adjacent-unaudited",
        "node A | 0 0 10 10 | adjacent=ghost\n",
        [],
        ["adjacent"],
        [],
        [],
    ),
    # -- overlap= 声明的部分重叠对 ------------------------------
    (
        "overlap-declared-ok",  # 声明对豁免 COLLIDE
        "node A | 0 0 10 10 | overlap=B\nnode B | 5 0 15 10 |\n",
        [],
        [],
        ["COLLIDE", "overlap", "CROWD", "NEST"],
        [],
    ),
    (
        "overlap-declared-reverse",  # 对称——任一侧可声明
        "node A | 0 0 10 10 |\nnode B | 5 0 15 10 | overlap=A\n",
        [],
        [],
        ["COLLIDE", "overlap"],
        [],
    ),
    (
        "overlap-unrealized",  # 声明了但已漂移分开 → 死声明
        "node A | 0 0 10 10 | overlap=B\nnode B | 12 0 22 10 |\n",
        [],
        ["overlap"],
        ["COLLIDE", "CROWD"],
        [],
    ),
    (
        "overlap-unaudited",
        "node A | 0 0 10 10 | overlap=ghost\n",
        [],
        ["overlap"],
        [],
        [],
    ),
    (
        "overlap-contained-nest",  # 声明 overlap 实为包含
        # → NEST 仍报：inside= 才是对的声明，不是 overlap=
        "node P | 0 0 30 30 |\nnode C | 5 5 10 10 | overlap=P\n",
        [],
        ["NEST"],
        ["overlap", "COLLIDE"],
        [],
    ),
    (
        "crowd-touch-undeclared",  # 未声明的贴边对
        "node A | 0 0 10 10 |\nnode B | 10 0 20 10 |\n",
        [],
        ["CROWD"],
        [],
        [],
    ),
    (
        "crowd-inside-related",  # 声明的包含是关系，不是 crowd
        "node P | 0 0 30 30 |\nnode C | 5 5 10 10 | inside=P\n",
        [],
        [],
        ["CROWD", "NEST"],
        [],
    ),
    (
        "inside-escape-other-collide",  # 去重按对算：无关的
        # 重叠对仍吃自己的 COLLIDE
        "node P | 0 0 100 100 |\n"
        "node Q | 105 -30 120 -10 |\n"
        "node C | 90 -20 110 10 | inside=P\n",
        ["inside", "COLLIDE"],
        [],
        [],
        [],
    ),
    # -- class: 展开目标（仅 adjacent=/overlap=）--------------------
    (
        "adjacent-class-ok",  # class:cell 展开为除己外全员——
        # 每格一条声明覆盖所有网格对，无 CROWD
        "node c1 | 0 0 10 10 | class=cell,adjacent=class:cell\n"
        "node c2 | 10 0 20 10 | class=cell,adjacent=class:cell\n"
        "node c3 | 20 0 30 10 | class=cell,adjacent=class:cell\n",
        [],
        [],
        ["CROWD", "adjacent"],
        [],
    ),
    (
        "adjacent-class-undeclared-pair",  # 只有 c1 声明：c2–c3 仍 crowd
        "node c1 | 0 0 10 10 | class=cell,adjacent=class:cell\n"
        "node c2 | 10 0 20 10 | class=cell\n"
        "node c3 | 20 0 30 10 | class=cell\n",
        [],
        ["CROWD"],
        ["adjacent"],
        [],
    ),
    (
        "adjacent-class-empty",  # class 解析为零 box → 悬空 warn
        "node c1 | 0 0 10 10 | adjacent=class:ghost\n",
        [],
        ["adjacent"],
        [],
        [],
    ),
    (
        "adjacent-class-self-only",  # 排除自身：独苗成员仍 warn
        "node c1 | 0 0 10 10 | class=lone,adjacent=class:lone\n",
        [],
        ["adjacent"],
        [],
        [],
    ),
    (
        "overlap-class-ok",  # overlap=class:sheet 豁免每个成员对；
        # s 真叠 a (5x15) 与 b (15x5) → 不报死声明 warn
        # （class= 成员须同 w×h——这里都 15x15）
        "node s | 0 0 20 20 | overlap=class:sheet\n"
        "node a | 15 -10 30 5 | class=sheet\n"
        "node b | 5 15 20 30 | class=sheet\n",
        [],
        [],
        ["COLLIDE", "overlap", "CROWD", "NEST"],
        [],
    ),
    (
        "overlap-class-stale",  # s 不叠任何 class 成员 → warn，但
        # 已声明对仍是关系对，不再叠 CROWD
        "node s | 0 0 20 20 | overlap=class:sheet\n"
        "node a | 25 0 45 20 | class=sheet\n"
        "node b | -45 0 -25 20 | class=sheet\n",
        [],
        ["overlap"],
        ["COLLIDE", "CROWD"],
        [],
    ),
    (
        "overlap-class-empty",  # 未知 class → 悬空目标 warn
        "node s | 0 0 20 20 | overlap=class:ghost\n",
        [],
        ["overlap"],
        [],
        [],
    ),
    (
        "inside-class-not-expanded",  # class: 展开只对 adjacent=/overlap=
        # ——inside= 保持按名直指 → 未审计 ERR
        "node c | 0 0 10 10 | inside=class:cell\n",
        ["inside"],
        [],
        [],
        [],
    ),
    # -- tiles= 真实覆盖 ---------------------------------------------------
    (
        "tiles-ok",
        "node P | 0 0 100 20 |\n"
        "node s1 | 0 0 50 20 | tiles=P\n"
        "node s2 | 50 0 100 20 | tiles=P\n",
        [],
        [],
        [],
        [],
    ),
    (
        "tiles-hole-x",  # 并集 bbox 覆盖但缺一条 x 带
        "node P | 0 0 100 20 |\n"
        "node s1 | 0 0 40 20 | tiles=P\n"
        "node s2 | 60 0 100 20 | tiles=P\n",
        ["tiles"],
        [],
        [],
        [],
    ),
    (
        "tiles-hole-y",  # 只有全宽的下半——顶部无覆盖
        "node P | 0 0 100 20 |\n"
        "node s1 | 0 0 50 10 | tiles=P\n"
        "node s2 | 50 0 100 10 | tiles=P\n",
        ["tiles"],
        [],
        [],
        [],
    ),
    (
        "tiles-2d-ok",  # 2x2 网格覆盖
        "node P | 0 0 100 20 |\n"
        "node s1 | 0 0 50 10 | tiles=P\n"
        "node s2 | 50 0 100 10 | tiles=P\n"
        "node s3 | 0 10 50 20 | tiles=P\n"
        "node s4 | 50 10 100 20 | tiles=P\n",
        [],
        [],
        [],
        [],
    ),
    (
        "tiles-overlap",
        "node P | 0 0 100 20 |\n"
        "node s1 | 0 0 60 20 | tiles=P\n"
        "node s2 | 50 0 100 20 | tiles=P\n",
        ["tiles"],
        [],
        [],
        [],
    ),
    (
        "tiles-no-crowd",  # 同 parent 碎片互为关系——不刷 CROWD
        "node P | 0 0 100 20 |\n"
        "node s1 | 0 0 50 20 | tiles=P\n"
        "node s2 | 50 0 100 20 | tiles=P\n"
        "node Z | 0 40 10 50 |\n",
        [],
        [],
        ["CROWD"],
        ["--gap", "15"],
    ),
    # -- 可重复标量键：链式 align / 多重 overlap -----------------
    (
        "alignx-chain-ok",  # me==A 且 me==C → A·C·me 共轴，无 tag ERR
        "node A | 40 0 60 10 |\n"
        "node B | 45 25 55 35 | alignx=A,alignx=C\n"
        "node C | 30 50 70 60 |\n",
        [],
        [],
        ["tag", "alignx", "CROWD"],
        [],
    ),
    (
        "alignx-chain-fail",  # 链上一个目标跑偏 → 该 ref ERR
        "node A | 40 0 60 10 |\n"
        "node B | 45 25 55 35 | alignx=A,alignx=C\n"
        "node C | 35 50 75 60 |\n",  # cx=55 != 50
        ["alignx"],
        [],
        ["tag"],
        [],
    ),
    (
        "alignx-chain-unaudited",  # 逐 ref 校验：幽灵目标仍 ERR
        "node A | 40 0 60 10 |\nnode B | 45 25 55 35 | alignx=A,alignx=ghost\n",
        ["alignx"],
        [],
        ["tag"],
        [],
    ),
    (
        "aligny-chain-ok",  # y 轴同款链式
        "node A | 0 40 10 60 |\n"
        "node B | 25 45 35 55 | aligny=A,aligny=C\n"
        "node C | 50 30 60 70 |\n",
        [],
        [],
        ["tag", "aligny", "CROWD"],
        [],
    ),
    (
        "alignx-chain-rows",  # 经合并的重打 tag 行成链（\vaudit 模式）
        "node A | 40 0 60 10 |\n"
        "node B | 45 25 55 35 | alignx=A\n"
        "node B | 45 25 55 35 | alignx=C\n"
        "node C | 30 50 70 60 |\n",
        [],
        [],
        ["tag", "alignx"],
        [],
    ),
    (
        "overlap-multi-ok",  # 两声明对都豁免 + 已校验
        "node A | 0 0 40 10 | overlap=B,overlap=C\n"
        "node B | 30 -5 50 5 |\n"
        "node C | -10 5 10 15 |\n",
        [],
        [],
        ["COLLIDE", "overlap", "tag", "CROWD", "NEST"],
        [],
    ),
    (
        "overlap-multi-stale",  # 一对漂移分开 → 只 warn 该对
        "node A | 0 0 40 10 | overlap=B,overlap=C\n"
        "node B | 30 -5 50 5 |\n"
        "node C | -10 12 10 22 |\n",  # A–C 不再相交
        [],
        ["overlap"],
        ["COLLIDE", "tag", "CROWD"],
        [],
    ),
    (
        "twin-chain-ok",  # 对两个目标都断言转置
        "node A | 0 0 30 10 |\n"
        "node B | 50 0 60 30 | twin=A,twin=C\n"  # 10x30 对两个 30x10 twin
        "node C | 90 0 120 10 |\n",
        [],
        [],
        ["tag", "twin", "CROWD"],
        [],
    ),
    (
        "eqww-chain-ok",  # 对两个目标都断言等宽
        "node A | 0 0 20 10 |\n"
        "node B | 40 0 60 15 | eqww=A,eqww=C\n"
        "node C | 80 0 100 5 |\n",
        [],
        [],
        ["tag", "dims", "CROWD"],
        [],
    ),
    (
        "eqww-chain-fail",  # 链上一个目标宽度不同 → dims ERR
        "node A | 0 0 20 10 |\n"
        "node B | 40 0 60 15 | eqww=A,eqww=C\n"
        "node C | 80 0 105 5 |\n",  # w=25 != 20
        ["dims"],
        [],
        ["tag"],
        [],
    ),
    # -- 回归 ------------------------------------------------------------
    (
        "collide-still-errors",
        "node A | 0 0 10 10 |\nnode B | 5 0 15 10 |\n",
        ["COLLIDE"],
        [],
        [],
        [],
    ),
    (
        "square-fails",
        "node A | 0 0 10 12 | square\n",
        ["square"],
        [],
        [],
        [],
    ),
    (
        "eqwh-ok",
        "node A | 0 0 10 30 | eqwh=B\n"
        "node B | 30 40 40 50 | \n",  # A.w=10 == B.h=10；x 间距 20——不挤
        [],
        [],
        [],
        ["--gap", "15"],
    ),
]


# --- 真 xelatex 冒烟（TeX 侧行为）---------------------------------

TEX_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[draw, minimum width=2cm, minimum height=1cm, vaudit={twin=R}] (A) at (0,0) {p};
\path \vaudit{A}{class=zz};  % merge: same node, extra tag
\node[draw, minimum width=2cm, minimum height=1cm, rotate=90, vaudit={twin=A}] (R) at (5,0) {r};
\node[draw, minimum width=1cm, minimum height=1cm, rotate=45, vaudit={square}] (D) at (8,0) {d};
\vzbbox{lane}{(0,4)}{(6,5)}[class=band]
\vzwire{w}{A.east; (3,0.5); R.south}{endpoint=A,R}
\draw (0,6) -- (1,6) node[draw, vaudit={class=mid}] (M) {m} -- (2,6) node[draw] (N) {n};
\end{tikzpicture}
\end{document}
"""

TEX_STALE = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[draw, vaudit={class=x}] (A) at (0,0) {ok};
\draw[vaudit={class=BAD}] (0,2) -- (1,2);
\end{tikzpicture}
\end{document}
"""


def xelatex_smoke():
    """compile a doc using every primitive; check .audit content + warnings."""
    if shutil.which("xelatex") is None:
        print("SKIP xelatex-smoke (no xelatex)")
        return True
    bad = []
    with tempfile.TemporaryDirectory(prefix="fvtex-") as td:
        src = Path(td) / "smoke.tex"
        src.write_text(TEX_DOC)
        env = dict(__import__("os").environ)
        env["TEXINPUTS"] = f"{VIZAUDIT.parent}:" + env.get("TEXINPUTS", "")
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "smoke.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        audit = Path(td) / "smoke.audit"
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            bad.append("xelatex compile failed")
            return False
        if not audit.exists():
            bad.append("smoke.audit not produced")
            return False
        rows = [ln for ln in audit.read_text().splitlines() if "|" in ln]
        box = {}
        wire = []
        a_rows = 0
        for ln in rows:
            head, rest = ln.split("|", 1)
            coords, _, tags = rest.partition("|")
            kind, _, name = head.strip().partition(" ")
            vals = [float(v.replace("pt", "")) for v in coords.split()]
            if kind == "wire":
                wire.append((name.strip(), vals, tags.strip()))
            else:
                box[name.strip()] = (vals, tags.strip())
                a_rows += name.strip() == "A"
        # 旋转 node：2cm x 1cm 转 90° → 审计 w≈1cm h≈2cm (≈28.45/56.9)
        if "R" not in box or not (
            abs(box["R"][0][2] - box["R"][0][0] - 28.4528) < 1.0
            and abs(box["R"][0][3] - box["R"][0][1] - 56.9055) < 1.0
        ):
            bad.append(f"rotated AABB wrong: {box.get('R')}")
        # 45° 菱形：审计 box 须为正方形
        if "D" not in box:
            bad.append("rotated node D missing")
        elif (
            abs((box["D"][0][2] - box["D"][0][0]) - (box["D"][0][3] - box["D"][0][1]))
            > 1.0
        ):
            bad.append(f"45° node not square in audit: {box.get('D')}")
        # vaudit 重打 tag 为 A 多产一行（python 侧合并）
        if a_rows != 2 or box["A"][1] != "class=zz":
            bad.append(f"vaudit re-tag row missing: a_rows={a_rows} A={box.get('A')}")
        # region 携带 tags
        if "lane" not in box or box["lane"][1] != "class=band":
            bad.append(f"region tags missing: {box.get('lane')}")
        # wire 导出 3 途经点 = 6 个 float + endpoint tag
        if not wire or len(wire[0][1]) != 6 or "endpoint=A,R" not in wire[0][2]:
            bad.append(f"wire row wrong: {wire}")
        # path 中途 node 导出自身（期望），尾随 node N 完全缺席
        if "M" not in box or box["M"][1] != "class=mid" or "N" in box:
            bad.append(f"mid-path node audit wrong: {sorted(box)}")

        # 失效/非 node 的 vaudit → LaTeX 告警 + 无 BAD tag 行
        src2 = Path(td) / "stale.tex"
        src2.write_text(TEX_STALE)
        proc2 = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "stale.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        if proc2.returncode != 0:
            print((proc2.stdout + proc2.stderr)[-1500:])
            bad.append("stale.tex compile failed")
        else:
            if "vaudit" not in proc2.stdout or "ignored" not in proc2.stdout:
                bad.append("no vizaudit balance warning for \\draw[vaudit]")
            a2 = (Path(td) / "stale.audit").read_text()
            if "BAD" in a2:
                bad.append("stale \\tikzlastnode row leaked into audit")
            if "class=x" not in a2:
                bad.append("good node row missing in stale.audit")

        # 全链路：冒烟文档的 audit 必须过 check_audit
        if not bad:
            rc, out = run_audit(audit.read_text())
            if rc != 0 or has(out, "twin") or has(out, "square"):
                bad.append(f"check_audit on real rows failed:\n{out}")
    for m in bad:
        print("  ", m)
    return not bad


# --- check_coverage.py fixtures（纯 stdlib，无 xelatex）--------------------

COV_DOC = r"""\begin{tikzpicture}
\node[model, vaudit={}] (A) at (0,0) {a};
\node[vstage] at (0,1.2) {stage1};
\fill[band] (0,2) rectangle (4,3);
\vzbbox{lane}{(0,2)}{(4,3)}
\fill[vteal] (5,0) rectangle (6,1);
\coordinate (c) at (9,9);
\node[msq] (m) at (1,4) {};
\draw[lead] (0,5) -- (2,5);
\node (R) at (8,0) {r};
\path \vaudit{R}{class=x};
\draw[varr] (A) -- (R);
\vzwire{ar}{A;R}{endpoint=A,R}
\draw[varr] (A) -- ++(0,-1) -| (m);
\node at (0,-2) {exempt}; % fv:noaudit
\end{tikzpicture}
"""

COV_OFF_DOC = r"""\begin{tikzpicture}
\node (x) at (0,0) {in-scope};
% fv:coverage off
\node (y) at (0,1) {exempt};
\node (z) at (0,2) {exempt2};
% fv:coverage on
\node (w) at (0,3) {back-on};
\end{tikzpicture}
"""

# \pic 按节点判据：无名 pic 必报；命名 pic 被 \vzbbox 重标即覆盖。
# (l1.north east) 多词锚名经 NAME_RE 解析到 l1，与 \vzwire 途经点互认。
COV_PIC_DOC = r"""\begin{tikzpicture}
\pic[ssw=1.5,ssd=1,sst=0.4] at (0,0) {ssolid=vteal};
\pic[ssw=1.5,ssd=1,sst=0.4] (s2) at (3,0) {ssolid=vblue};
\vzbbox{s2}{(3,0)}{(4.5,1)}
\node[vaudit={}] (l1) at (5,0) {x};
\node[vaudit={}] (l2) at (5,1) {y};
\draw[varr] (l1.north east) -- (l2.south west);
\vzwire{l12}{l1.north east; l2.south west}{endpoint=l1,l2}
\end{tikzpicture}
"""


def run_cov(text):
    """write tex fixture, run check_coverage.py, return (rc, stdout)."""
    with tempfile.TemporaryDirectory(prefix="fvcov-") as td:
        f = Path(td) / "fig.tex"
        f.write_text(text)
        proc = subprocess.run(
            [sys.executable, str(COVERAGE), str(f)],
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout


# \tikzset 样式定义内 vaudit=：使用处按已埋点计；keep 经 beam 传递继承；
# plain 样式与裸 \node (d) 未埋点 → 各报；末行 \draw 内嵌 node[beam] 文字
# 自身已埋点（样式带 vaudit），但 [beam] 是内嵌节点的 opts 不是语句的——
# 语句引用名 ∉ wires 仍报语句级 warn，共 3 warn。
COV_STYLE_DOC = r"""\begin{tikzpicture}
\tikzset{
  beam/.style={card, vaudit={class=tok}},
  keep/.style={beam, fill=vteal!12},
  plain/.style={card},
}
\node[beam] (a) at (0,0) {a};
\node[keep] (b) at (2,0) {b};
\node[plain] (c) at (4,0) {c};
\node (d) at (6,0) {d};
\draw (a) -- (b) node[beam] {mid};
\end{tikzpicture}
"""

# every node 带 vaudit → 所有 \node 使用处已埋点。
COV_EVERYNODE_DOC = r"""\begin{tikzpicture}
\tikzset{every node/.append style={vaudit={}}}
\node (a) at (0,0) {a};
\node[card] (b) at (2,0) {b};
\end{tikzpicture}
"""

# 空文本但带墨迹的节点不豁免：fill=/shade=/pattern=/draw= 都是真墨迹，
# 必须 vaudit 或重标；draw=none 与坐标式 \node (p) {}; 仍豁免。
COV_INK_DOC = r"""\begin{tikzpicture}
\node[fill=vteal] (c) at (0,0) {};
\node[shade] (s) at (2,0) {};
\node[pattern=dots] (d) at (8,0) {};
\node[draw] (b) at (10,0) {};
\node[draw=none] (n) at (4,0) {};
\node (p) at (6,0) {};
\node[fill=vteal, vaudit={}] (ok) at (12,0) {};
\node[fill=vteal] (rt) at (14,0) {};
\path \vaudit{rt}{class=x};
\end{tikzpicture}
"""

# pgfkeys handler 链写法同样算埋点：vaudit/.expand once= 与 vaudit/.expanded=
# 在等号前挂 '/.<handler>(args)' 段，正则按 handler 链识别。
COV_HANDLER_DOC = r"""\begin{tikzpicture}
\node[vaudit/.expand once={\foo}] (a) at (0,0) {a};
\node[vaudit/.expanded={class=tok}] (b) at (2,0) {b};
\node[vaudit={}] (c) at (4,0) {c};
\node (d) at (6,0) {d};
\end{tikzpicture}
"""

# 内嵌 node 复查：wire 镜像只豁免路径部分。
#   hidden   — wire 覆盖的 \draw 内未埋点文字 → warn（盲区修复）
#   seen     — 内嵌 node 自带 vaudit= → 干净
#   tagged   — 内嵌命名 node 被 \vaudit 重标 → 内嵌干净；但语句名字引用
#              多出 tagged ∉ wires → 语句级 warn 照报（先有限定）
#   tail     — 路径 vaudit 只审计最后一个 node（TeX 语义）→ 干净
#   first    — 同一路径上的倒数第二个 node 仍需自理 → warn
#   quiet    — % fv:noaudit 整条豁免
COV_EMBED_DOC = r"""\begin{tikzpicture}
\node[vaudit={}] (b1) at (0,0) {s};
\node[vaudit={}] (b2) at (3,0) {d};
\vzwire{w}{b1;b2}{endpoint=b1,b2}
\draw[varr] (b1) -- (b2) node[vnote] at (1,-1) {hidden};
\draw[varr] (b1) -- (b2) node[vaudit={}] {seen};
\draw[varr] (b1) -- (b2) node (tagged) {rt};
\path \vaudit{tagged}{class=x};
\draw[vaudit={}] (b1) -- (b2) node{tail};
\draw[vaudit={}] (b1) -- (b2) node{first} node{last};
\draw (b1) -- (b2) node{quiet}; % fv:noaudit
\end{tikzpicture}
"""

# calc 角点 \vzbbox：'$(N)+(-2.4cm,0cm)$' 含嵌套括号，平正则抠角点会断——
# 花括号配对解析后 body 仍注册 region，同名 \pic 覆盖不报；(bare) 无埋点照报。
COV_CALC_DOC = r"""\begin{tikzpicture}
\node[vaudit={}] (N) at (0,0) {nref};
\pic[ssw=1.5,ssd=1,sst=0.4] (body) at (1,0) {ssolid=vteal};
\vzbbox{body}{($(N)+(-2.4cm,0cm)$)}{(4,1)}
\pic[ssw=1.5,ssd=1,sst=0.4] (bare) at (6,0) {ssolid=vblue};
\end{tikzpicture}
"""

# 装饰豁免只盖无文本墨水语句：
#   lead-line — 纯引线仍豁免
#   lead-text — \node[lead]{r5-draft} 带真文本 → 语句报
#   lead-mid  — 中途空 {} 节点挂 label=left:{per-token} → 内嵌 + 语句各报
#   lead-fill — 内嵌 fill 节点本身按未埋点墨迹报；语句无文本墨水仍豁免
#   grid-text — grid 路径挂文本节点 → 内嵌 + 语句各报
COV_DECOR_DOC = r"""\begin{tikzpicture}
\coordinate (a) at (0,0);
\coordinate (b) at (2,0);
\draw[lead] (a) -- (b);
\node[lead] at (0,1) {r5-draft};
\draw[lead] (a) -- (b) node[midway,label=left:{per-token}] {};
\draw[lead] (a) -- (b) node[midway,fill=vteal] {};
\draw (0,3) grid (2,4) node {gridnote};
\end{tikzpicture}
"""

# 节点花括号文本里的字面圆括号不是名字引用：剥掉配对 {} 组后语句名引用
# 只剩端点 a/b ⊆ wires → 干净；嵌套 {nest (x)} 同样剥除。未定义节点引用
# (undefined_node) ∉ wires 仍照报语句级 warn。
COV_BRACE_DOC = r"""\begin{tikzpicture}
\node[vaudit={}] (a) at (0,0) {a};
\node[vaudit={}] (b) at (1,0) {b};
\draw[varr] (a) -- (b) node[vaudit={}] {text (hb) {nest (x)} more};
\vzwire{w}{a;b}{endpoint=a,b}
\draw[varr] (a) -- (undefined_node);
\end{tikzpicture}
"""


def coverage_cases():
    """check_coverage fixtures -> [(name, [bad...])] like the CASES loop."""
    rows = []

    rc, out = run_cov(COV_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc} (warn-only checker must exit 0)")
    if len(warns) != 3:
        bad.append(f"want exactly 3 coverage warns, got {warns}")
    for needle in ("vstage", "vteal", "varr"):
        if not any(needle in w for w in warns):
            bad.append(f"no warn mentions {needle!r}")
    rows.append(("coverage-mixed", bad))

    rc, out = run_cov(COV_OFF_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 2:
        bad.append(f"want 2 warns outside off/on region, got {warns}")
    if not any("in-scope" in w for w in warns):
        bad.append("node before off-region not warned")
    if not any("back-on" in w for w in warns):
        bad.append("node after on-region not warned")
    if any("exempt" in w for w in warns):
        bad.append("off-region nodes warned")
    rows.append(("coverage-off-on", bad))

    proc = subprocess.run(
        [sys.executable, str(COVERAGE), "/nonexistent-fig.tex"],
        capture_output=True,
        text=True,
    )
    rows.append(
        (
            "coverage-missing-file",
            []
            if proc.returncode == 2
            else [f"missing file rc={proc.returncode}, want 2"],
        )
    )

    rc, out = run_cov(COV_PIC_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 1 or "\\pic" not in warns[0]:
        bad.append(f"want exactly 1 warn on the unnamed \\pic, got {warns}")
    rows.append(("coverage-pic-multiword", bad))

    # \tikzset 样式内 vaudit= 使用处生效：beam 直挂、keep 传递继承均干净，
    # plain/裸节点/\draw 语句报出；内嵌 node[beam] 不再报但语句照报。
    rc, out = run_cov(COV_STYLE_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 3:
        bad.append(f"want 3 warns (plain + bare + \\draw), got {warns}")
    if not any("plain" in w for w in warns):
        bad.append(f"plain-styled node not warned: {warns}")
    if not any("(d)" in w for w in warns):
        bad.append(f"bare node (d) not warned: {warns}")
    if not any("\\draw" in w for w in warns):
        bad.append(f"unwired \\draw not warned: {warns}")
    if any("embeds unaudited node" in w for w in warns):
        bad.append(f"audit-styled embedded node warned: {warns}")
    rows.append(("coverage-tikzset-vaudit", bad))

    rc, out = run_cov(COV_EVERYNODE_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if warns:
        bad.append(f"every-node vaudit should cover all, got {warns}")
    rows.append(("coverage-every-node", bad))

    # 空文本 + 墨迹键 = 真墨迹节点，必须埋点：fill/shade/pattern/draw 各报一条；
    # draw=none、无键坐标节点、vaudit= 与 \vaudit 重标各自豁免通道不报。
    rc, out = run_cov(COV_INK_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 4:
        bad.append(f"want 4 warns (fill/shade/pattern/draw ink), got {warns}")
    for needle in ("(c)", "(s)", "(d)", "(b)"):
        if not any(needle in w for w in warns):
            bad.append(f"ink node {needle} not warned: {warns}")
    for good in ("(n)", "(p)", "(ok)", "(rt)"):
        if any(good in w for w in warns):
            bad.append(f"exempt/covered node {good} warned: {warns}")
    rows.append(("coverage-empty-ink", bad))

    # handler 链 vaudit/.expand once=、vaudit/.expanded= 均算埋点；
    # 只剩裸节点 (d) 报一条。
    rc, out = run_cov(COV_HANDLER_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 1 or "(d)" not in warns[0]:
        bad.append(f"want only bare node (d) warned, got {warns}")
    rows.append(("coverage-vaudit-handlers", bad))

    # wire 覆盖的 \draw 只豁免路径：hidden/first 内嵌文字报出；
    # seen/tail/quiet 各自通道干净；tagged 内嵌干净但语句引用 ∉ wires 报语句。
    rc, out = run_cov(COV_EMBED_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    embeds = [w for w in warns if "embeds unaudited node" in w]
    if len(warns) != 3:
        bad.append(f"want 3 warns (2 embeds + 1 stmt), got {warns}")
    if len(embeds) != 2:
        bad.append(f"want 2 embedded-node warns, got {embeds}")
    if not any("hidden" in w for w in embeds):
        bad.append(f"embedded 'hidden' not warned: {warns}")
    if not any("first" in w for w in embeds):
        bad.append(f"embedded 'first' not warned: {warns}")
    if not any("\\draw" in w and "tagged" in w for w in warns):
        bad.append(f"tagged-name \\draw stmt not warned: {warns}")
    for good in ("seen", "tail", "last", "quiet"):
        if any(good in w for w in warns):
            bad.append(f"clean embedded node {good!r} warned: {warns}")
    rows.append(("coverage-embedded-node", bad))

    # calc 角点 \vzbbox：body 仍注册 region → 同名 \pic 覆盖不报；
    # 未埋点的 (bare) \pic 照报，字面角点行为由 coverage-pic-multiword 兜底。
    rc, out = run_cov(COV_CALC_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 1 or "(bare)" not in warns[0]:
        bad.append(f"want exactly 1 warn on \\pic (bare), got {warns}")
    rows.append(("coverage-vzbbox-calc", bad))

    # 装饰键只豁免无文本墨水语句：\node[lead]{text}、label=/pin= 内嵌节点
    # 与其宿主语句回到审计路径；纯引线与 fill-only 内嵌语句仍豁免。
    rc, out = run_cov(COV_DECOR_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    embeds = [w for w in warns if "embeds unaudited node" in w]
    stmts = [w for w in warns if "embeds unaudited node" not in w]
    if len(warns) != 6 or len(embeds) != 3 or len(stmts) != 3:
        bad.append(f"want 6 warns (3 stmt + 3 embeds), got {warns}")
    if not any("r5-draft" in w for w in stmts):
        bad.append(f"\\node[lead] text not warned: {warns}")
    if not any("\\draw" in w and "label" in w for w in stmts):
        bad.append(f"label-inked \\draw[lead] stmt not warned: {warns}")
    if not any("\\draw" in w and "gridnote" in w for w in stmts):
        bad.append(f"text-inked grid stmt not warned: {warns}")
    for needle in ("per-token", "fill=vteal", "gridnote"):
        if not any(needle in w for w in embeds):
            bad.append(f"embedded {needle!r} not warned: {warns}")
    if any("line 4:" in w for w in warns):
        bad.append(f"pure lead line warned: {warns}")
    if any("line 7:" in w for w in stmts):
        bad.append(f"fill-only embed \\draw[lead] stmt warned: {warns}")
    rows.append(("coverage-decor-ink", bad))

    # 花括号文本的 (hb)/(x) 不产名字引用：wire 覆盖的 \draw 干净；
    # 真未定义引用 undefined_node 的 \draw 仍报唯一一条 warn。
    rc, out = run_cov(COV_BRACE_DOC)
    warns = warn_lines(out, "coverage")
    bad = []
    if rc != 0:
        bad.append(f"rc={rc}")
    if len(warns) != 1 or "undefined_node" not in warns[0]:
        bad.append(f"want exactly 1 warn on undefined_node \\draw, got {warns}")
    if any("hb" in w for w in warns):
        bad.append(f"brace-text (hb) leaked into name refs: {warns}")
    rows.append(("coverage-brace-text", bad))
    return rows


# --- check_readback_tex.py（需 xelatex + pdftotext）------------------------

RB_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[draw, minimum width=3.2cm, minimum height=1.2cm, vaudit={}] (A) at (0,0) {InWord};
\node[anchor=west, xshift=-8pt] at (A.east) {CrossWord};
\node[draw, vaudit={}] (B) at (0,-3) {Btext};
\end{tikzpicture}
\end{document}
"""

# 画布被 \useasboundingbox 钉小，文字伸出裁切边 -> 词盒部分在页外。
# border=0pt：standalone 的 border 会掩盖小量伸出。
RB_CLIP_DOC = r"""\documentclass[border=0pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\useasboundingbox (0,-0.5) rectangle (4,0.5);
\node[anchor=west] at (-0.6,0) {StraddlingWordHere};
\node[vaudit={}] (A) at (3,0) {a};
\end{tikzpicture}
\end{document}
"""

# 两段文字词盒真实相交（BetaWord 起点压进 AlphaWord 尾部、基线错开），
# 不属于任何 audited 盒 -> word-vs-word warn；下方 audited 盒作证映射在位。
RB_OVERLAP_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[anchor=west] at (0,0) {AlphaWord};
\node[anchor=west] at (1.35,-0.12) {BetaWord};
\node[vaudit={}] (A) at (0,-2) {lower};
\end{tikzpicture}
\end{document}
"""

# 词心骑盒边的 straddle：EdgeWord 居中压 A.east；TailWord 心在 B 内、
# 尾部探出 B.east ~15pt——两者词心都不在盒外（旧 inside 判据双双逃逸），
# 词盒都跨盒边界 -> crosses。InWord/Btext 完全盒内 -> 不报。
# B 加宽到 5cm：TailWord 与 Btext 拉开 ~34pt，避免 pdftotext 并词。
RB_EDGE_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[draw, minimum width=3.2cm, minimum height=1.2cm, vaudit={}] (A) at (0,0) {InWord};
\node at (A.east) {EdgeWord};
\node[draw, minimum width=5cm, minimum height=1.2cm, vaudit={}] (B) at (0,-3) {Btext};
\node[anchor=east, xshift=15pt] at (B.east) {TailWord};
\end{tikzpicture}
\end{document}
"""

# \vzwire 折线横穿词盒：thru 在 y=0 穿过垂直居中在 y=0 的 WireVictimWord；
# conn 的终点扎进 LabelText 词盒内（gap=0 < 2bp）属正常连接 -> 豁免；
# aa/bb 的 audited 盒只作 origin 校准见证，不与任何词盒纠缠。
RB_WIRE_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[anchor=west] at (0,0) {WireVictimWord};
\node[anchor=west] (L) at (0,-1.5) {LabelText};
\vzwire{thru}{(-2,0); (4,0)}{endpoint=A,B}
\vzwire{conn}{(-2,-1.5); (0.15,-1.5)}{endpoint=A,L}
\node[vaudit={}] (A) at (-2,-3) {aa};
\node[vaudit={}] (B) at (4,-3) {bb};
\end{tikzpicture}
\end{document}
"""


def readback_wordpair_unit():
    """word-vs-word 规则的纯 python fixture——不依赖 pdftotext/xelatex。"""
    w = rb.Word
    words = [
        w(0, 0, 10, 6, "Alpha", 0),
        w(8, 2, 20, 8, "Beta", 0),  # dx=2 dy=4 → 相交
        w(30, 0, 40, 6, "Gamma", 0),  # 完全分离
        w(2, 20, 9, 26, "Far", 0),  # x 与 Alpha 相交但 y 分离
        w(0, 0, 10, 6, "Other", 1),  # 与 Alpha 同盒但不同页
        w(10.5, 20, 16, 26, "Touch", 0),  # 与 Alpha x 相交 -0.5、y 分离 → 不碰
    ]
    warns = rb.word_overlaps(words, 1.0)
    bad = []
    if len(warns) != 1 or 'word "Alpha" overlaps word "Beta"' not in warns[0]:
        bad.append(f"want exactly one Alpha/Beta overlap, got {warns}")
    return ("readback-wordpair-unit", bad)


def readback_straddle_unit():
    """crosses 规则改为边界相交判定——词心骑边/尾部探出都要报。"""
    w = rb.Word
    box = [("A", rb.Rect(20, 0, 60, 20))]
    words = [
        w(50, 5, 70, 15, "Edge", 0),  # 词心 x=60 恰压盒右边 → 报（旧 inside 逃逸）
        w(45, 5, 61.5, 15, "Tail", 0),  # 心在盒内、尾部探出 1.5bp → 报
        w(0, -5, 100, 30, "Big", 0),  # 词盒整个罩住盒 → 边界相交 → 报
        w(30, 5, 50, 15, "In", 0),  # 完全盒内 → 不报（coverage 的职责）
        w(45, 5, 60.05, 15, "Dust", 0),  # 探出 0.05bp < eps → 算盒内 → 不报
        w(70, 5, 90, 15, "Out", 0),  # 完全盒外不相交 → 不报
        w(60, 5, 80, 15, "Graze", 0),  # 仅贴边 dx=0 → 不报
    ]
    warns = rb.box_crossings(words, box, 1.0)
    bad = []
    got = sorted(w.split('"')[1] for w in warns)
    if got != ["Big", "Edge", "Tail"]:
        bad.append(f"want Edge+Tail+Big crosses only, got {warns}")
    return ("readback-straddle-unit", bad)


def readback_wire_unit():
    """wire-vs-word 规则——声明折线穿词即报；端点搭词盒边缘属正常连接。"""
    w = rb.Word
    words = [
        w(20, 0, 40, 8, "Victim", 0),  # thru 横穿中腰 → 报
        w(20, 30, 44, 38, "Label", 0),  # conn 端点扎进盒内 2bp → 豁免
        w(60, 0, 80, 8, "Far", 0),  # 谁都不碰
    ]
    wires = [
        ("thru", [(0, 4), (60, 4)]),  # 水平穿过 Victim 中腰，两端离盒远
        ("conn", [(0, 34), (22, 34)]),  # 端点在 Label 盒内（gap=0）→ 豁免
        ("miss", [(0, 20), (60, 20)]),  # 从词间空当穿过 → 不报
        ("gra", [(0, 7.5), (50, 7.5)]),  # 只咬进 Victim 0.5bp < depth → 不报
    ]
    warns = rb.wire_word_crossings(wires, words, 1.0)
    bad = []
    if len(warns) != 1 or 'wire "thru" crosses word "Victim"' not in warns[0]:
        bad.append(f"want exactly one thru x Victim warn, got {warns}")
    return ("readback-wire-unit", bad)


def readback_case():
    """编译一个词骑跨已审计边界的文档 -> warn。"""
    if shutil.which("xelatex") is None or shutil.which("pdftotext") is None:
        print("SKIP readback (no xelatex/pdftotext)")
        return []
    bad = []
    with tempfile.TemporaryDirectory(prefix="fvrb-") as td:
        src = Path(td) / "rb.tex"
        src.write_text(RB_DOC)
        env = dict(os.environ)
        env["TEXINPUTS"] = f"{VIZAUDIT.parent}:" + env.get("TEXINPUTS", "")
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "rb.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            return [("readback-cross", ["xelatex compile failed"])]
        audit = Path(td) / "rb.audit"
        if "origin " not in audit.read_text():
            bad.append("origin row missing from rb.audit")
        p = subprocess.run(
            [
                sys.executable,
                str(READBACK),
                str(Path(td) / "rb.pdf"),
                str(audit),
            ],
            capture_output=True,
            text=True,
        )
        warns = warn_lines(p.stdout, "readback")
        if p.returncode != 0:
            bad.append(f"readback rc={p.returncode} (warn-only, want 0)")
        cross = [w for w in warns if "crosses audited box" in w]
        if (
            len(cross) != 1
            or 'word "CrossWord"' not in cross[0]
            or '"A"' not in cross[0]
        ):
            bad.append(f"want exactly one CrossWord->A crossing, got {warns}")
        if any("InWord" in w or "Btext" in w for w in warns):
            bad.append(f"interior words flagged: {warns}")

        # straddle: 词盒部分跨出页面裁切边 -> clipped at page edge
        src.write_text(RB_CLIP_DOC)
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "rb.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        sbad = []
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            sbad.append("straddle compile failed")
        else:
            p = subprocess.run(
                [
                    sys.executable,
                    str(READBACK),
                    str(Path(td) / "rb.pdf"),
                    str(Path(td) / "rb.audit"),
                ],
                capture_output=True,
                text=True,
            )
            warns = warn_lines(p.stdout, "readback")
            clip = [w for w in warns if "clipped at page edge" in w]
            # poppler 会丢掉整个出界的字形——词文本可能只剩 'addlingWordHere'
            if not clip or not any("WordHere" in w for w in clip):
                sbad.append(f"want a WordHere clip warn, got {warns}")
            if any("outside page" in w for w in warns):
                sbad.append(f"straddle misreported as outside-page: {warns}")

        # word-vs-word：两段非 audited 文字真实相交 -> overlaps warn
        src.write_text(RB_OVERLAP_DOC)
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "rb.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        obad = []
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            obad.append("overlap compile failed")
        else:
            p = subprocess.run(
                [
                    sys.executable,
                    str(READBACK),
                    str(Path(td) / "rb.pdf"),
                    str(Path(td) / "rb.audit"),
                ],
                capture_output=True,
                text=True,
            )
            warns = warn_lines(p.stdout, "readback")
            ov = [w for w in warns if "overlaps word" in w]
            if len(ov) != 1 or not any(
                "AlphaWord" in w and "BetaWord" in w for w in ov
            ):
                obad.append(f"want one AlphaWord x BetaWord overlap, got {warns}")
            if any("crosses audited box" in w for w in warns):
                obad.append(f"unexpected crosses warn: {warns}")

        # edge-straddle: 词心骑边/尾探出盒都报 crosses；盒内词不报
        src.write_text(RB_EDGE_DOC)
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "rb.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        ebad = []
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            ebad.append("edge-straddle compile failed")
        else:
            p = subprocess.run(
                [
                    sys.executable,
                    str(READBACK),
                    str(Path(td) / "rb.pdf"),
                    str(Path(td) / "rb.audit"),
                ],
                capture_output=True,
                text=True,
            )
            warns = warn_lines(p.stdout, "readback")
            cross = [w for w in warns if "crosses audited box" in w]
            if not (
                any('word "EdgeWord"' in w and '"A"' in w for w in cross)
                and any('word "TailWord"' in w and '"B"' in w for w in cross)
            ):
                ebad.append(f"want EdgeWord->A + TailWord->B crosses, got {warns}")
            if any("InWord" in w or "Btext" in w for w in warns):
                ebad.append(f"interior words flagged: {warns}")

        # wire-vs-word: vzwire 折线穿词 -> warn；端点搭词盒 -> 豁免
        src.write_text(RB_WIRE_DOC)
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "rb.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        wbad = []
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            wbad.append("wire compile failed")
        else:
            audit = Path(td) / "rb.audit"
            if not any(
                ln.startswith("wire thru") for ln in audit.read_text().splitlines()
            ):
                wbad.append("wire row missing from rb.audit")
            p = subprocess.run(
                [
                    sys.executable,
                    str(READBACK),
                    str(Path(td) / "rb.pdf"),
                    str(audit),
                ],
                capture_output=True,
                text=True,
            )
            warns = warn_lines(p.stdout, "readback")
            wx = [w for w in warns if "crosses word" in w]
            if not any('wire "thru"' in w and 'word "WireVictimWord"' in w for w in wx):
                wbad.append(f"want thru x WireVictimWord warn, got {warns}")
            if any("conn" in w or "LabelText" in w for w in warns):
                wbad.append(f"endpoint connection not exempt: {warns}")
        return [
            ("readback-cross", bad),
            ("readback-straddle", sbad),
            ("readback-wordpair", obad),
            ("readback-edge", ebad),
            ("readback-wire", wbad),
        ]
    return [
        ("readback-cross", bad),
        ("readback-straddle", ["xelatex missing"]),
        ("readback-wordpair", ["xelatex missing"]),
        ("readback-edge", ["xelatex missing"]),
        ("readback-wire", ["xelatex missing"]),
    ]


# --- render_tex.py --overlay 冒烟（需 xelatex）-----------------------------

OVL_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\input{vizaudit}
\begin{document}
\begin{tikzpicture}
\node[draw, minimum width=2cm, minimum height=1cm, vaudit={}] (A) at (0,0) {a};
\node[draw, minimum width=2cm, minimum height=1cm, vaudit={}] (B) at (5,0) {b};
\draw (A) -- (B);
\vzwire{ab}{A;B}{endpoint=A,B}
\end{tikzpicture}
\end{document}
"""


def overlay_smoke():
    """render_tex.py --overlay on an audit-clean doc -> overlay pdf + rc 0."""
    if shutil.which("xelatex") is None:
        print("SKIP overlay-smoke (no xelatex)")
        return True
    bad = []
    with tempfile.TemporaryDirectory(prefix="fvovl-") as td:
        src = Path(td) / "ovl.tex"
        src.write_text(OVL_DOC)
        proc = subprocess.run(
            [
                sys.executable,
                str(RENDER_TEX),
                str(src),
                "--outdir",
                td,
                "--no-png",
                "--no-svg",
                "--overlay",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2500:])
            bad.append(f"render_tex --overlay rc={proc.returncode}")
        if not (Path(td) / "ovl.overlay.pdf").exists():
            bad.append("ovl.overlay.pdf missing")
        audit = Path(td) / "ovl.audit"
        if not audit.exists() or "origin " not in audit.read_text():
            bad.append("origin row missing from ovl.audit")
    for m in bad:
        print("  ", m)
    return not bad


# --- frag 导言预载 + 正文 input 守卫（xelatex）-----------------------

# frag 不自带 \input{vizaudit}：preamble 预载必须让审计照常产出。
FRAG_DOC = r"""\begin{tikzpicture}
\node[draw, minimum width=2cm, minimum height=1cm, vaudit={}] (A) at (0,0) {a};
\end{tikzpicture}
"""

# frag 里残留 \input{vizaudit}：双载守卫 no-op，审计仍由 preamble 生效。
FRAG_STRAY = r"""\input{vizaudit}
\begin{tikzpicture}
\node[draw, minimum width=2cm, minimum height=1cm, vaudit={}] (A) at (0,0) {a};
\end{tikzpicture}
"""

# 正文里 \input{vizaudit}：组级守卫拦下并警告，不产生 .audit。
# （文档不能用 vaudit —— 机制被跳过后该 key 未定义。）
GUARD_DOC = r"""\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\begin{document}
\input{vizaudit}
\begin{tikzpicture}
\node[draw] at (0,0) {plain};
\end{tikzpicture}
\end{document}
"""


def frag_smoke():
    """render_tex --frag：不自带 input 的 frag 也审计；残留 input 是无害 no-op。"""
    if shutil.which("xelatex") is None:
        print("SKIP frag-smoke (no xelatex)")
        return True
    bad = []
    for stem, body in (("fragplain", FRAG_DOC), ("fragstray", FRAG_STRAY)):
        with tempfile.TemporaryDirectory(prefix="fvfrag-") as td:
            src = Path(td) / f"{stem}.tex"
            src.write_text(body)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_TEX),
                    str(src),
                    "--frag",
                    "--outdir",
                    td,
                    "--no-png",
                    "--no-svg",
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print((proc.stdout + proc.stderr)[-2500:])
                bad.append(f"{stem}: render_tex --frag rc={proc.returncode}")
                continue
            audit = Path(td) / f"{stem}.audit"
            if not audit.exists():
                bad.append(f"{stem}: no .audit produced")
            elif "origin " not in audit.read_text():
                bad.append(f"{stem}: origin row missing")
    for m in bad:
        print("  ", m)
    return not bad


def guard_smoke():
    """body \\input{vizaudit}：组级守卫警告 + 不产生 .audit。"""
    if shutil.which("xelatex") is None:
        print("SKIP guard-smoke (no xelatex)")
        return True
    bad = []
    with tempfile.TemporaryDirectory(prefix="fvgrd-") as td:
        src = Path(td) / "guard.tex"
        src.write_text(GUARD_DOC)
        env = dict(os.environ)
        env["TEXINPUTS"] = f"{VIZAUDIT.parent}:" + env.get("TEXINPUTS", "")
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "guard.tex"],
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode != 0:
            print((proc.stdout + proc.stderr)[-2000:])
            bad.append("guard.tex compile failed")
        else:
            if "loaded inside a group" not in proc.stdout:
                bad.append("no 'loaded inside a group' warning in xelatex log")
            if (Path(td) / "guard.audit").exists():
                bad.append("guard.audit produced despite body input")
    for m in bad:
        print("  ", m)
    return not bad


def main() -> int:
    fails = 0
    extra = 0
    for name, fixture, want_err, want_warn, forbid, flags in CASES:
        rc, out = run_audit(fixture, *flags)
        bad = []
        if want_err and rc == 0:
            bad.append("expected errors but exit 0")
        if not want_err and rc != 0:
            bad.append(f"expected clean but exit {rc}")
        for r in want_err:
            if not has(out, r, "ERR"):
                bad.append(f"missing ERR {r}:")
        for r in want_warn:
            if not has(out, r, "warn"):
                bad.append(f"missing warn {r}:")
        for r in forbid:
            if has(out, r):
                bad.append(f"forbidden rule fired: {r}")
        ok = not bad
        print(("PASS" if ok else "FAIL"), name, "" if ok else f"{bad} | {out.strip()}")
        fails += 0 if ok else 1

    for name, bad in (
        *coverage_cases(),
        readback_wordpair_unit(),
        readback_straddle_unit(),
        readback_wire_unit(),
        *readback_case(),
    ):
        ok = not bad
        print(("PASS" if ok else "FAIL"), name, "" if ok else f"{bad}")
        extra += 1
        fails += 0 if ok else 1

    ok = xelatex_smoke()
    print(("PASS" if ok else "FAIL"), "xelatex-smoke")
    fails += 0 if ok else 1
    extra += 1

    ok = overlay_smoke()
    print(("PASS" if ok else "FAIL"), "overlay-smoke")
    fails += 0 if ok else 1
    extra += 1

    ok = frag_smoke()
    print(("PASS" if ok else "FAIL"), "frag-smoke")
    fails += 0 if ok else 1
    extra += 1

    ok = guard_smoke()
    print(("PASS" if ok else "FAIL"), "guard-smoke")
    fails += 0 if ok else 1
    extra += 1

    print(f"--- {len(CASES) + extra} cases, {fails} failed ---")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
