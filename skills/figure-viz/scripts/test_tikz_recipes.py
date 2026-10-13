#!/usr/bin/env python3
"""test_tikz_recipes.py — vizstyle.tex 配方族冒烟：四族 token 真实编译 + 审计全绿。

每族一个 .frag fixture（pgm plate / nn-blockstack / seq-lifeline /
selfmsg via= 逃生舱 / sn-edge 搜索树），经 render_tex.py 走真实 xelatex +
check_audit + check_coverage + check_readback 全链路（.frag 后缀自动
嗅探，不显式传 --frag）；断言 rc==0、.audit 落盘、
输出无 "ERR " 行——即 token 定义、配方宏（\\nskipw/\\nskipwe/\\selfmsg/
vselfmsg pic/\\snkids/\\seqnum）与审计埋点处方在真实文件里自洽。

    python3 scripts/test_tikz_recipes.py

任一 FAIL → 退出 1。只依赖 stdlib；无 xelatex 时全部 SKIP（返回 0）。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from testkit import FAILS, check

SCRIPTS = Path(__file__).resolve().parent
RENDER_TEX = SCRIPTS / "render_tex.py"

# --- fixtures（与 references/tikz/recipes.md 骨架同源，审计埋点按处方写全） ----

# pgm plate：const/lat/obs/plate/plab + class=rv 等大 + inside=pl 成员 +
# plab 角标 adjacent=w + 穿板连线 via=pl。
PGM_FRAG = r"""\begin{tikzpicture}[x=1cm,y=1cm]
\node[const, vaudit={}] (al) at (-1.6,1.4) {$\alpha$};
\node[lat, vaudit={class=rv}] (th) at (0,1.4) {$\theta$};
\node[lat, vaudit={class=rv,inside=pl}] (z) at (0,-0.6) {$z$};
\node[obs, vaudit={class=rv,inside=pl}] (w) at (1.7,-0.6) {$w$};
\node[plate, fit=(z)(w), inner xsep=10pt, inner ysep=14pt, vaudit={}] (pl) {};
\node[plab, anchor=south east, vaudit={inside=pl,adjacent=w}]
  at ($(pl.south east)+(-3pt,3pt)$) {$N$};
