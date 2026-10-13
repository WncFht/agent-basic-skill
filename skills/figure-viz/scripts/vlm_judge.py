#!/usr/bin/env python3
"""vlm_judge.py — 语义评审单生成器：把「图说了什么 vs 画了什么」外包给 VLM。

用法:
    vlm_judge.py FIG.png [--intent FILE] [--backend none|claude]
                         [--out FILE] [--timeout SEC]

机器审计（check_audit.py / fv.audit）只管几何与数据不变量——「顶部主张与
曲线证据矛盾」这类语义层造假是固有盲区（实测案例：几何审计全绿，语义
评审仍判 fail），机器查不了。本脚本生成一份 markdown 评审单：意图摘要 +
六条 checklist（每条带具体问题）+ 可直接喂给任意 VLM 的提示词 + 产物路径。
`--backend claude` 且 PATH 有 claude 时实际调用
``claude -p <prompt> <图>`` 并把回复附进报告；`--backend none`（默认）
只产评审单与提示词，由调用者自己喂给任意 VLM。

`--intent` 接台账/spec/NOTES 等「图想论证什么」的文本：.json 按 spec 处
理（抽 meta.ledger / meta.caption），其余按纯文本截取摘要。不给 intent
时只按图面评审，并列出同目录检测到的候选 intent 来源。

这是 advisory 工具，不是审计：
  - 评审结论永不进退出码——exit 0 = 评审单已生成（无论发现多少问题）；
    exit 2 = 输入/用法错误（图或 intent 不存在、参数非法）；没有 exit 1。
  - 输出遵守统一行约：只 emit 'warn <rule>: <msg>'（永不 emit 'ERR '），
    干净运行打 'ok: <files>'；评审单本身不属 ok:/artifacts: 语义——它不
    是渲染产物，是对渲染产物的意见。
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# intent 摘要截取上限：够装台账/主张，不整篇搬进评审单
INTENT_MAX_CHARS = 8000

# (id, 标题, [具体问题]) —— 评审单与 VLM 提示词共用同一份数据，防两侧漂移
CHECKLIST = [
    (
        "claim-data",
        "主张—数据一致性",
        [
            "顶部主张、标题与含义框里的每条断言，是否都有曲线/形状/数值上的直接证据？",
            "有没有主张断言的趋势、大小或因果，在绘制内容里找不到支撑，甚至与证据相反？",
            "数据里显眼的现象（交叉、反转、异常点、平台期）是否都被主张或标注解释，而不是被回避？",
            "示意性简化（单元格数≠真实维度、截断轴、省略分片）是否只声明一次、且不会被误读为真实量？",
        ],
    ),
    (
        "label-read",
        "标签可读性",
        [
            "全部文字在交付尺寸下是否可读：字号、对比度足够，无裁切、截断或溢出边框？",
            "每个符号、缩写与记号是否在使用处或含义框中定义？有无未解释的孤立记号？",
            "数学排版是否正常（无豆腐块、无缺字形）？旋转/竖排文字是否确有必要？",
        ],
    ),
    (
        "encoding",
        "编码通道可辨识度",
        [
            "同时出现的色相是否两两可辨（含明度相近色对与色盲安全）？",
            "颜色即语义是否成立：同一色相全图同一含义，换含义才换色相，明度只表幅度？",
            "第二通道（线型/marker/明度层级/纹理）与其声称的类别或幅度是否单调对应？",
            "活跃色相族数是否在预算内（≤4 族 + 中性灰），超出是否有显式声明？",
        ],
    ),
    (
        "reading-order",
        "阅读顺序",
        [
            "视觉动线是否按论证顺序推进（主张→结构/数据→结论），而非让视线来回跳？",
            "连接器方向与语义流向是否一致；反馈回路、分支合流是否一眼可辨？",
            "多面板/多阶段图的默认阅读顺序（行优先/列优先/编号）是否显然？",
        ],
    ),
    (
        "unmarked-collide",
        "未埋点碰撞风险",
        [
            "是否有未进审计的文字/标签压在线上、框上或其他文字上（机器审计只覆盖埋点对象）？",
            "画布边缘是否有被裁掉半个的元素？连接线是否擦过非端点对象？",
            "白衬底标签是否盖住了不该盖的连线或数据？",
        ],
    ),
    (
        "fig-caption",
        "图—caption 一致性",
        [
            "底部含义框/标识行描述的是否恰是实际画出的对象，不多不少？",
            "若 intent 给了正文 caption 或台账：图内文字与之是否互相印证，而非各说各话？",
            "标识行是否泄露了图里没有的信息，或漏掉了图中实际存在的关键对象？",
        ],
    ),
]

VERDICT_GUIDE = (
    "PASS = 全部条目通过；CONCERN = 有疑点需人工复核；"
    "FAIL = 主张与图面冲突或可读性失守，拒收重画"
)


def excerpt(text: str, limit: int = INTENT_MAX_CHARS) -> str:
    """截一段能代表「图想论证什么」的文本——摘要不是全文搬运。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n…（截断，全文 {len(text)} 字符）"


