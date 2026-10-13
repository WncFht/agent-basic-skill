#!/usr/bin/env python3
"""render_mpl.py — 把 figure spec JSON 渲染成 PNG+SVG(+PDF) 并审计。

用法：
    render_mpl.py SPEC.json [--outdir DIR] [--dpi N] [--no-audit]
                            [--no-readback] [--overlay]

- spec.output 控制路径/格式；缺省时 CLI 把 SPEC 词干的
  .png/.svg/.pdf 写到 spec 旁边（或 --outdir 里）
- 输出遵循共享的审计行约定：spec lint 打 'warn lint:<name>: <msg>'；
  fv.audit 问题打 'ERR <rule>: <msg>' 或 'warn <rule>: <msg>'
  （级别取自 fvstyle.RENDER_RULES；规则名取问题串首个 token，
  未知规则按 error 计）
- 审计含 rb-* 绘制后回读层（由 spec 自身文本喂的声明值 vs 渲染值
  标签 diff）与 print-fit 槽位检查；--no-readback 只抑制 rb-* 规则，
  --overlay 额外写带轴/图例/文本窗范围的 <stem>.overlay.png
- 存在 error 级审计项时退出 1——warn 永不失败；spec 错误退出 2；
  --no-audit 跳过 lint 打印与渲染审计；'ok:' 只在干净运行时列产物
  ——出错运行改列 'artifacts:'（文件照常落盘，但 'ok:' 绝不出现在
  ERR 之前）
- 每次运行在产物列表之前打一条审计确认行：'audit: clean'
  （0 warn 0 err）、'audit: N error(s)[, M warning(s)]' 或
  'audit: skipped (--no-audit)'——干净审计与没跑的审计可区分
- 同样的审计行也落进图产物旁的 <stem>.audit.txt（头部
  'spec: <path>' + warn/ERR 行 + 确认行）；--no-audit 写一行
  'audit: skipped (--no-audit)' 说明，而不是留下过期报告

运行方式：uv run --with matplotlib --with numpy python render_mpl.py ...
"""

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "assets" / "mpl"))

import matplotlib as mpl  # noqa: E402

mpl.use("Agg")

import fvspec  # noqa: E402
import fvstyle  # noqa: E402

DEFAULT_FORMATS = ["png", "svg", "pdf"]


def emit_audit(problems, sink=None) -> tuple[int, int]:
    """打印统一审计行并返回 (errors, warns)；sink 收集原行进 audit.txt。

    行格式与严重度判定单一事实源在 fvstyle（format_audit_lines /
    problem_severity）：未识别规则按 error——无法归类的条目必须响亮
    失败，不静默降级。
    """
    lines = fvstyle.format_audit_lines(problems)
    errs = sum(fvstyle.problem_severity(p) == "error" for p in problems)
    for line in lines:
        print(line)
    if sink is not None:
        sink.extend(lines)
    return errs, len(problems) - errs


