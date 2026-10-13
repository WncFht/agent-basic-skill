#!/usr/bin/env python3
"""test_oracle_tree.py — layout_oracle 的 tidy-tree（纯树/森林）路径回归。

    python3 scripts/test_oracle_tree.py

实测背景（树/森林布局）：simple 后端零交叉但父盒不居中子代中轴；lualatex
Sugiyama 在纯树上兄弟乱序出可见交叉。现 oracle 对森林输入（环断后每点
入度 <= 1）走 tidy 路径：兄弟按输入边序、父盒居中首末子中心中轴、
等深同层、子树轮廓贴合；auto 下纯树直接跳过 lualatex。

fixture：满二叉对称树、非对称混合尺寸树（单子链 + 深扇出）、beam
search 式剪枝树（宽 3 深 3，9 个 L2 中 3 个带子叶）、双树森林 + 孤立
点、LR 向。断言：父居中、兄弟保序、等深同层、相邻层零交叉、盒不重叠、
兄弟/层隙 >= gap；auto 与 simple 坐标一致（证明 auto 走了 tidy）；
带环输入仍出图且 warn。
"""

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from testkit import FAILS, check

SCRIPTS = Path(__file__).resolve().parent
ORACLE = SCRIPTS / "layout_oracle.py"


def _tree(nodes_spec, edges_spec, direction="TB", layer_gap=1.0, node_gap=0.5):
    return {
        "nodes": [{"id": n, "w": w, "h": h} for n, w, h in nodes_spec],
        "edges": [list(e) for e in edges_spec],
        "options": {
            "direction": direction,
            "layer_gap": layer_gap,
            "node_gap": node_gap,
        },
    }


# 满二叉树深 3：15 节点全同尺寸
SYMM = _tree(
    [
        ("r", 1.2, 0.8),
        ("a", 1.2, 0.8),
        ("b", 1.2, 0.8),
        ("a1", 1.2, 0.8),
        ("a2", 1.2, 0.8),
        ("b1", 1.2, 0.8),
        ("b2", 1.2, 0.8),
        ("a11", 1.2, 0.8),
        ("a12", 1.2, 0.8),
        ("a21", 1.2, 0.8),
        ("a22", 1.2, 0.8),
        ("b11", 1.2, 0.8),
        ("b12", 1.2, 0.8),
        ("b21", 1.2, 0.8),
        ("b22", 1.2, 0.8),
    ],
    [
        ("r", "a"),
        ("r", "b"),
        ("a", "a1"),
        ("a", "a2"),
        ("b", "b1"),
        ("b", "b2"),
        ("a1", "a11"),
        ("a1", "a12"),
        ("a2", "a21"),
        ("a2", "a22"),
        ("b1", "b11"),
        ("b1", "b12"),
        ("b2", "b21"),
        ("b2", "b22"),
    ],
)

# 非对称：a 侧单子链挂深扇出，b 侧浅宽；尺寸参差
ASYM = _tree(
    [
        ("r", 1.6, 0.9),
        ("a", 1.2, 0.8),
        ("b", 2.0, 1.0),
        ("a1", 1.4, 0.8),
        ("b1", 1.0, 0.7),
        ("b2", 1.8, 0.9),
        ("a11", 2.4, 0.8),
        ("a12", 1.0, 0.8),
        ("a13", 1.8, 0.8),
        ("b11", 3.0, 0.7),
    ],
    [
        ("r", "a"),
        ("r", "b"),
        ("a", "a1"),
        ("a1", "a11"),
        ("a1", "a12"),
        ("a1", "a13"),
        ("b", "b1"),
        ("b", "b2"),
        ("b1", "b11"),
    ],
)

# beam search 式剪枝树：宽 3 深 3，
# L2 九个候选里只有 c1/c5/c8 存活扩展 L3，其余为剪枝终止叶
BEAM = _tree(
    [(n, 1.15, 0.72) for n in ["r", "p1", "p2", "p3"]]
    + [(f"c{i}", 1.15, 0.72) for i in range(1, 10)]
    + [(f"l{i}", 1.15, 0.72) for i in range(1, 10)],
    [("r", "p1"), ("r", "p2"), ("r", "p3")]
    + [(p, f"c{i}") for p, i in zip(("p1", "p2", "p3"), (1, 4, 7))]
    + [(p, f"c{i}") for p, i in zip(("p1", "p2", "p3"), (2, 5, 8))]
    + [(p, f"c{i}") for p, i in zip(("p1", "p2", "p3"), (3, 6, 9))]
    + [("c1", f"l{i}") for i in (1, 2, 3)]
    + [("c5", f"l{i}") for i in (4, 5, 6)]
    + [("c8", f"l{i}") for i in (7, 8, 9)],
    layer_gap=1.1,
    node_gap=0.55,
)

