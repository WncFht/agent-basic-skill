#!/usr/bin/env python3
"""render.py — figure-viz 统一渲染入口：按扩展名分发到两条轨的后端 CLI。

用法：
    render.py FIG.tex   [--frag] [--dpi N] [--outdir DIR] [--no-svg] [--no-png] [--no-audit]
                        [--no-coverage] [--no-readback] [--overlay]
    render.py FIG.frag  [同上；.frag 扩展名隐含 --frag]
    render.py SPEC.json [--dpi N] [--outdir DIR] [--no-audit] [--no-readback] [--overlay]

- .tex/.frag → render_tex.py（xelatex → pdf/png/svg；产物含 .audit 时自动审计）
- .json/.spec.json → render_mpl.py（fvspec → png/svg/pdf + fvstyle 审计）
- --no-audit 两轨同义（tex 轨映射到 render_tex 的 --no-check）；
  --no-readback/--overlay 两轨各自实现、语义相近（渲染回读核对 / 调试覆盖图）；
  --frag/--no-svg/--no-png/--no-coverage 是 tex 专有旗标，喂给 .json 会报错而非静默吞掉
- 审计输出两轨同一格式：'ERR <rule>: <msg>' / 'warn <rule>: <msg>'
  （mpl 侧 spec lint 为 'warn lint:<name>: <msg>'）
- 退出码：0 干净或仅 warn；1 有 error 级审计问题；2 输入/用法错误

两个后端 CLI（render_tex.py / render_mpl.py）保持可独立调用；本脚本只做
旗标规整与转发（惰性 import——tex 轨不需要 matplotlib）。

运行方式：tex 轨 python3 render.py fig.tex；mpl 轨
          uv run --with matplotlib --with numpy python render.py fig.spec.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))  # 后端 CLI 是同目录兄弟模块

TEX_SUFFIXES = {".tex", ".frag"}
MPL_SUFFIXES = {".json"}


def _invoke(module, prog: str, argv: list[str]) -> int:
    """以显式 argv 调后端 main()。

    sys.argv 换入换出而不是猜签名：无论后端是 main() 还是
    main(argv=None)（parse_args 缺省都读 sys.argv[1:]），结果一致。
    """
    old = sys.argv
    sys.argv = [prog, *argv]
    try:
        return module.main()
    finally:
        sys.argv = old


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="render.py",
        description="figure-viz 统一渲染入口：.tex/.frag→TikZ 轨，.json→mpl spec 轨",
    )
    ap.add_argument("file", type=Path, help=".tex/.frag（TikZ）或 .json（spec）")
    ap.add_argument(
        "--frag",
        action="store_true",
        help="tex 轨：片段自动包标准 preamble（.frag 扩展名隐含）",
    )
    ap.add_argument("--dpi", type=int, help="png 导出分辨率")
    ap.add_argument("--outdir", type=Path, help="产物目录（缺省写源文件旁）")
    ap.add_argument(
        "--no-audit",
        "--no-check",
        dest="no_audit",
        action="store_true",
        help="跳过审计（tex 轨即 --no-check）",
    )
    ap.add_argument("--no-svg", action="store_true", help="tex 轨：不导出 svg")
    ap.add_argument("--no-png", action="store_true", help="tex 轨：不导出 png/透明 png")
    ap.add_argument(
        "--no-coverage",
        action="store_true",
        help="tex 轨：跳过未埋点绘制对象的静态覆盖扫描",
    )
    ap.add_argument(
        "--no-readback",
        action="store_true",
        help="跳过渲染产物回读核对（tex 轨 pdftotext / mpl 轨 rb-* 规则）",
    )
    ap.add_argument(
        "--overlay",
        action="store_true",
        help="额外产调试覆盖图（tex: <stem>.overlay.pdf；mpl: <stem>.overlay.png）",
    )
    args = ap.parse_args(argv)

    suffix = args.file.suffix.lower()
    if suffix in TEX_SUFFIXES:
        argv2 = [str(args.file)]
        if args.frag or suffix == ".frag":
            argv2.append("--frag")
        if args.dpi is not None:
            argv2 += ["--dpi", str(args.dpi)]
        if args.outdir is not None:
            argv2 += ["--outdir", str(args.outdir)]
        if args.no_audit:
            argv2.append("--no-check")
        if args.no_svg:
            argv2.append("--no-svg")
        if args.no_png:
            argv2.append("--no-png")
        if args.no_coverage:
            argv2.append("--no-coverage")
        if args.no_readback:
            argv2.append("--no-readback")
        if args.overlay:
            argv2.append("--overlay")
        import render_tex  # 惰性：tex 轨不拖 matplotlib

        return _invoke(render_tex, "render_tex.py", argv2)

    if suffix in MPL_SUFFIXES:
        bad = [
            f
            for f, given in (
                ("--frag", args.frag),
                ("--no-svg", args.no_svg),
                ("--no-png", args.no_png),
                ("--no-coverage", args.no_coverage),
            )
            if given
        ]
        if bad:
            print(
                f"render: {', '.join(bad)} only apply to .tex/.frag input, "
                f"not {args.file.name!r}",
                file=sys.stderr,
            )
            return 2
        argv2 = [str(args.file)]
        if args.dpi is not None:
            argv2 += ["--dpi", str(args.dpi)]
        if args.outdir is not None:
            argv2 += ["--outdir", str(args.outdir)]
        if args.no_audit:
            argv2.append("--no-audit")
        if args.no_readback:
            argv2.append("--no-readback")
        if args.overlay:
            argv2.append("--overlay")
        try:
            import render_mpl  # 惰性：json 轨才需要 matplotlib
        except ImportError:
            print(
                "render: matplotlib/numpy not importable in this interpreter — "
                "rerun as:\n  uv run --with matplotlib --with numpy python "
                f"{Path(__file__).name} {args.file}",
                file=sys.stderr,
            )
            return 2

        return _invoke(render_mpl, "render_mpl.py", argv2)

    print(
        f"render: cannot dispatch {args.file.name!r} — "
        f"want .tex/.frag (TikZ) or .json (spec)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
