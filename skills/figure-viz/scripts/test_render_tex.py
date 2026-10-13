#!/usr/bin/env python3
"""test_render_tex.py — render_tex.py 的单元与集成测试。

    python3 scripts/test_render_tex.py          # 单元测试
    python3 scripts/test_render_tex.py --xe     # 加跑 xelatex 集成冒烟

单元部分覆盖纯函数：TEXINPUTS 构造（尾冒号保 kpathsea 默认路径）、
连接器正则（含注释剥离）、wire 行计数。集成部分（--xe）真实编译两个
frag：带 vaudit+连接器（应报无 \\vzwire 提示）与不带埋点（应报未启用
审计），并核对 pdf/png/透明png/svg 四件产出。
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import render_tex  # noqa: E402

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name} {detail}")


def unit():
    print("== build_texinputs ==")
    env = {}
    out = render_tex.build_texinputs(env)
    check("empty env ends with sep", out.endswith(os.pathsep), out)
    # `.` 必须保持最前（srcdir 遮蔽守卫，见 build_texinputs docstring）
    check(
        "empty env prepends . then assets",
        out.startswith(f".{os.pathsep}{render_tex.SKILL_DIR}/assets/tikz{os.pathsep}"),
        out,
    )

    env = {"TEXINPUTS": "/user/dir"}  # 无结尾冒号：旧的整树替换场景
    out = render_tex.build_texinputs(env)
    check("prev kept", "/user/dir" in out, out)
    check("trailing sep restores defaults", out.endswith(os.pathsep), out)

    env = {"TEXINPUTS": "/user/dir:"}
    out = render_tex.build_texinputs(env)
    check(
        "already-trailing sep not doubled",
        out.endswith(":") and not out.endswith("::"),
        out,
    )

    print("== CONNECTOR_RE / uncommented ==")
    src = r"""