# 双树森林 + 孤立点：t1 深 2、iso 无子
FOREST = _tree(
    [
        ("t1", 1.4, 0.8),
        ("t2", 1.2, 0.9),
        ("iso", 2.0, 0.7),
        ("t1a", 1.0, 0.8),
        ("t1b", 1.6, 0.8),
        ("t1a1", 1.2, 0.8),
        ("t2a", 1.0, 0.8),
        ("t2b", 1.4, 0.8),
        ("t2c", 1.0, 0.8),
    ],
    [
        ("t1", "t1a"),
        ("t1", "t1b"),
        ("t1a", "t1a1"),
        ("t2", "t2a"),
        ("t2", "t2b"),
        ("t2", "t2c"),
    ],
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


def tree_info(spec):
    """children（按输入边序）/ roots / depth，从 spec 边表直算。"""
    children = {str(n["id"]): [] for n in spec["nodes"]}
    indeg = dict.fromkeys(children, 0)
    for s, d in spec["edges"]:
        s, d = str(s), str(d)
        children[s].append(d)
        indeg[d] += 1
    roots = [i for i in children if indeg[i] == 0]
    depth = dict.fromkeys(roots, 0)
    stack = list(roots)
    while stack:
        v = stack.pop()
        for c in children[v]:
            depth[c] = depth[v] + 1
            stack.append(c)
    return children, roots, depth


def check_tree(spec, proc, direction):
    """tidy 不变量：父居中 / 兄弟保序 / 等深同层 / 邻层零交叉 /
    盒不重叠 / 兄弟与层隙达标。输出坐标只留 3 位小数，容差放宽到 2e-3。"""
    bad = []
    if proc.returncode != 0:
        return [f"exit {proc.returncode}: {proc.stderr[-300:]}"]
    cs = coords(proc)
    sizes = {str(n["id"]): (n["w"], n["h"]) for n in spec["nodes"]}
    children, roots, depth = tree_info(spec)
    if sorted(cs) != sorted(sizes):
        return [f"coord ids {sorted(cs)} != node ids {sorted(sizes)}"]
    opts = spec.get("options", {})
    lgap, ngap = opts.get("layer_gap", 1.2), opts.get("node_gap", 0.8)
    tb = direction == "TB"

    def uv(v):  # 横轴（兄弟序方向）：TB 取 x，LR 取 -y（首子在最上）
        return cs[v][0] if tb else -cs[v][1]

    def dv(v):  # 纵深轴：TB 取 y（父 > 子），LR 取 x（父 < 子）
        return cs[v][1] if tb else cs[v][0]

    # 等深同层
    by_depth = defaultdict(list)
    for v, d in depth.items():
        by_depth[d].append(v)
    for d, vs in sorted(by_depth.items()):
        vals = {round(dv(v), 6) for v in vs}
        if len(vals) > 1:
            bad.append(f"depth {d} not collinear: {sorted(vals)}")

    # 边单调 + 层隙（树边恰跨一层；纵深尺寸 TB 取 h、LR 取 w）
    dsize = 1 if tb else 0
    for s, d in spec["edges"]:
        s, d = str(s), str(d)
        if depth[d] != depth[s] + 1:
            bad.append(f"edge {s}->{d}: depth {depth[s]}->{depth[d]}")
            continue
        span = dv(d) - dv(s) if tb else dv(s) - dv(d)
        if span >= 0:
            bad.append(f"edge {s}->{d}: not monotone")
            continue
        edge_gap = abs(dv(s) - dv(d)) - (sizes[s][dsize] + sizes[d][dsize]) / 2
        if edge_gap < lgap - 2e-3:
            bad.append(f"edge {s}->{d}: layer gap {edge_gap:.3f} < {lgap}")

    # 兄弟保序 + 兄弟边隙 + 父居中
    for p, kids in children.items():
        if not kids:
            continue
        us = [uv(c) for c in kids]
        for i in range(1, len(us)):
            if us[i] - us[i - 1] <= 1e-6:
                bad.append(f"sibling order {p}: {us}")
            min_gap = (
                sizes[kids[i - 1]][0 if tb else 1] + sizes[kids[i]][0 if tb else 1]
            ) / 2 + ngap
            if us[i] - us[i - 1] < min_gap - 2e-3:
                bad.append(f"sibling gap {p}: {us[i] - us[i - 1]:.3f} < {min_gap:.3f}")
        mid = (us[0] + us[-1]) / 2
        if abs(uv(p) - mid) > 2e-3:
            bad.append(f"parent {p} not centered: {uv(p):.3f} vs mid {mid:.3f}")

    # 邻层零交叉：按父横轴排序，子横轴须严格增
    by_bound = defaultdict(list)
    for s, d in spec["edges"]:
        s, d = str(s), str(d)
        by_bound[depth[s]].append((uv(s), uv(d), s, d))
    for d0, pairs in sorted(by_bound.items()):
        pairs.sort()
        for i in range(1, len(pairs)):
            if pairs[i][1] - pairs[i - 1][1] <= 1e-6:
                bad.append(
                    f"crossing d{d0}->d{d0 + 1}: {pairs[i - 1][2:]} vs {pairs[i][2:]}"
                )

    # 盒不重叠
    ids = list(cs)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            wa, ha = sizes[a]
            wb, hb = sizes[b]
            dx = (wa + wb) / 2 - abs(cs[a][0] - cs[b][0])
            dy = (ha + hb) / 2 - abs(cs[a][1] - cs[b][1])
            if min(dx, dy) > 2e-3:
                bad.append(f"overlap {a} vs {b}: {dx:.3f}x{dy:.3f}cm")
    return bad


def main() -> int:
    # --- 对称满二叉树 ---------------------------------------------------------
    proc = oracle(SYMM, "--backend", "simple")
    bad = check_tree(SYMM, proc, "TB")
    if not bad:  # 满二叉：叶行等距（同宽叶相邻边隙恰为 node_gap）
        cs = coords(proc)
        xs = sorted(cs[f"a{i}{j}"][0] for i in (1, 2) for j in (1, 2))
        xs += sorted(cs[f"b{i}{j}"][0] for i in (1, 2) for j in (1, 2))
        xs.sort()
        diffs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        if max(diffs) - min(diffs) > 2e-3:
            bad.append(f"leaf row not evenly spaced: {diffs}")
    check("tree-symm-TB", not bad, "; ".join(bad))

    # --- 非对称混合尺寸树 -----------------------------------------------------
    proc = oracle(ASYM, "--backend", "simple")
    bad = check_tree(ASYM, proc, "TB")
    if not bad:
        cs = coords(proc)
        # 单子链：父与子同轴居中
        for p, c in (("a", "a1"), ("b1", "b11")):
            if abs(cs[p][0] - cs[c][0]) > 2e-3:
                bad.append(f"chain {p}->{c} not aligned: {cs[p][0]} vs {cs[c][0]}")
    check("tree-asym-TB", not bad, "; ".join(bad))

    # --- 剪枝树（beam search 同形回归）----------------------------------------
    bad = check_tree(BEAM, oracle(BEAM, "--backend", "simple"), "TB")
    check("tree-pruned-beam-TB", not bad, "; ".join(bad))

    # --- 森林：根按输入序横排 ---------------------------------------------------
    proc = oracle(FOREST, "--backend", "simple")
    bad = check_tree(FOREST, proc, "TB")
    if not bad:
        cs = coords(proc)
        if not (cs["t1"][0] < cs["t2"][0] < cs["iso"][0]):
            bad.append(f"root order broken: {[cs[r][0] for r in ('t1', 't2', 'iso')]}")
    check("tree-forest-TB", not bad, "; ".join(bad))

    # --- LR 向：兄弟上→下保序、父居中、单调 ----------------------------------
    lr = dict(SYMM, options=dict(SYMM["options"], direction="LR"))
    bad = check_tree(lr, oracle(lr, "--backend", "simple"), "LR")
    check("tree-symm-LR", not bad, "; ".join(bad))

    # --- auto 路由：纯树输入与 simple 坐标一致（跳过 lualatex）------------------
    bad = []
    pa, ps = oracle(BEAM, "--backend", "auto"), oracle(BEAM, "--backend", "simple")
    if pa.returncode != 0 or ps.returncode != 0:
        bad.append(f"exit auto={pa.returncode} simple={ps.returncode}")
    elif coords(pa) != coords(ps):
        bad.append("auto != simple on pure tree")
    if "backend=simple" not in pa.stderr:
        bad.append(f"auto did not take simple path: {pa.stderr.strip()}")
    check("tree-auto-routes-tidy", not bad, "; ".join(bad))

    # --- 非森林 DAG 不受影响（走 Sugiyama 路径，不炸即可）----------------------
    dag = json.loads(json.dumps(SYMM))
    dag["edges"].append(["a", "b1"])  # b1 双父 -> 非森林
    proc = oracle(dag, "--backend", "simple")
    bad = []
    if proc.returncode != 0:
        bad.append(f"non-forest exit {proc.returncode}: {proc.stderr[-200:]}")
    elif sorted(coords(proc)) != sorted(str(n["id"]) for n in dag["nodes"]):
        bad.append("non-forest coords incomplete")
    check("tree-nonforest-simple", not bad, "; ".join(bad))

    # --- 环断后仍是森林：回边被丢 + warn + tidy 仍生效 ---------------------------
    cyc = json.loads(json.dumps(SYMM))
    cyc["edges"].append(["b22", "r"])  # 叶->根回边
    proc = oracle(cyc, "--backend", "simple")
    bad = check_tree(SYMM, proc, "TB")  # 不变量按原树边表校验
    if "warn oracle:" not in proc.stderr:
        bad.append("no 'warn oracle:' for dropped feedback edge")
    check("tree-backedge-warn", not bad, "; ".join(bad))

    # --- 单点 + 自环：丢边后是孤立森林，仍出图 ----------------------------------
    loop = {"nodes": [{"id": "s", "w": 1.0, "h": 1.0}], "edges": [["s", "s"]]}
    proc = oracle(loop, "--backend", "simple")
    bad = []
    if proc.returncode != 0:
        bad.append(f"self-loop exit {proc.returncode}")
    elif list(coords(proc)) != ["s"]:
        bad.append("self-loop node missing")
    if "warn oracle:" not in proc.stderr:
        bad.append("no 'warn oracle:' for dropped self-loop")
    check("tree-selfloop", not bad, "; ".join(bad))

    print(f"--- done, {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
