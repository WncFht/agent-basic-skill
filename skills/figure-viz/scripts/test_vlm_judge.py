#!/usr/bin/env python3
"""test_vlm_judge.py — vlm_judge.py 回归自检：评审单结构、intent 抽取、退出码契约。

每条用例起 vlm_judge.py 子进程，断言退出码与评审单内容；claude backend
用 PATH 上的假 `claude` 脚本喂死回复，不调真模型（确定性、零成本）。

    python3 scripts/test_vlm_judge.py

任一 FAIL → 退出 1。只依赖 stdlib。
"""

import base64
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
JUDGE = SCRIPTS / "vlm_judge.py"

# 1x1 透明 PNG——评审单不读像素，有个真图文件够走通流程
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)

# 假 claude：原样吐出 argv 环境注入的回复，模拟 `claude -p` 成功路径
FAKE_CLAUDE_OK = """#!/bin/sh
echo "FAKE-VLM-REPLY claim-data PASS"
"""
FAKE_CLAUDE_BAD = """#!/bin/sh
echo "boom" >&2
exit 3
"""


def run_judge(*argv, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(JUDGE), *map(str, argv)],
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def make_fig(td, name="fig.png"):
    f = Path(td) / name
    f.write_bytes(PNG_1PX)
    return f


def make_claude(bindir, script):
    exe = Path(bindir) / ("claude.exe" if os.name == "nt" else "claude")
    exe.write_text(script)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


def check(name, bad):
    print(
        ("PASS" if not bad else "FAIL"), name, "" if not bad else "| " + "; ".join(bad)
    )
    return not bad


