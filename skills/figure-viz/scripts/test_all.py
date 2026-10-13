#!/usr/bin/env python3
"""test_all.py — figure-viz 全轨自检入口。

    python3 scripts/test_all.py [--tikz]

本脚本自身只需 stdlib；依赖 matplotlib 的步骤一律经
``uv run --no-project --with matplotlib --with numpy python SCRIPT``
起子进程（--no-project 防 cwd 所在工程的 pyproject 劫持解释器解析）。

步骤：
  palette    check_palette.py   两轨调色板 hex 一致性（纯 stdlib）
  agg        test_agg.py        fvagg 聚合 helper：group-by/csv round-trip（纯 stdlib）
  selftest   selftest.py        fv.audit 每条规则一个违规图 + 干净图型
  spec       test_spec.py       fvspec 引擎：示例回归/SpecError/lint/polar
  spec-atoms test_spec_atoms.py  探针驱动 spec 原子补全与 lint 新面
  spec-kde   test_spec_kde.py   kde 系列 + scatter jitter + _heat_cmap 薄壳
  spec-image test_spec_image.py image 图版/heat 底图系列与 badge/extent/cmap
  spec-field test_spec_field.py contour/quiver 场族系列与 occluded-by-heat 扩展
  spec-matrix test_spec_matrix.py layout matrix/spans + rows/cols 边默认与 bind
  spec-waterfall test_spec_waterfall.py bar 瀑布 bottom/connect/labels 三件套
  spec-sankey test_spec_sankey.py sankey 守恒流向图系列
  spec-sig   test_spec_sig.py   sig 显著性括号 + bar connect.label 幽灵条目
  render     test_render.py     render.py 分发 + render_mpl 审计输出契约
  render-tex test_render_tex.py render_tex 纯函数单元测试（纯 stdlib；--xe 集成不走全量）
  audit-rules test_audit_rules.py fvstyle.audit 新规则隔离测试（mpl）
  audit-mpl2 test_audit_mpl2.py 审计盲区补规则：text-overlaps-data/旋转文本/cmap artist（mpl）
  audit-tikz test_audit_tikz.py .audit fixtures 正反例 + xelatex 冒烟（纯 stdlib）
  tikz-recipes test_tikz_recipes.py  vizstyle 配方族四 fixture 真实编译冒烟（纯 stdlib）
  vlm-judge  test_vlm_judge.py  语义评审单结构/intent 抽取/退出码契约（纯 stdlib）
  oracle     test_oracle_codegen.py  布局 oracle 两后端 + codegen 骨架回归（纯 stdlib）
  oracle-tree test_oracle_tree.py    tidy-tree 森林布局回归（纯 stdlib）
  solid      test_solid.py      solid 伪 3D 骨架编译 + 审计正反例（纯 stdlib）
  demos      examples/*_demo.py imperative 模板冒烟：跑通且无审计行
  tikz       render_tex --frag  TikZ 轨渲染冒烟（--tikz 才跑，需 xelatex）

任何一步失败 → 退出 1。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
EXAMPLES = SCRIPTS / "examples"

UV_MPL = [
    "uv",
    "run",
    "--no-project",
    "--with",
    "matplotlib",
    "--with",
    "numpy",
    "python",
]

# (name, script, needs_mpl) — mpl 步骤经 uv 起隔离解释器，stdlib 步骤直接跑
STEPS = [
    ("palette", "check_palette.py", False),
    ("agg", "test_agg.py", False),
    ("selftest", "selftest.py", True),
    ("spec", "test_spec.py", True),
    ("spec-atoms", "test_spec_atoms.py", True),
    ("spec-kde", "test_spec_kde.py", True),
    ("spec-image", "test_spec_image.py", True),
    ("spec-field", "test_spec_field.py", True),
    ("spec-matrix", "test_spec_matrix.py", True),
    ("spec-waterfall", "test_spec_waterfall.py", True),
    ("spec-sankey", "test_spec_sankey.py", True),
    ("spec-sig", "test_spec_sig.py", True),
    ("render", "test_render.py", True),
    ("render-tex", "test_render_tex.py", False),
    ("audit-rules", "test_audit_rules.py", True),
    ("audit-mpl2", "test_audit_mpl2.py", True),
    ("audit-tikz", "test_audit_tikz.py", False),
    ("tikz-recipes", "test_tikz_recipes.py", False),
    ("vlm-judge", "test_vlm_judge.py", False),
    ("oracle", "test_oracle_codegen.py", False),
    ("oracle-tree", "test_oracle_tree.py", False),
    ("solid", "test_solid.py", False),
]

TIKZ_FRAG = r"""\input{vizstyle}
\begin{tikzpicture}
\fill[vteal] (0,0) rectangle (1,0.6);
\fill[vgold] (1.15,0) rectangle (2.15,0.6);
\end{tikzpicture}
"""


def run(name, argv, **kw):
    print(f"===== {name} =====", flush=True)
    proc = subprocess.run(argv, **kw)
    return proc.returncode


def script_argv(script, needs_mpl):
    if needs_mpl:
        return [*UV_MPL, str(SCRIPTS / script)]
    return [sys.executable, str(SCRIPTS / script)]


def demos() -> int:
    """imperative 模板冒烟：每个 *_demo.py 在 uv 下跑通且不产生审计行。

    cwd 放临时目录：demo 的 fv.save 产物不污染 examples/。
    审计行是统一格式 'ERR <rule>: msg' / 'warn <rule>: msg'——demo 作为
    模板要求全干净，两种严重度出现即 FAIL（demo 自身也会因 ERR 非零退出）。
    """
    scripts = sorted(EXAMPLES.glob("*_demo.py"))
    if not scripts:
        print("===== demos =====\ndemos FAIL: no *_demo.py found")
        return 1
    fails = 0
    with tempfile.TemporaryDirectory(prefix="fv-demos-") as td:
        for s in scripts:
            print(f"===== demo {s.name} =====", flush=True)
            proc = subprocess.run(
                [*UV_MPL, str(s)],
                cwd=td,
                capture_output=True,
                text=True,
            )
            audits = [
                line
                for line in (proc.stdout + proc.stderr).splitlines()
                if line.startswith(("ERR ", "warn "))
            ]
            if proc.returncode != 0:
                fails += 1
                print(proc.stdout + proc.stderr)
                print(f"demo {s.name} FAIL: exit {proc.returncode}")
            elif audits:
                fails += 1
                print("\n".join(audits))
                print(f"demo {s.name} FAIL: {len(audits)} audit lines")
            else:
                print(f"demo {s.name} PASS")
    return 1 if fails else 0


def tikz_smoke() -> int:
    if shutil.which("xelatex") is None:
        print("===== tikz =====\nskip: xelatex not found")
        return 0
    with tempfile.TemporaryDirectory(prefix="fv-tikz-") as td:
        frag = Path(td) / "frag.tex"
        frag.write_text(TIKZ_FRAG)
        outdir = Path(td) / "out"
        rc = run(
            "tikz",
            [
                sys.executable,
                str(SCRIPTS / "render_tex.py"),
                str(frag),
                "--frag",
                "--outdir",
                str(outdir),
            ],
        )
        if rc != 0:
            return rc
        got = {p.suffix for p in outdir.glob("frag.*")}
        missing = {".pdf", ".png", ".svg"} - got
        if missing:
            print(f"tikz FAIL: missing {sorted(missing)}")
            return 1
        print("tikz PASS: pdf/png/svg produced")
        return 0


def main() -> int:
    fails = 0
    steps = 0
    for name, script, needs_mpl in STEPS:
        fails += run(name, script_argv(script, needs_mpl)) != 0
        steps += 1
    fails += demos() != 0
    steps += 1
    if "--tikz" in sys.argv:
        fails += tikz_smoke() != 0
        steps += 1
    print(f"===== {steps} steps, {fails} failed =====")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