def _print_slot_inches(spec):
    """spec.size 声明的目标槽位 -> 英寸；显式 [w,h] 无槽位意图 -> None
    （fv.audit 自动档只对超过 full 宽的图启用 full 槽）。"""
    slots = dict(fvspec.SIZE_SLOTS)
    us = spec.get("size_slots")
    if isinstance(us, dict):
        slots.update(us)
    size = spec.get("size", "half")
    name = None
    if isinstance(size, str):
        name = size
    elif isinstance(size, dict):
        name = size.get("slot", "half")
    if name is None:
        return None
    v = slots.get(name)
    return float(v) if v is not None else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--outdir", type=Path)
    ap.add_argument("--dpi", type=int)
    ap.add_argument(
        "--no-audit", action="store_true", help="skip fvstyle.audit and lint printing"
    )
    ap.add_argument(
        "--no-readback",
        action="store_true",
        help="skip the rb-* post-draw readback rules (keeps lint and audit)",
    )
    ap.add_argument(
        "--overlay",
        action="store_true",
        help="write <stem>.overlay.png with axes/legend/text window extents",
    )
    args = ap.parse_args(argv)

    src = args.spec.resolve()
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    try:
        spec = json.loads(src.read_text())
    except json.JSONDecodeError as e:
        print(f"spec error: {src.name}: {e}", file=sys.stderr)
        return 2
    if not isinstance(spec, dict):
        print(
            f"spec error: {src.name}: top level must be a JSON object, "
            f"got {type(spec).__name__}",
            file=sys.stderr,
        )
        return 2

    # CLI 保证有产物：缺 output 块时注入默认。
    if "output" not in spec:
        spec["output"] = {"path": src.stem, "formats": DEFAULT_FORMATS}

    try:
        fig = fvspec.render(spec, base_dir=src.parent, outdir=args.outdir, dpi=args.dpi)
    except fvspec.SpecError as e:
        print(f"spec error: {e}", file=sys.stderr)
        return 2

    report = getattr(fig, "fvspec_report", {})
    audit_lines = []
    if not args.no_audit:
        for w in report.get("warnings", []):
            line = f"warn lint:{w}"
            print(line)
            audit_lines.append(line)
    saved = list(report.get("saved", []))

    # audit overrides：spec 的声明文本集喂给 rb-label-diff、size 槽位喂给
    # print-fit；--no-readback 只豁免 rb-* 三条（lint 与其余审计照跑）。
    overrides = {}
    if args.no_readback:
        base = report.get("audit_kwargs", {}).get("ignore") or set()
        overrides["ignore"] = set(base) | fvstyle.RB_RULES
    else:
        overrides["declared"] = fvspec.declared_texts(spec, base_dir=src.parent)
    slot = _print_slot_inches(spec)
    if slot is not None:
        overrides["print_slot"] = slot

    if args.no_audit:
        errs = warns = 0
    else:
        errs, warns = emit_audit(fvspec.audit_fig(fig, **overrides), audit_lines)
        warns += len(report.get("warnings", []))

    # 审计确认行：「审计跑过且收敛」与「审计没跑」在 stdout 可区分——
    # clean 是 0 warn 0 err，skipped 显式标注 --no-audit
    if args.no_audit:
        audit_lines.append("audit: skipped (--no-audit)")
    elif not errs and not warns:
        audit_lines.append("audit: clean")
    else:
        parts = []
        if errs:
            parts.append(f"{errs} error(s)")
        if warns:
            parts.append(f"{warns} warning(s)")
        audit_lines.append("audit: " + ", ".join(parts))
    print(audit_lines[-1])

    # 审计报告落盘：与 stdout 相同的 warn/ERR 行 + 首部 spec 名；--no-audit
    # 写一行 skipped 而不是留一份过期报告——产物旁永远能查到本次审计状态
    stem = saved[0].with_suffix("") if saved else (args.outdir or src.parent) / src.stem
    apath = stem.parent / f"{stem.name}.audit.txt"
    if args.no_audit:
        apath.write_text(f"spec: {src}\naudit: skipped (--no-audit)\n")
    else:
        apath.write_text(f"spec: {src}\n" + "\n".join(audit_lines) + "\n")

    if args.overlay:
        opath = stem.parent / f"{stem.name}.overlay.png"
        # 与渲染同一 rc 复量，坐标才对应已落盘的产物
        with mpl.rc_context(rc=report.get("rc") or {}):
            fvstyle.overlay(fig, opath)
        saved.append(opath)

    if saved:
        # 审计出 error 时产物仍已落盘——用 artifacts: 列名，'ok:' 只表示
        # 全程干净，避免「ok: 之后跟 ERR + 退出码 1」的自相矛盾
        print(
            ("ok:" if not errs else "artifacts:"),
            ", ".join(p.name for p in saved),
        )
    elif not errs:
        print("ok: rendered (unsaved)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
