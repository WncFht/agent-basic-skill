#!/usr/bin/env python3
"""test_oracle_codegen.py — layout_oracle + codegen 回归。

    python3 scripts/test_oracle_codegen.py

fixture：8 节点 DAG（菱形 + 跨层长边 src->aux->sink + 输入序打乱）。断言：
  - simple 后端：层序单调（TB 沿边严格下降）、相邻层边隙 >= layer_gap、
    盒两两不重叠；LR 同判（沿边 x 严格右移）
  - lualatex 后端（无 lualatex 时 SKIP）：同上
  - auto 与 lualatex 一致；--emit-tex 追加 \\coordinate 行
  - 非法输入（坏 JSON / 未知端点 / 坏 direction / 空 nodes）一律 exit 2；
    有向环输入 simple 仍出图 + 'warn oracle:'
  - codegen：自洽台账 → exit 0 且骨架含 vaudit/\\vzbbox/\\vzwire；
    xelatex 在场时 render_tex.py 编译 + 审计全绿；
    不自洽台账 → exit 0 + 'warn codegen:'；非法 JSON → exit 2
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ORACLE = SCRIPTS / "layout_oracle.py"
CODEGEN = SCRIPTS / "codegen.py"
RENDER_TEX = SCRIPTS / "render_tex.py"

DAG8 = {
    "nodes": [
        {"id": "src", "w": 3.0, "h": 1.0},
        {"id": "a1", "w": 2.0, "h": 0.8},
        {"id": "a2", "w": 2.6, "h": 1.0},
        {"id": "join", "w": 3.4, "h": 1.2},
        {"id": "e1", "w": 1.8, "h": 0.8},
        {"id": "e2", "w": 2.2, "h": 1.0},
        {"id": "aux", "w": 1.5, "h": 0.8},
        {"id": "sink", "w": 3.0, "h": 1.0},
    ],
    "edges": [
        ["src", "a1"],
        ["src", "a2"],
        ["a1", "join"],
        ["a2", "join"],
        ["join", "e1"],
        ["join", "e2"],
        ["e1", "sink"],
        ["e2", "sink"],
        ["src", "aux"],
        ["aux", "sink"],
    ],
    "options": {"direction": "TB", "layer_gap": 1.2, "node_gap": 0.8},
}

LEDGER = {
    "canvas": {"w": 12.0, "h": 7.0},
    "boxes": [
        {
            "id": n,
            "class": "blk",
            "style": "model, draw=vteal, fill=vteal!14, text width=3.0cm,"
            " minimum height=1.4cm",
            "x": x,
            "y": 5.5,
            "text": f"{{\\small ${t}$}}",
            "inside": "bandA",
        }
        for n, x, t in (("a1", 2.0, "A"), ("a2", 6.0, "B"), ("a3", 10.0, "C"))
    ]
    + [
        {
            "id": n,
            "class": "blk",
            "style": "model, draw=vorange, fill=vorange!14,"
            " text width=3.0cm, minimum height=1.4cm",
            "x": x,
            "y": 2.0,
            "text": f"{{\\small ${t}$}}",
            "inside": "bandB",
            "alignx": ax,
        }
        for n, x, t, ax in (
            ("b1", 2.0, "D", "a1"),
            ("b2", 6.0, "E", "a2"),
            ("b3", 10.0, "F", "a3"),
        )
    ],
    "bands": [
        {
            "id": "bandA",
            "sw": [0.0, 4.4],
            "ne": [12.0, 6.6],
            "style": "band=vteal",
            "tags": "class=band",
        },
        {
            "id": "bandB",
            "sw": [0.0, 0.9],
            "ne": [12.0, 3.1],
            "style": "band=vorange",
            "tags": "class=band",
        },
    ],
    "wires": [
        {
            "id": "wa1",
            "pts": ["a1.east", "a2.west"],
            "endpoint": "a1,a2",
            "via": "bandA",
        },
        {
            "id": "wa2",
            "pts": ["a2.east", "a3.west"],
            "endpoint": "a2,a3",
            "via": "bandA",
        },
        {
            "id": "wb1",
            "pts": ["b1.east", "b2.west"],
            "endpoint": "b1,b2",
            "via": "bandB",
        },
        {
            "id": "wb2",
            "pts": ["b2.east", "b3.west"],
            "endpoint": "b2,b3",
            "via": "bandB",
        },
        {
            "id": "wdown",
            "pts": ["a2.south", "b2.north"],
            "endpoint": "a2,b2",
            "via": "bandA,bandB",
        },
    ],
    "mean": {
        "text": "\\textbf{对象}\\quad {\\color{vteal}$\\blacksquare$}\\,A 族；"
        "{\\color{vorange}$\\blacksquare$}\\,B 族\\\\[3pt]"
        "\\textbf{机制}\\quad 下行链路"
    },
    "caption": {"text": "codegen 骨架冒烟：带=阶段，块=算子"},
}

FAILS = []


def report(name, bad):
    if bad:
        FAILS.append(name)
        for m in bad:
            print("  ", m)
    print(("PASS" if not bad else "FAIL"), name)


def run(script, *argv):
    return subprocess.run(
        [sys.executable, str(script), *argv], capture_output=True, text=True
    )


def oracle(spec_dict, *flags):
    with tempfile.TemporaryDirectory(prefix="fv-orc-") as td:
        f = Path(td) / "in.json"
        f.write_text(json.dumps(spec_dict))
        return subprocess.run(
            [sys.executable, str(ORACLE), str(f), *flags],
            capture_output=True,
            text=True,
        )


def coords(proc):
    """首行 stdout -> {id: (x,y)}"""
    return {k: (v[0], v[1]) for k, v in json.loads(proc.stdout.splitlines()[0]).items()}


def check_layout(spec_dict, proc, direction):
    """两个后端共享的不变量：边单调 + 无重叠。"""
    bad = []
    if proc.returncode != 0:
        return [f"exit {proc.returncode}: {proc.stderr[-300:]}"]
    sizes = {str(n["id"]): (n["w"], n["h"]) for n in spec_dict["nodes"]}
    gap = spec_dict.get("options", {}).get("layer_gap", 1.2)
    cs = coords(proc)
    if sorted(cs) != sorted(sizes):
        bad.append(f"coord ids {sorted(cs)} != node ids {sorted(sizes)}")
        return bad
    for s, d in spec_dict["edges"]:
        s, d = str(s), str(d)
        if direction == "TB":
            edge_gap = (cs[s][1] - sizes[s][1] / 2) - (cs[d][1] + sizes[d][1] / 2)
            if cs[s][1] <= cs[d][1]:
                bad.append(f"edge {s}->{d}: not monotone down")
            elif edge_gap < gap - 1e-6:
                bad.append(f"edge {s}->{d}: layer gap {edge_gap:.3f} < {gap}")
        else:
            edge_gap = (cs[d][0] - sizes[d][0] / 2) - (cs[s][0] + sizes[s][0] / 2)
            if cs[d][0] <= cs[s][0]:
                bad.append(f"edge {s}->{d}: not monotone right")
            elif edge_gap < gap - 1e-6:
                bad.append(f"edge {s}->{d}: layer gap {edge_gap:.3f} < {gap}")
    ids = list(cs)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            wa, ha = sizes[a]
            wb, hb = sizes[b]
            dx = (wa + wb) / 2 - abs(cs[a][0] - cs[b][0])
            dy = (ha + hb) / 2 - abs(cs[a][1] - cs[b][1])
            if min(dx, dy) > 1e-4:
                bad.append(f"overlap {a} vs {b}: {dx:.3f}x{dy:.3f}cm")
    return bad


def main() -> int:
    # --- simple 后端，TB -------------------------------------------------
    bad = check_layout(DAG8, oracle(DAG8, "--backend", "simple"), "TB")
    report("oracle-simple-TB", bad)

    # --- simple 后端，LR -------------------------------------------------
    lr = dict(DAG8, options=dict(DAG8["options"], direction="LR"))
    bad = check_layout(lr, oracle(lr, "--backend", "simple"), "LR")
    report("oracle-simple-LR", bad)

    # --- lualatex 后端 ----------------------------------------------------
    if shutil.which("lualatex") is None:
        print("SKIP oracle-lualatex (no lualatex)")
    else:
        proc = oracle(DAG8, "--backend", "lualatex")
        report("oracle-lualatex-TB", check_layout(DAG8, proc, "TB"))
        bad = check_layout(lr, oracle(lr, "--backend", "lualatex"), "LR")
        report("oracle-lualatex-LR", bad)
        # auto 此处应落 lualatex 且与显式运行一致
        proc_auto = oracle(DAG8, "--backend", "auto")
        bad = [] if coords(proc_auto) == coords(proc) else ["auto != lualatex"]
        report("oracle-auto-matches", bad)

    # --- emit-tex -------------------------------------------------------------
    proc = oracle(DAG8, "--backend", "simple", "--emit-tex")
    bad = []
    lines = proc.stdout.splitlines()
    if len(lines) != 9 or not lines[1].startswith("\\coordinate (src) at ("):
        bad.append(f"emit-tex lines wrong: {lines[:3]}")
    report("oracle-emit-tex", bad)

    # --- 非法输入 -> exit 2 ---------------------------------------------
    bad = []
    for spec in (
        {"nodes": []},
        {"nodes": [{"id": "a", "w": 1, "h": 1}], "edges": [["a", "ghost"]]},
        dict(DAG8, options={"direction": "XX"}),
        {"nodes": [{"id": "a", "w": -1, "h": 1}]},
    ):
        if oracle(spec).returncode != 2:
            bad.append(f"spec {str(spec)[:60]}: exit != 2")
    with tempfile.TemporaryDirectory(prefix="fv-orc-") as td:
        f = Path(td) / "bad.json"
        f.write_text("{oops")
        p = subprocess.run(
            [sys.executable, str(ORACLE), str(f)], capture_output=True, text=True
        )
        if p.returncode != 2:
            bad.append("malformed json: exit != 2")
        if oracle(DAG8, "--backend", "simple", f.name).returncode == 0:
            bad.append("extra positional accepted")
    report("oracle-usage-exit2", bad)

    # --- 有环：simple 仍输出 + warn -------------------------------------
    cyc = dict(DAG8)
    cyc["edges"] = DAG8["edges"] + [["sink", "src"], ["sink", "sink"]]
    proc = oracle(cyc, "--backend", "simple")
    bad = []
    if proc.returncode != 0:
        bad.append(f"cycle input exit {proc.returncode}")
    if "warn oracle:" not in proc.stderr:
        bad.append("no 'warn oracle:' for dropped feedback edges")
    report("oracle-cycle-warn", bad)

    # --- codegen：自洽 ledger ---------------------------------------
    with tempfile.TemporaryDirectory(prefix="fv-cg-") as td:
        lf = Path(td) / "ledger.json"
        lf.write_text(json.dumps(LEDGER))
        out = Path(td) / "skel.tex"
        proc = run(CODEGEN, lf, "-o", out)
        bad = []
        if proc.returncode != 0:
            bad.append(f"exit {proc.returncode}: {proc.stderr[-300:]}")
        elif proc.stderr.strip():
            bad.append(f"unexpected warns: {proc.stderr.strip()}")
        else:
            tex = out.read_text()
            for needle in (
                "\\input{vizstyle.tex}",
                "\\input{vizaudit.tex}",
                "vaudit={class=blk,inside=bandA}",
                "\\vzbbox{bandA}",
                "\\vzwire{wdown}",
                "\\draw[varr]",
                "\\node[mean",
            ):
                if needle not in tex:
                    bad.append(f"skeleton missing {needle!r}")
        report("codegen-skeleton", bad)

        # 经 render_tex（xelatex）编译 + 审计
        if shutil.which("xelatex") is None:
            print("SKIP codegen-compile (no xelatex)")
        else:
            rp = run(RENDER_TEX, out, "--no-svg", "--no-png")
            bad = []
            if rp.returncode != 0:
                bad.append(f"render_tex exit {rp.returncode}: {rp.stdout[-400:]}")
            if "ERR " in rp.stdout or "ERR " in rp.stderr:
                bad.append(f"audit errors: {rp.stdout[-400:]}")
            if not any(ln.startswith("ok:") for ln in rp.stdout.splitlines()):
                bad.append(f"no 'ok:' line: {rp.stdout[-200:]}")
            report("codegen-compile-audit", bad)

    # --- codegen：不自洽 ledger 告警但退出 0 ------------------------
    with tempfile.TemporaryDirectory(prefix="fv-cg-") as td:
        bad_led = json.loads(json.dumps(LEDGER))
        bad_led["boxes"][0]["inside"] = "ghost"
        bad_led["boxes"][1]["x"] = 99.0  # 越出画布
        bad_led["bands"][0]["sw"] = [12.0, 6.6]  # 角点写反
        lf = Path(td) / "bad.json"
        lf.write_text(json.dumps(bad_led))
        proc = run(CODEGEN, lf, "-o", Path(td) / "skel.tex")
        bad = []
        if proc.returncode != 0:
            bad.append(f"exit {proc.returncode} (want 0 with warns)")
        if proc.stderr.count("warn codegen:") < 3:
            bad.append(f"expected >=3 warns, got:\n{proc.stderr}")
        report("codegen-warns", bad)

    # --- codegen：坏 json -> exit 2 -------------------------------------
    with tempfile.TemporaryDirectory(prefix="fv-cg-") as td:
        f = Path(td) / "bad.json"
        f.write_text("[1,2]")
        proc = run(CODEGEN, f)
        bad = [] if proc.returncode == 2 else [f"exit {proc.returncode}"]
        report("codegen-usage-exit2", bad)

    print(f"--- done, {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
