#!/usr/bin/env python3
r"""render_tex.py — 把 standalone .tex 图编译成 PDF + PNG + SVG。

用法：
    render_tex.py FIG.tex [--frag] [--dpi N] [--outdir DIR] [--no-svg]
                          [--no-png] [--no-check] [--no-coverage]
                          [--no-readback] [--overlay]

- 完整 standalone 文档：原样编译
- --frag：把片段（tikzpicture / minipage 片段）包进标准导言区再编译
  ——导言区已加载 vizstyle+vizaudit，片段原样即可被审计；frag 正文里
  多余的 \input{vizaudit} 经 vizaudit 的防重入守卫是无害空操作。
  `.frag` 后缀隐含 --frag（与 render.py 同一分发规则）
- 预检：standalone 源含 CJK 字符而导言区未加载 CJK 字体栈
  （ctex/xeCJK/\setCJK...）时发一条 warn-only `warn cjk-no-ctex:`——
  xelatex 会静默丢掉每个汉字字形
- <stem>.audit.txt 在产物旁持久化判定摘要（输入路径 + 每个检查器
  一行），编译失败路径也会写
- TEXINPUTS 追加本 skill 的 assets/tikz 目录，图里可直接
  `\input{vizstyle}` / `\input{vizaudit}` 无需拷文件。源文件自身
  目录最先被搜，所以相对路径引用的资源——`\addplot
  table{data.csv}`、`\input{sub.tex}`、`\includegraphics{img.png}`
  ——即使编译在 tempdir 里跑也能解析
- 编译产出 FIG.audit（vizaudit 埋点）时自动跑 check_audit.py，除非
  --no-check；含 connector（\draw[varr/lead/inh]）却无 \vzwire
  锚点的图会得到一条 coverage 提示
- --no-coverage：跳过 check_coverage.py（tex 源的「未审计绘制对象」
  静态扫描）；--no-readback：跳过 check_readback_tex.py（pdftotext
  词盒 vs 已审计 box）。两者都仅 warn，从不改变退出码。
- --overlay：额外编译一遍，把每个审计锚点（已审计 box 的虚线框 +
  名签、wire 的虚线折线）画进 FIG.overlay.pdf——调试产物，不影响
  退出码。

产物默认落在源文件旁：FIG.pdf、FIG.png（白底）、
FIG.transparent.png、FIG.svg、FIG.audit、FIG.audit.txt
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

FRAG_PREAMBLE = r"""\documentclass[border=8pt]{standalone}
\usepackage[UTF8,fontset=fandol]{ctex}
\usepackage{amsmath,amssymb}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{arrows.meta,positioning,calc,decorations.pathreplacing,fit,matrix,graphs}
\pgfdeclarelayer{bg}
\pgfsetlayers{bg,main}
\input{vizstyle}
\input{vizaudit}
\begin{document}
"""
FRAG_EPILOGUE = "\n\\end{document}\n"

# \vzwire 能为 WIRE-CROSS/CROWD 导出几何的 connector 样式
CONNECTOR_RE = re.compile(
    r"\\draw\s*\[[^\]\n]*"
    r"\b(?:varr|lead|inh|nskip|nskipe|lifeline|snkeep|snret|snghost)\b"
)
COMMENT_RE = re.compile(r"(?<!\\)%.*")

# CJK preflight: 统一表意文字 + 扩展A + 兼容表意 + CJK 标点 + 全角字符。
# standalone 源含这些码位而导言缺 CJK 字体栈时，xelatex 静默吞字形——
# pdf/png/svg/audit 全链路 exit 0 但汉字全丢，只能靠源扫描拦住。
CJK_RE = re.compile(
    "[㐀-䶿"  # 扩展 A 区
    "一-鿿"  # 统一表意文字
    "豈-﫿"  # 兼容表意文字
    "　-〿"  # CJK 符号与标点
    "！-｠￠-￦]"  # 全角形式（不含半角假名/谚文）
)
# 导言区任一标记即视为已配 CJK 字体栈：ctex 宏包/文类、xeCJK、\setCJKmainfont 族
CJK_FONT_RE = re.compile(r"ctex|xeCJK|setCJK")


def run(cmd, cwd, log, env=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    log.write(proc.stdout + proc.stderr)
    return proc.returncode


def build_texinputs(env: dict, srcdir: Path | None = None) -> str:
    r"""把源目录与 assets/tikz 前插进 TEXINPUTS，末尾恒带路径分隔符。

    编译在 TemporaryDirectory 里跑。`.` 必须保持最前：--frag 把包装
    副本写成工作目录里的 `<stem>.tex`，没有 `.` 时 srcdir 里同名
    原始源会遮蔽它（kpsewhich 经 TEXINPUTS 解析主输入）。srcdir 排
    第二，于是同目录资源——`\addplot table{data.csv}`、
    `\input{sub.tex}`、`\includegraphics{img.png}`——都能解析。
    用 `dir` 而非 `dir//`——递归搜索会让裸文件名静默命中嵌套子目录
    里的同名文件而不是报错，还在大源码目录里每次查找扑空都强制
    走一遍树。

    kpathsea 会在开头的或结尾的 ':'（或 '::'）处重新插入内置默认
    搜索路径。没有结尾分隔符时，调用方 TEXINPUTS 形如 'foo'（无冒号）
    会替换掉整棵系统 texmf 树，xelatex 连 article.cls 都找不到。
    """
    parts = ["."] + ([str(srcdir)] if srcdir else []) + [f"{SKILL_DIR}/assets/tikz"]
    prev = env.get("TEXINPUTS", "")
    if prev:
        parts.append(prev)
    texinputs = os.pathsep.join(parts)
    if not texinputs.endswith(os.pathsep):
        texinputs += os.pathsep
    return texinputs


def uncommented(tex: str) -> str:
    """剥掉 % 注释，让启发式扫描无视注释掉的 draw。"""
    return "\n".join(COMMENT_RE.sub("", ln) for ln in tex.splitlines())


def cjk_unsupported(tex: str) -> bool:
    """standalone 源含 CJK 字符但导言区无 ctex/xeCJK/setCJK 字体栈。

    只供 standalone 路径使用——--frag/.frag 走 FRAG_PREAMBLE（自带 ctex）。
    导言区取 \begin{document} 之前；找不到 \begin{document} 的残源按全文
    当导言扫（反正编译会先挂）。注释里的汉字不算内容。
    """
    body = uncommented(tex)
    if not CJK_RE.search(body):
        return False
    preamble = body.split(r"\begin{document}", 1)[0]
    return CJK_FONT_RE.search(preamble) is None


def wire_rows(audit: Path) -> int:
    return sum(1 for ln in audit.read_text().splitlines() if ln.startswith("wire "))


def audit_lines(out: str) -> int:
    """统计 'ERR <rule>:'/'warn <rule>:' 行数（允许缩进）。"""
    return sum(1 for ln in out.splitlines() if ln.strip().startswith(("ERR ", "warn ")))


def run_checker(
    script: str, argv: list[str], log=None, sink: list[str] | None = None
) -> tuple[int, int]:
    """跑一个 scripts/ 检查器，透传其输出，返回 (rc, finding_count)。

    sink（list）逐字收集检查器的 ERR/warn 行，供持久化
    <stem>.audit.txt 报告。
    """
    proc = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / script), *argv],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if log is not None:
        log.write(proc.stdout + proc.stderr)
    if sink is not None:
        sink.extend(
            ln
            for ln in (proc.stdout + proc.stderr).splitlines()
            if ln.strip().startswith(("ERR ", "warn "))
        )
    return proc.returncode, audit_lines(proc.stdout) + audit_lines(proc.stderr)


def checker_report(report: list[str], name: str, findings: list[str], rc: int):
    """每个检查器一条判定行 + 其 findings 行（已缩进）。"""
    nerr = sum(1 for ln in findings if ln.strip().startswith("ERR "))
    nwarn = len(findings) - nerr
    if rc == 2:
        verdict = f"{name}: failed (rc=2)"
    elif not findings and rc == 0:
        verdict = f"{name}: clean"
    else:
        parts = ([f"{nerr} error(s)"] if nerr else []) + (
            [f"{nwarn} warning(s)"] if nwarn else []
        )
        # rc!=0 但解析出 0 条 finding = 检查器在报告前崩了
        verdict = (
            f"{name}: " + ", ".join(parts) if parts else f"{name}: failed (rc={rc})"
        )
    report.append(verdict)
    report.extend(findings)


def write_audit_report(outdir: Path, stem: str, report: list[str]):
    (outdir / f"{stem}.audit.txt").write_text("\n".join(report) + "\n")


def compile_tex(tex: Path, workdir: Path, env: dict, log, passes=2) -> bool:
    for attempt in range(passes):  # pgfplots 图例/remember-picture 要两遍
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
            cwd=workdir,
            capture_output=True,
            text=True,
            env=env,
        )
        log.write(proc.stdout[-4000:] + proc.stderr)
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr)[-2500:]
            print(f"FAIL xelatex (pass {attempt + 1}):\n{tail}", file=sys.stderr)
            return False
    return True


def export_transparent_png(pdf: Path, stem: str, dpi: int, work, log) -> Path | None:
    """经 pdftocairo 真 alpha 通道导透明 PNG。

    取代旧的 magick '-fuzz 2% -transparent white' 通路——它会在抗锯齿
    边上留白边；pdftocairo 缺席时 magick 仅作降级兜底。
    """
    base = work / "transp"
    if shutil.which("pdftocairo"):
        rc = run(
            [
                "pdftocairo",
                "-png",
                "-transp",
                "-r",
                str(dpi),
                "-singlefile",
                str(pdf),
                str(base),
            ],
            work,
            log,
        )
        produced = base.with_suffix(".png")
        if rc == 0 and produced.exists():
            return produced
    if shutil.which("magick"):
        white = work / f"{stem}.png" if (work / f"{stem}.png").exists() else None
        if white is not None:
            log.write(
                "note: pdftocairo missing; magick fuzz fallback has white-edge artifacts\n"
            )
            rc = run(
                [
                    "magick",
                    str(white),
                    "-fuzz",
                    "2%",
                    "-transparent",
                    "white",
                    str(base.with_suffix(".png")),
                ],
                work,
                log,
            )
            produced = base.with_suffix(".png")
            if rc == 0 and produced.exists():
                return produced
    return None


def svg_has_ink(svg: Path) -> bool:
    """真图 svg 必须含绘制元素；dvisvgm 丢弃 pgf 的 pdf: specials
    时，幸存 svg 充其量只剩零散 <text>——光查文件存在分不清好 svg
    和空壳。"""
    try:
        body = svg.read_text(errors="replace")
    except OSError:
        return False
    return any(
        tag in body
        for tag in (
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


def export_svg(pdf: Path, texsrc: Path, work: Path, stem: str, env, log) -> Path | None:
    """带真文本的 SVG：优先 dvisvgm 走 xelatex 的 .xdv，否则 pdftocairo。

    dvisvgm --font-format 内嵌 WOFF/WOFF2 web 字体，<text> 在浏览器里
    忠实渲染。'dvisvgm --pdf' 有意跳过：它需要 ghostscript <10.01 或
    mutool，而当前发行版大多带 gs>=10.01。.xdv 通路多付一遍
    'xelatex -no-pdf' 但到处可用——除了它无法解释 pgf 的 pdf: page
    specials（'WARNING: N PDF specials ignored'），会丢光所有绘制路径
    却仍 exit 0；检测到就回退。pdftocairo 的 svg 是矢量化路径——永远
    正确，但文本不可编辑。
    """
    svg = work / f"{stem}.svg"
    if shutil.which("dvisvgm"):
        xdv_rc = run(
            [
                "xelatex",
                "-no-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                texsrc.name,
            ],
            work,
            log,
            env=env,
        )
        xdv = work / f"{stem}.xdv"
        if xdv_rc == 0 and xdv.exists():
            for fmt in ("woff2", "woff"):
                proc = subprocess.run(
                    ["dvisvgm", f"--font-format={fmt}", str(xdv), "-o", str(svg)],
                    cwd=work,
                    capture_output=True,
                    text=True,
                )
                log.write(proc.stdout + proc.stderr)
                out = proc.stdout + proc.stderr
                dropped = "specials ignored" in out
                if (
                    proc.returncode == 0
                    and svg.exists()
                    and not dropped
                    and svg_has_ink(svg)
                ):
                    return svg
                if svg.exists():
                    svg.unlink()  # 坏 svg 不得掩盖兜底通路
                if dropped:
                    log.write(
                        f"note: dvisvgm ({fmt}) dropped pgf pdf: specials — "
                        "svg would be empty; falling back to pdftocairo\n"
                    )
    rc = run(["pdftocairo", "-svg", str(pdf), str(svg)], work, log)
    if rc == 0 and svg.exists():
        return svg
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tex", type=Path)
    ap.add_argument(
        "--frag",
        action="store_true",
        help="wrap fragment in standard preamble (implied by .frag suffix)",
    )
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--outdir", type=Path)
    ap.add_argument("--no-svg", action="store_true")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-check", action="store_true", help="skip audit check")
    ap.add_argument(
        "--no-coverage",
        action="store_true",
        help="skip static coverage scan of unaudited drawn objects",
    )
    ap.add_argument(
        "--no-readback",
        action="store_true",
        help="skip pdftotext readback against audited boxes",
    )
    ap.add_argument(
        "--overlay",
        action="store_true",
        help="extra pass painting audit anchors -> <stem>.overlay.pdf",
    )
    args = ap.parse_args()

    src = args.tex.resolve()
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2

    # .frag 后缀隐含 --frag —— 与 render.py 的分发规则一致，直接调用
    # render_tex.py x.frag 不再把裸片段当整文档编译
    frag = args.frag or src.suffix.lower() == ".frag"

    outdir = (args.outdir or src.parent).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stem = src.stem

    env = dict(os.environ)
    env["TEXINPUTS"] = build_texinputs(env, src.parent)

    warned = False
    self_warns = []

    def warn_s(msg):
        nonlocal warned
        warned = True
        self_warns.append(msg)
        print(msg, file=sys.stderr)

    report = [f"tex: {src}"]

    # CJK preflight：standalone 源含汉字但导言无 CJK 字体栈 → xelatex 静默
    # 吞字形且三件套全 exit 0。frag 由 FRAG_PREAMBLE 自带 ctex，不查。
    if not frag and cjk_unsupported(src.read_text()):
        warn_s(
            "warn cjk-no-ctex: 源含 CJK 字符但导言区无 ctex/xeCJK/setCJK，"
            "xelatex 会静默吞掉汉字字形"
        )

    audit_produced = False
    with tempfile.TemporaryDirectory(prefix="figviz-") as td:
        work = Path(td)
        texsrc = work / f"{stem}.tex"
        if frag:
            texsrc.write_text(FRAG_PREAMBLE + src.read_text() + FRAG_EPILOGUE)
        else:
            shutil.copy(src, texsrc)

        with open(work / "build.log", "w") as log:
            ok = compile_tex(texsrc, work, env, log)
            if not ok:
                log.flush()
                shutil.copy(work / "build.log", outdir / f"{stem}.log")
                report.append(f"xelatex: failed (see {stem}.log)")
                if self_warns:
                    report.append(f"render_tex: {len(self_warns)} warning(s)")
                    report.extend("  " + w for w in self_warns)
                write_audit_report(outdir, stem, report)
                print(f"full log: {outdir / (stem + '.log')}", file=sys.stderr)
                return 1

            pdf = work / f"{stem}.pdf"
            shutil.copy(pdf, outdir / f"{stem}.pdf")
            # 上一次失败运行留下的 log 会被读成新的失败产物——成功
            # 必须清掉它（同 .audit）
            stale_log = outdir / f"{stem}.log"
            if stale_log.exists():
                stale_log.unlink()

            if not args.no_png:
                run(
                    [
                        "pdftoppm",
                        "-png",
                        "-r",
                        str(args.dpi),
                        "-singlefile",
                        str(pdf),
                        str(work / stem),
                    ],
                    work,
                    log,
                )
                shutil.copy(work / f"{stem}.png", outdir / f"{stem}.png")
                transp = export_transparent_png(pdf, stem, args.dpi, work, log)
                if transp is not None:
                    shutil.copy(transp, outdir / f"{stem}.transparent.png")
                else:
                    warn_s("warn export: transparent png 失败（pdftocairo 不可用）")

            if not args.no_svg:
                svg = export_svg(pdf, texsrc, work, stem, env, log)
                if svg is not None:
                    shutil.copy(svg, outdir / f"{stem}.svg")
                else:
                    warn_s("warn export: svg export failed")

            audit = work / f"{stem}.audit"
            if audit.exists():
                audit_produced = True
                shutil.copy(audit, outdir / f"{stem}.audit")
                # coverage 提示：有 connector 但没导出 \vzwire 锚点，
                # WIRE-CROSS/CROWD 无从检查
                if (
                    CONNECTOR_RE.search(uncommented(texsrc.read_text()))
                    and wire_rows(audit) == 0
                ):
                    warn_s(
                        "warn audit: 源文件含连接器样式（varr/lead/inh/nskip/lifeline/"
                        "snkeep 等）但无 \\vzwire 埋点，WIRE-CROSS 未检查"
                    )
            else:
                warn_s("warn audit: 未启用 vaudit 埋点，审计未运行")
                # 清掉上次运行留下的 audit，免得它拿已不存在的几何
                # 再校验
                stale = outdir / f"{stem}.audit"
                if stale.exists():
                    stale.unlink()

            # 调试覆盖层：预注入 \vzoverlaytrue 重编译，vizaudit 里被
            # 守卫的 \newif 会看到旗标已为真。旗标必须在 vizaudit 被
            # \input 之前置位——包装文件是可靠载体（已验证：命令行
            # input-line 注入会踩目标导言区里 e-TeX 条件解析的坑）。
            if args.overlay:
                wrap = work / f"{stem}.overlay.tex"
                wrap.write_text(
                    "\\newif\\ifvzoverlay\\vzoverlaytrue\\input{" + texsrc.name + "}\n"
                )
                opdf = work / f"{stem}.overlay.pdf"
                if compile_tex(wrap, work, env, log) and opdf.exists():
                    shutil.copy(opdf, outdir / opdf.name)
                else:
                    warn_s("warn overlay: 覆盖层编译失败（正文产物不受影响）")

    outs = sorted(
        p.name
        for p in outdir.glob(f"{stem}.*")
        if p.suffix in {".pdf", ".png", ".svg", ".audit"}
    )

    errs = 0
    audit_file = outdir / f"{stem}.audit"
    report.append("xelatex: ok")
    if self_warns:
        report.append(f"render_tex: {len(self_warns)} warning(s)")
        report.extend("  " + w for w in self_warns)
    # 只查本次编译产出的 audit——上次运行的残留不得再校验（其几何
    # 已与源码不符）
    if audit_produced and audit_file.exists() and not args.no_check:
        findings = []
        errs, found = run_checker("check_audit.py", [str(audit_file)], sink=findings)
        warned = warned or found > 0 or errs != 0
        checker_report(report, "check_audit", findings, errs)
    elif args.no_check:
        report.append("check_audit: skipped (--no-check)")
    else:
        report.append("check_audit: skipped (no .audit produced)")
    # 静态源扫描：不带审计锚点的绘制对象（仅 warn）
    if not args.no_coverage:
        findings = []
        rc, found = run_checker("check_coverage.py", [str(src)], sink=findings)
        warned = warned or found > 0 or rc == 2
        checker_report(report, "check_coverage", findings, rc)
    else:
        report.append("check_coverage: skipped (--no-coverage)")
    # 渲染词回读对照已审计 box（仅 warn）；无 .audit 时仍跑
    # outside-page 检查
    if not args.no_readback:
        rb_argv = [str(outdir / f"{stem}.pdf")]
        if audit_file.exists():
            rb_argv.append(str(audit_file))
        findings = []
        rc, found = run_checker("check_readback_tex.py", rb_argv, sink=findings)
        warned = warned or found > 0 or rc == 2
        checker_report(report, "check_readback", findings, rc)
    else:
        report.append("check_readback: skipped (--no-readback)")
    # 与 mpl 侧 <stem>.audit.txt 对齐：产物旁永远能查到本次各检查器结论，
    # 包括 checker 全跳过的运行
    write_audit_report(outdir, stem, report)
    # 'ok:' 只表示全程干净；有 error 或任何 warn 时产物仍在，改列 artifacts:
    print(("ok:" if not errs and not warned else "artifacts:"), ", ".join(outs))
    return errs


if __name__ == "__main__":
    sys.exit(main())