\draw[varr] (al) -- (th);
\vzwire{wat}{al;th}{endpoint=al,th}
\draw[varr] (th) -- (z);
\vzwire{wtz}{th;z}{endpoint=th,z via=pl}
\draw[varr] (z) -- (w);
\vzwire{wzw}{z;w}{endpoint=z,w via=pl}
\end{tikzpicture}
"""

# nn-blockstack：blk/tap/vadd 三类 + alignx 链 + \nskipw（西通道）与
# \nskipwe（东通道）两宏各一条跳连。坐标按 pitch 台账排：h=1.0 块高、
# g1=0.95（tap→块底）、g2=0.72（块顶→add）、g3=0.78（add→下 tap），
# 单元 pitch P=3.45，tap/add/blk 逐单元严格 +P。
NN_FRAG = r"""\begin{tikzpicture}[x=1cm,y=1cm,
  blk/.style={model, draw=#1, fill=#1!14, text width=2.0cm,
              minimum height=1.0cm, align=center},
]
\node[blk=vteal, vaudit={class=blk}] (embed) at (0,0) {embed};
\node[mdot=vink, vaudit={class=tap}] (s1) at (0,1.15) {};
\node[blk=vviolet, vaudit={class=blk,alignx=embed}] (attn) at (0,2.60) {attn};
\node[vadd, vaudit={class=add,alignx=embed}] (ad1) at (0,3.82) {$+$};
\node[mdot=vink, vaudit={class=tap}] (s2) at (0,4.60) {};
\node[blk=vgreen, vaudit={class=blk,alignx=embed}] (mlp) at (0,6.05) {mlp};
\node[vadd, vaudit={class=add,alignx=embed}] (ad2) at (0,7.27) {$+$};
\draw[varr] (embed.north) -- (s1.south);
\vzwire{we1}{embed.north;s1.south}{endpoint=embed,s1}
\draw[varr] (s1.north) -- (attn.south);
\vzwire{w1a}{s1.north;attn.south}{endpoint=s1,attn}
\draw[varr] (attn.north) -- (ad1.south);
\vzwire{wa1}{attn.north;ad1.south}{endpoint=attn,ad1}
\draw[varr] (ad1.north) -- (s2.south);
\vzwire{w12}{ad1.north;s2.south}{endpoint=ad1,s2}
\draw[varr] (s2.north) -- (mlp.south);
\vzwire{w2m}{s2.north;mlp.south}{endpoint=s2,mlp}
\draw[varr] (mlp.north) -- (ad2.south);
\vzwire{wm2}{mlp.north;ad2.south}{endpoint=mlp,ad2}
\nskipw{s1}{ad1}{-2.3}{sk1}{}
\nskipwe{s2}{ad2}{2.3}{sk2}{}
\end{tikzpicture}
"""

# seq-lifeline：hdr 头盒 class + lifeline via=被盖条 + act 条 adjacent=头盒
# + eqww 宽链（条时长不同天然不等高，class=act 是陷阱）+ 条缘命名坐标消息
# + \seqnum 序号 + \selfmsg 宏形与 vselfmsg pic 形（selfw 负值左折）各一条
# 自消息，两条标签都带 \\ 折行（宏形 align=left、pic 形 align=right）+
# \path \vaudit 给宏产标签补埋点。
SEQ_FRAG = r"""\begin{tikzpicture}[x=1cm,y=1cm]
\node[model, draw=vteal, fill=vteal!12, minimum width=1.8cm,
      vaudit={class=hdr}] (S1) at (0,0) {S1};
\node[model, draw=vorange, fill=vorange!12, minimum width=1.8cm,
      vaudit={class=hdr}] (S2) at (4.5,0) {S2};
\draw[lifeline] (S1.south) -- (0,-3.6);
\vzwire{lf1}{S1.south;0,-3.6}{endpoint=S1 via=a1}
\draw[lifeline] (S2.south) -- (4.5,-3.6);
\vzwire{lf2}{S2.south;4.5,-3.6}{endpoint=S2 via=a2}
\node[act=vteal, minimum height=2.0cm, vaudit={adjacent=S1}]
  (a1) at (0,-0.7) {};
\node[act=vorange, minimum height=1.4cm, vaudit={adjacent=S2,eqww=a1}]
  (a2) at (4.5,-0.7) {};
\coordinate (m1a) at (0.12,-1.5);
\coordinate (m1b) at (4.38,-1.5);
\draw[varr] (m1a) -- (m1b)
  node[midway, above=1pt, vnote, vaudit={}] {\seqnum~\texttt{RequestVote}};
\vzwire{mm1}{m1a;m1b}{endpoint=a1,a2}
\coordinate (s1o) at (0.12,-2.1);
\selfmsg{s1o}{a1}{m2}{\seqnum~local\\work}{}
\path \vaudit{m2l}{};
\coordinate (s2o) at (-0.12,-1.8);
\pic[selfw=-0.9, vaudit={}] at (s2o) {vselfmsg={a1}{m3}{\seqnum~save\\state}{}};
\end{tikzpicture}
"""

# selfmsg via= 逃生舱：两条自消息折回腿各压一个合法穿越徽章（card），
# 第五/第四参 {via=bdg} 声明后 WIRE-CROSS 豁免。bdg 距条缘与标签节点的
# 间距刻意拉开 >10pt，避开 CROWD；pic 形 selfw=-1.5 左折加长折回腿。
SELFVIA_FRAG = r"""\begin{tikzpicture}[x=1cm,y=1cm]
\node[model, draw=vteal, fill=vteal!12, minimum width=1.8cm,
      vaudit={class=hdr}] (S1) at (0,0) {S1};