def read_intent(path: Path) -> tuple[str, str]:
    """读 intent 文件，返回 (摘要文本, 来源描述)。

    .json 按 spec 处理：抽 meta.ledger / meta.caption / meta.usermeta，
    再附 series 与 panels 名单帮 VLM 对齐「声明了哪些绘制对象」；
    非 dict 或解析失败回落为纯文本截取。其余后缀一律按纯文本截取。
    """
    raw = path.read_text(errors="replace")
    if path.suffix == ".json":
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError:
            spec = None
        if isinstance(spec, dict):
            meta = spec.get("meta") or {}
            parts = []
            if isinstance(meta.get("ledger"), str) and meta["ledger"].strip():
                parts.append("台账（meta.ledger）:\n" + meta["ledger"].strip())
            if isinstance(meta.get("caption"), str) and meta["caption"].strip():
                parts.append("标识行（meta.caption）: " + meta["caption"].strip())
            series = spec.get("series")
            if isinstance(series, list) and series:
                names = [
                    s.get("id") or s.get("kind") or "?"
                    for s in series
                    if isinstance(s, dict)
                ]
                parts.append("series: " + ", ".join(names))
            panels = spec.get("panels")
            if isinstance(panels, dict) and panels:
                parts.append("panels: " + ", ".join(sorted(panels)))
            if parts:
                return excerpt("\n\n".join(parts)), "spec 字段抽取"
    return excerpt(raw), "文本截取"


def intent_candidates(fig: Path) -> list[Path]:
    """无 --intent 时列出同目录可喂给 --intent 的候选来源。"""
    out = []
    for cand in (
        fig.parent / "NOTES.md",
        fig.with_suffix(".spec.json"),
        fig.with_suffix(".tex"),
        fig.with_suffix(".audit"),
    ):
        if cand.is_file() and cand != fig:
            out.append(cand)
    return out


def vlm_prompt(fig: Path, intent: str | None) -> str:
    """可复制给任意 VLM 的评审提示词——与评审单 checklist 同源。"""
    lines = [
        "你是研究图的语义评审。评审所附图片：只按图面与所给意图判断，",
        "不臆测未给出的数据，不复核几何像素级对齐（那是机器审计的活）。",
        "逐条判定：每项给 PASS / CONCERN / FAIL 加一行证据（指出图中具体",
        "位置），最后给总判（PASS / CONCERN / FAIL）与一句最优先的修改建议。",
        "",
        f"评审对象图片：{fig}",
    ]
    if intent:
        lines += ["", "## 作者声明的意图", intent]
    else:
        lines += ["", "## 作者声明的意图", "（未提供——仅按图面评审）"]
    lines += ["", "## Checklist"]
    for i, (_key, title, questions) in enumerate(CHECKLIST, 1):
        lines.append(f"{i}. {title}")
        lines += [f"   - {q}" for q in questions]
    lines += ["", f"总判口径：{VERDICT_GUIDE}。"]
    return "\n".join(lines)


def build_sheet(
    fig: Path,
    intent_src: Path | None,
    intent_text: str | None,
    intent_desc: str | None,
    candidates: list[Path],
    backend: str,
    prompt: str,
    vlm_reply: str | None,
    vlm_note: str | None,
    out_path: Path,
) -> str:
    lines = [
        f"# VLM 语义评审单 — {fig.name}",
        "",
        f"- figure: `{fig}`",
        f"- intent: {f'`{intent_src}`（{intent_desc}）' if intent_src else '未提供——仅按图面评审'}",
        f"- backend: `{backend}`",
        f"- date: {datetime.datetime.now().astimezone().date().isoformat()}",
        "- 性质: advisory——本单结论不阻断交付、不进机器审计退出码",
        "",
        "## 意图摘要",
        "",
        intent_text or "（未提供 intent；VLM 仅能按图面推断论证目标）",
        "",
    ]
    if not intent_src and candidates:
        lines += [
            "检测到候选 intent 来源（未使用，经 `--intent` 传入可增强针对性）：",
            "",
            *[f"- `{c}`" for c in candidates],
            "",
        ]
    lines += ["## Checklist", ""]
    for i, (_key, title, questions) in enumerate(CHECKLIST, 1):
        lines += [
            f"### {i}. {title}",
            "",
            "判定：____（PASS / CONCERN / FAIL）　证据：____",
            "",
            *[f"- [ ] {q}" for q in questions],
            "",
        ]
    lines += [
        "## 总判",
        "",
        f"____（{VERDICT_GUIDE}）",
        "",
        "最优先修改建议：____",
        "",
        "## 附：可复制的 VLM 提示词",
        "",
        "把下面整段连同图片一起喂给任意 VLM（或 `--backend claude` 自动调用）：",
        "",
        "```text",
        prompt,
        "```",
        "",
        "## VLM 回复",
        "",
    ]
    if vlm_reply:
        lines += [vlm_reply, ""]
    elif vlm_note:
        lines += [f"（backend={backend} 未产出回复：{vlm_note}）", ""]
    else:
        lines += ["（backend=none：未调用 VLM，请用上方提示词自行评审）", ""]
    lines += [
        "## 产物",
        "",
        f"- 评审单: `{out_path}`",
        f"- 评审对象: `{fig}`",
    ]
    if intent_src:
        lines.append(f"- intent: `{intent_src}`")
    lines.append("")
    return "\n".join(lines)