def main() -> int:
    fails = 0
    with tempfile.TemporaryDirectory(prefix="fvj-") as td:
        fig = make_fig(td)

        # -- clean run: backend none，无 intent --------------------------------
        rc, out = run_judge(fig)
        sheet_path = fig.parent / "fig.vlm-judge.md"
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        if "ok: fig.vlm-judge.md" not in out:
            bad.append(f"missing ok line: {out.strip()}")
        if not sheet_path.is_file():
            bad.append("sheet not written")
        else:
            sheet = sheet_path.read_text()
            for want in (
                "意图摘要",
                "Checklist",
                "总判",
                "可复制的 VLM 提示词",
                "## 产物",
                "主张—数据一致性",
                "标签可读性",
                "编码通道可辨识度",
                "阅读顺序",
                "未埋点碰撞风险",
                "图—caption 一致性",
                "backend=none",
            ):
                if want not in sheet:
                    bad.append(f"sheet missing '{want}'")
        fails += not check("clean-run-sheet", bad)

        # -- 无 intent 时同目录候选被列出 --------------------------------------
        (Path(td) / "NOTES.md").write_text("# 机制说明\n本图论证 X→Y 流程。\n")
        make_fig(td, "withcand.png")
        (Path(td) / "withcand.spec.json").write_text(json.dumps({"version": 1}))
        rc, out = run_judge(Path(td) / "withcand.png")
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        sheet = (Path(td) / "withcand.vlm-judge.md").read_text()
        for want in ("候选 intent 来源", "NOTES.md", "withcand.spec.json"):
            if want not in sheet:
                bad.append(f"sheet missing '{want}'")
        fails += not check("intent-candidates-listed", bad)

        # -- --intent spec.json：抽 meta.ledger/caption + series 名单 ----------
        spec = {
            "version": 1,
            "meta": {"ledger": "台账: acc 是验证集 top1", "caption": "train loss"},
            "series": [{"kind": "line", "id": "s1"}],
        }
        intent_json = Path(td) / "fig.spec.json"
        intent_json.write_text(json.dumps(spec))
        rc, out = run_judge(fig, "--intent", intent_json, "--out", Path(td) / "r2.md")
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        sheet = (Path(td) / "r2.md").read_text()
        for want in ("台账: acc 是验证集 top1", "train loss", "s1", "spec 字段抽取"):
            if want not in sheet:
                bad.append(f"sheet missing '{want}'")
        fails += not check("intent-spec-extract", bad)

        # -- --intent 纯文本：NOTES.md 截截取进摘要 ----------------------------
        notes = Path(td) / "mynotes.md"
        notes.write_text("本图主张：方法 A 全面超过基线 B。\n细节略。")
        rc, out = run_judge(fig, "--intent", notes, "--out", Path(td) / "r3.md")
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        if "方法 A 全面超过基线 B" not in (Path(td) / "r3.md").read_text():
            bad.append("intent text not in sheet")
        fails += not check("intent-text-excerpt", bad)

        # -- backend claude：假 claude 在 PATH 上，回复进报告 ------------------
        fakebin = Path(td) / "fakebin"
        fakebin.mkdir()
        make_claude(fakebin, FAKE_CLAUDE_OK)
        rc, out = run_judge(
            fig,
            "--backend",
            "claude",
            "--out",
            Path(td) / "r4.md",
            env_extra={"PATH": str(fakebin)},
        )
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        sheet = (Path(td) / "r4.md").read_text()
        if "FAKE-VLM-REPLY claim-data PASS" not in sheet:
            bad.append("claude reply not in sheet")
        fails += not check("backend-claude-reply", bad)

        # -- backend claude：claude 不在 PATH → warn 降级，仍 exit 0 ------------
        emptybin = Path(td) / "emptybin"
        emptybin.mkdir()
        rc, out = run_judge(
            fig,
            "--backend",
            "claude",
            "--out",
            Path(td) / "r5.md",
            env_extra={"PATH": str(emptybin)},
        )
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        if "warn backend:" not in out:
            bad.append(f"missing warn backend: {out.strip()}")
        if "ok:" not in out:
            bad.append("sheet not produced on fallback")
        fails += not check("backend-claude-missing-fallback", bad)

        # -- backend claude：假 claude 非零退出 → warn，仍 exit 0 ---------------
        badbin = Path(td) / "badbin"
        badbin.mkdir()
        make_claude(badbin, FAKE_CLAUDE_BAD)
        rc, out = run_judge(
            fig,
            "--backend",
            "claude",
            "--out",
            Path(td) / "r6.md",
            env_extra={"PATH": str(badbin)},
        )
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        if "warn backend:" not in out:
            bad.append(f"missing warn backend: {out.strip()}")
        fails += not check("backend-claude-nonzero-fallback", bad)

        # -- 用法错误：图不存在 → exit 2；intent 不存在 → exit 2 ----------------
        rc, out = run_judge(Path(td) / "nope.png")
        fails += not check(
            "missing-fig-exit2",
            [] if rc == 2 else [f"expected exit 2, got {rc}"],
        )
        rc, out = run_judge(fig, "--intent", Path(td) / "nope.md")
        fails += not check(
            "missing-intent-exit2",
            [] if rc == 2 else [f"expected exit 2, got {rc}"],
        )

        # -- 非常见后缀 → warn input，仍 exit 0 ---------------------------------
        bmp = make_fig(td, "fig.bmp")
        rc, out = run_judge(bmp, "--out", Path(td) / "r7.md")
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        if "warn input:" not in out:
            bad.append(f"missing warn input: {out.strip()}")
        fails += not check("unusual-suffix-warn", bad)

        # -- --out 落不了盘 → warn output + 评审单转 stdout，仍 exit 0 ----------
        blocker = Path(td) / "blocker"
        blocker.write_text("x")
        rc, out = run_judge(fig, "--out", blocker / "sub" / "r.md")
        bad = []
        if rc != 0:
            bad.append(f"exit {rc}")
        if "warn output:" not in out:
            bad.append(f"missing warn output: {out.strip()}")
        if "# VLM 语义评审单" not in out:
            bad.append("sheet not on stdout fallback")
        fails += not check("unwritable-out-stdout-fallback", bad)

    # ERR 扫描：干净跑 + backend 降级跑，stdout/stderr 都不得出现 'ERR '
    with tempfile.TemporaryDirectory(prefix="fvj2-") as td:
        fig = make_fig(td)
        bad = []
        for argv, env in (
            ((fig,), None),
            ((fig, "--backend", "claude"), {"PATH": tempfile.gettempdir()}),
        ):
            rc, out = run_judge(*argv, env_extra=env)
            if rc != 0:
                bad.append(f"exit {rc} for {argv[1:] or 'default'}")
            if any(line.startswith("ERR ") for line in out.splitlines()):
                bad.append(f"ERR line emitted: {out.strip()}")
        fails += not check("never-emits-ERR", bad)

    print(f"--- {fails} failed ---" if fails else "--- all cases passed ---")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