\draw[lifeline] (S1.south) -- (0,-3.6);
\vzwire{lf1}{S1.south;0,-3.6}{endpoint=S1 via=a1}
\node[act=vteal, minimum height=2.0cm, vaudit={adjacent=S1}]
  (a1) at (0,-0.7) {};
\coordinate (s1o) at (0.12,-2.1);
\node[card, fill=vgold!30, vaudit={}] (bdg) at (0.75,-2.1) {x};
\selfmsg{s1o}{a1}{m2}{\seqnum~retry}{via=bdg}
\path \vaudit{m2l}{};
\coordinate (s2o) at (-0.12,-2.0);
\node[card, fill=vgold!30, vaudit={}] (bdg2) at (-0.75,-2.0) {y};
\pic[selfw=-1.5, vaudit={}] at (s2o)
  {vselfmsg={a1}{m3}{\seqnum~wait}{via=bdg2}};
\end{tikzpicture}
"""

# sn-edge 搜索树：snroot/snkeep/snghost/snret 节点双用 + 钉尺寸后 class=tk
# 等大断言 + \snkids 按态分组批量连边——前三条走默认竖树锚 south,north，
# 末条 \snkids[west,east] 走横树可选锚对（声明折线钉边界锚，裸节点名的
# 心到心折线会穿端点盒内文字触发 readback wire-crosses-text）。
TREE_FRAG = r"""\begin{tikzpicture}[x=1cm,y=1cm,
  tk/.style={card, #1, text width=0.9cm, minimum height=0.8cm, align=center},
]
\node[tk=snroot,  vaudit={class=tk}] (r) at (0,0) {$\langle s\rangle$};
\node[tk=snkeep,  vaudit={class=tk}] (a) at (-1.6,-1.3) {the};
\node[tk=snghost, vaudit={class=tk}] (b) at (1.6,-1.3) {a};
\node[tk=snret,   vaudit={class=tk}] (c) at (-1.6,-2.6) {cat};
\node[tk=snret,   vaudit={class=tk}] (d) at (-3.4,-2.6) {dog};
\snkids{r}{snkeep}{a}
\snkids{r}{snghost}{b}
\snkids{a}{snret}{c}
\snkids[west,east]{c}{snret}{d}
\end{tikzpicture}
"""

FIXTURES = {
    "pgm": PGM_FRAG,
    "nn": NN_FRAG,
    "seq": SEQ_FRAG,
    "selfvia": SELFVIA_FRAG,
    "tree": TREE_FRAG,
}


def run_frag(stem, body):
    """写 .frag 到临时目录跑 render_tex 全链路，返回 (rc, combined output, outdir).

    不显式传 --frag：.frag 后缀自动嗅探即 render_tex 直调路径的等价入口。
    """
    td = tempfile.TemporaryDirectory(prefix="fvrcp-")
    outdir = Path(td.name)
    src = outdir / f"{stem}.frag"
    src.write_text(body)
    proc = subprocess.run(
        [
            sys.executable,
            str(RENDER_TEX),
            str(src),
            "--outdir",
            str(outdir),
            "--no-png",
            "--no-svg",
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr, td


def main():
    if shutil.which("xelatex") is None:
        print("SKIP recipe-smoke (no xelatex)")
        return 0
    for stem, body in FIXTURES.items():
        rc, out, td = run_frag(stem, body)
        check(f"{stem}-rc", rc == 0, f"rc={rc}\n{out[-2000:]}")
        audit = Path(td.name) / f"{stem}.audit"
        check(f"{stem}-audit", audit.exists(), "no .audit produced")
        check(
            f"{stem}-noerr",
            "ERR " not in out,
            "\n".join(ln for ln in out.splitlines() if "ERR" in ln),
        )
        check(
            f"{stem}-clean",
            "all invariants hold" in out and "ok:" in out,
            out[-800:],
        )
    print(f"--- done, {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