\draw[varr] (a) -- (b);
\draw[varr, draw=vcoral] (c) -| (d);
\draw[lead] (e) -- (1,2);
\draw[inh] (f) -- (g);
\draw[black!40] (h) -- (i);   % plain stroke, not a connector
% \draw[varr] (j) -- (k);     % commented out
"""
    hits = render_tex.CONNECTOR_RE.findall(render_tex.uncommented(src))
    check("4 real connectors found", len(hits) == 4, hits)
    check(
        "comment stripped",
        render_tex.CONNECTOR_RE.search(
            render_tex.uncommented("% \\draw[varr] (j)--(k);")
        )
        is None,
    )
    check(
        "uncommented still catches",
        render_tex.CONNECTOR_RE.search(
            render_tex.uncommented("\\draw[varr] (j)--(k);")
        ),
    )

    print("== wire_rows ==")
    with tempfile.TemporaryDirectory(prefix="fv-t-") as td:
        a = Path(td) / "x.audit"
        a.write_text(
            "node a | 0pt 0pt 1pt 1pt | class=c\n"
            "wire ab | 0 0 1 1 | endpoint=a,b\n"
            "region r | 0pt 0pt 2pt 2pt |\n"
        )
        check("one wire row", render_tex.wire_rows(a) == 1)
        a.write_text("node a | 0pt 0pt 1pt 1pt |\n")
        check("zero wire rows", render_tex.wire_rows(a) == 0)

    print("== cjk_unsupported ==")
    plain = "\\documentclass{article}\n\\begin{document}\nhello\n\\end{document}"
    check("ascii-only clean", not render_tex.cjk_unsupported(plain))
    ctex = "\\documentclass[UTF8]{ctexart}\n\\begin{document}\n阶段\n\\end{document}"
    check("ctexart covers CJK", not render_tex.cjk_unsupported(ctex))
    usepkg = (
        "\\documentclass{article}\n\\usepackage{xeCJK}\n"
        "\\begin{document}\n阶段\n\\end{document}"
    )
    check("xeCJK covers CJK", not render_tex.cjk_unsupported(usepkg))
    setcjk = (
        "\\documentclass{article}\n\\usepackage{fontspec}\n"
        "\\setCJKmainfont{Noto Sans CJK SC}\n"
        "\\begin{document}\n阶段\n\\end{document}"
    )
    check("setCJKmainfont covers CJK", not render_tex.cjk_unsupported(setcjk))
    bare = "\\documentclass{article}\n\\begin{document}\n阶段 $x$\n\\end{document}"
    check("CJK without font flagged", render_tex.cjk_unsupported(bare))
    punct = "\\documentclass{article}\n\\begin{document}\na。、b\n\\end{document}"
    check("CJK punctuation flagged", render_tex.cjk_unsupported(punct))
    fw = "\\documentclass{article}\n\\begin{document}\nprice：\\$5\n\\end{document}"
    check("fullwidth colon flagged", render_tex.cjk_unsupported(fw))
    cmt = (
        "\\documentclass{article}\n\\begin{document}\n"
        "% 注释里的汉字不算\nhello\n\\end{document}"
    )
    check("commented CJK ignored", not render_tex.cjk_unsupported(cmt))
    post = (
        "\\documentclass{article}\n\\begin{document}\nhello\n\\end{document}\n% 阶段\n"
    )
    check("trailing comment ignored", not render_tex.cjk_unsupported(post))


FRAG_AUDIT = r"""\input{vizstyle}
\input{vizaudit}
\begin{tikzpicture}
\node[model, fill=vteal!14, vaudit={class=m}] (a) at (0,0) {A};
\node[model, fill=vviolet!14, vaudit={class=m}] (b) at (3,0) {B};
\draw[varr] (a) -- (b);
\end{tikzpicture}
"""

FRAG_PLAIN = r"""\input{vizstyle}
\begin{tikzpicture}
\node[model, fill=vteal!14] (a) at (0,0) {A};
\node[msq=vorange] (s) at (2,0) {};
\node[gcell, minimum size=0.5cm] (g) at (4,0) {};
\end{tikzpicture}
"""


def xe():
    if shutil.which("xelatex") is None:
        print("== xe ==\nskip: xelatex not found")
        return
    print("== xe integration ==")
    with tempfile.TemporaryDirectory(prefix="fv-txe-") as td:
        td = Path(td)

        # 1) 带 vaudit 与 connector 但无 \vzwire 的 frag -> coverage 提示
        src = td / "aud.tex"
        src.write_text(FRAG_AUDIT)
        out = td / "o1"
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_tex.py"),
                str(src),
                "--frag",
                "--outdir",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        check("aud compiles", p.returncode == 0, p.stderr[-800:])
        check("audit file produced", (out / "aud.audit").exists())
        check(
            "unwired-connector hint",
            "warn audit:" in p.stderr and "vzwire" in p.stderr,
            p.stderr,
        )
        for suffix in (".pdf", ".png", ".transparent.png", ".svg"):
            check(f"aud{suffix} produced", (out / f"aud{suffix}").exists())
        atxt = out / "aud.audit.txt"
        check("audit.txt persisted", atxt.exists())
        if atxt.exists():
            body = atxt.read_text()
            check(
                "audit.txt verdict lines",
                body.startswith("tex: ")
                and "xelatex: ok" in body
                and "check_audit:" in body
                and "check_coverage:" in body
                and "check_readback:" in body,
                body,
            )

        # 2) 不带 vizaudit 的 standalone 文档 -> no-audit 哨兵。
        # frag 路径总会经 FRAG_PREAMBLE 加载 vizaudit，所以只有 \input
        # vizstyle 但不 \input vizaudit 的裸 .tex 才能走到哨兵分支。
        src2 = td / "plain.tex"
        src2.write_text(
            "\\documentclass[border=8pt]{standalone}\n"
            "\\usepackage{tikz}\n"
            "\\usetikzlibrary{arrows.meta,positioning,calc}\n"
            "\\input{vizstyle}\n"
            "\\begin{document}\n"
            + FRAG_PLAIN.replace("\\input{vizstyle}\n", "")
            + "\n\\end{document}\n"
        )
        out2 = td / "o2"
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_tex.py"),
                str(src2),
                "--outdir",
                str(out2),
            ],
            capture_output=True,
            text=True,
        )
        check("plain compiles", p.returncode == 0, p.stderr[-800:])
        check(
            "no-audit sentinel",
            "warn audit: 未启用 vaudit 埋点，审计未运行" in p.stderr,
            p.stderr,
        )
        check("plain exit 0 (warn never fails)", p.returncode == 0)

        # 2b) .frag 后缀隐含 --frag——直接调 render_tex.py 必须包住
        # 裸片段而不是当 standalone 编译
        src2b = td / "auto.frag"
        src2b.write_text(FRAG_PLAIN)
        out2b = td / "o2b"
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_tex.py"),
                str(src2b),
                "--outdir",
                str(out2b),
                "--no-svg",
                "--no-png",
            ],
            capture_output=True,
            text=True,
        )
        check(".frag auto-wraps", p.returncode == 0, p.stderr[-800:])
        check(".frag pdf", (out2b / "auto.pdf").exists())
        check(
            ".frag audit.txt written",
            (out2b / "auto.audit.txt").exists(),
        )

        # 2c) 含 CJK 但无 CJK 字体栈的 standalone -> 仅告警的预检
        src2c = td / "cjk.tex"
        src2c.write_text(
            "\\documentclass{standalone}\n\\usepackage{tikz}\n"
            "\\begin{document}\n"
            "\\begin{tikzpicture}\n"
            "\\node[draw] (a) at (0,0) {阶段};\n"
            "\\end{tikzpicture}\n\\end{document}\n"
        )
        out2c = td / "o2c"
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_tex.py"),
                str(src2c),
                "--outdir",
                str(out2c),
                "--no-svg",
                "--no-png",
            ],
            capture_output=True,
            text=True,
        )
        check("cjk-no-ctex warns", "warn cjk-no-ctex:" in p.stderr, p.stderr)
        check(
            "cjk-no-ctex warn-only",
            p.returncode == 0,
            f"rc={p.returncode} {p.stderr[-400:]}",
        )

        # 3) 敌意 TEXINPUTS（无结尾冒号）仍须编译通过
        src3 = td / "hostile.frag"
        src3.write_text(FRAG_PLAIN)
        env = dict(os.environ, TEXINPUTS="/nonexistent/userdir")
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_tex.py"),
                str(src3),
                "--frag",
                "--outdir",
                str(td / "o3"),
                "--no-svg",
                "--no-png",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        check("hostile TEXINPUTS still compiles", p.returncode == 0, p.stderr[-800:])

        # 4) svg 须是真文本（dvisvgm）或至少是矢量路径（pdftocairo
        # 回退——dvisvgm 丢弃 pgf 的 pdf: specials，所以纯路径 svg
        # 是正确结果而非失败）
        svg = (
            (out / "aud.svg").read_text(errors="ignore")
            if (out / "aud.svg").exists()
            else ""
        )
        has_ink = any(
            tag in svg
            for tag in (
                "<text",
                "<path",
                "<use",
                "<image",
                "<line",
                "<rect",
                "<circle",
                "<ellipse",
                "<polygon",
                "<polyline",
            )
        )
        check(
            "svg has text or vector ink",
            svg != "" and has_ink,
            "no text elems nor drawing paths",
        )


def main():
    unit()
    if "--xe" in sys.argv:
        xe()
    if fails:
        print(f"== {len(fails)} FAIL ==")
        return 1
    print("== all pass ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