def run_claude(prompt: str, fig: Path, timeout: int) -> tuple[str | None, str | None]:
    """调 `claude -p <prompt> <图>`；返回 (回复, 失败原因) 恰一非 None。"""
    exe = shutil.which("claude")
    if exe is None:
        return None, "claude 不在 PATH"
    try:
        proc = subprocess.run(
            [exe, "-p", prompt, str(fig)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"claude 超时（>{timeout}s）"
    except OSError as e:
        return None, f"claude 调用失败: {e}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip()[:200]
        return None, f"claude exit {proc.returncode}: {tail}"
    reply = proc.stdout.strip()
    return (reply or None), (None if reply else "claude 返回空")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="生成图的 VLM 语义评审单（advisory，永不进退出码语义）"
    )
    ap.add_argument(
        "fig", type=Path, help="待评审图（png/jpg/webp；其他后缀照收但 VLM 可读性自理）"
    )
    ap.add_argument(
        "--intent",
        type=Path,
        help="台账/spec/NOTES 等声明「图想论证什么」的文件（.json 按 spec 抽 meta）",
    )
    ap.add_argument(
        "--backend",
        choices=["none", "claude"],
        default="none",
        help="none=只产评审单+提示词（默认）；claude=实际调用 claude -p 并附回复",
    )
    ap.add_argument(
        "--out",
        type=Path,
        help="评审单输出路径（默认 <图名>.vlm-judge.md 与图同目录）",
    )
    ap.add_argument(
        "--timeout", type=int, default=300, help="claude backend 超时秒数（默认 300）"
    )
    args = ap.parse_args(argv)

    fig = args.fig.resolve()
    if not fig.is_file():
        print(f"vlm-judge: no such figure: {fig}", file=sys.stderr)
        return 2
    if args.intent is not None and not args.intent.is_file():
        print(f"vlm-judge: no such intent file: {args.intent}", file=sys.stderr)
        return 2

    warns = []
    if fig.suffix.lower() not in IMAGE_SUFFIXES:
        warns.append(
            ("input", f"{fig.name}: 非常见图片后缀，多数 VLM 只吃 png/jpg/webp")
        )

    intent_src = args.intent.resolve() if args.intent else None
    intent_text = intent_desc = None
    if intent_src:
        try:
            intent_text, intent_desc = read_intent(intent_src)
        except OSError as e:
            warns.append(
                ("intent", f"{intent_src.name}: 读取失败（{e}），按无 intent 继续")
            )
            intent_src = None
    candidates = [] if intent_src else intent_candidates(fig)

    out_path = args.out or fig.parent / (fig.stem + ".vlm-judge.md")
    prompt = vlm_prompt(fig, intent_text)

    vlm_reply = vlm_note = None
    backend = args.backend
    if backend == "claude":
        vlm_reply, vlm_note = run_claude(prompt, fig, args.timeout)
        if vlm_reply is None:
            warns.append(("backend", f"claude backend 未产出回复：{vlm_note}"))

    sheet = build_sheet(
        fig,
        intent_src,
        intent_text,
        intent_desc,
        candidates,
        backend,
        prompt,
        vlm_reply,
        vlm_note,
        out_path,
    )

    for rule, msg in warns:
        print(f"warn {rule}: {msg}")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sheet)
    except OSError as e:
        # 产物落不了盘不阻断 advisory——评审单转投 stdout，调用者照样能用
        print(f"warn output: {out_path}: 写盘失败（{e}），评审单转 stdout")
        print(sheet)
        return 0
    print(f"ok: {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
