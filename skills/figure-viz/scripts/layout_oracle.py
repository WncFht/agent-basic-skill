#!/usr/bin/env python3
r"""layout_oracle.py — DAG/通信拓扑布局求解器：只产坐标，不产图。

用法：
    layout_oracle.py IN.json [--backend auto|lualatex|simple] [--emit-tex]

IN.json（单位一律 cm）:
    {"nodes":  [{"id": "a", "w": 3.6, "h": 1.55}, ...],
     "edges":  [["a", "b"], ...],
     "options": {"direction": "TB"|"LR", "layer_gap": 1.2, "node_gap": 0.8}}

stdout 第一行输出坐标 JSON {"<id>": [x, y]}——cm，tikzpicture 直角坐标
（x 右、y 上），原点在布局包围盒左下角（最左/最下节点盒边贴 0，坐标
全部非负）。--emit-tex 在 JSON 之后逐行追加
    \coordinate (id) at (x,y);
供直接粘进 tex（id 需是合法 tikz 节点名，奇异字符请自行改名）。

stderr 打状态行：'ok: backend=.. nodes=..' / 'warn oracle: ..' /
'ERR oracle: ..'。

backend：
  lualatex  生成 \graph[layered layout] 驱动 tex 跑 lualatex（pgf
            graphdrawing 的 Sugiyama 实现），\pgfextractx + \typeout
            回收每个节点中心坐标；
  simple    纯 python：环断后入度全 <= 1（纯树/森林）走 tidy-tree——
            兄弟按输入边序横排、子树沿各深度轮廓贴合（边隙 >= node_gap）、
            父盒居中首末子中心中轴、等深同层；一般 DAG 走 Sugiyama-lite
            （DFS 反馈边删除 → longest-path 分层 → barycenter 下/上两遍
            扫层内排序 → 层内按节点尺寸 +node_gap 边距排开，相邻层距 =
            两层最大节点尺寸/2 之和 + layer_gap）；
  auto      纯树/森林输入直接走 simple 的 tidy 路径（lualatex Sugiyama
            实测在纯树上打乱兄弟序、产生可见交叉）；其余先试 lualatex，
            不可用或失败回退 simple（warn oracle:）。

退出码：0 成功（可带 warn）；1 显式 --backend lualatex 但后端失败；
2 输入/用法非法。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PT_PER_CM = 28.45274
FVPOS_RE = re.compile(r"^FVPOS (\S+) ([-+\d.]+)pt ([-+\d.]+)pt")

DEFAULT_LAYER_GAP = 1.2
DEFAULT_NODE_GAP = 0.8


class UsageError(Exception):
    """输入/用法非法 -> exit 2"""


class BackendError(Exception):
    """lualatex 后端不可用/失败 -> auto 回退或显式指定时 exit 1"""


# --- 输入 -----------------------------------------------------------------


def load_spec(path: Path):
    """校验 IN.json -> (nodes{id:(w,h)}, order[ids], edges, dir, gaps)。"""
    try:
        spec = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise UsageError(f"{path}: {e}") from e
    if not isinstance(spec, dict):
        raise UsageError("top level must be a JSON object")
    raw_nodes = spec.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise UsageError('"nodes" must be a non-empty list')
    nodes, order = {}, []
    for i, n in enumerate(raw_nodes):
        if not isinstance(n, dict) or "id" not in n:
            raise UsageError(f"nodes[{i}]: missing 'id'")
        nid = str(n["id"])
        if nid in nodes:
            raise UsageError(f"duplicate node id {nid!r}")
        try:
            w, h = float(n["w"]), float(n["h"])
        except (KeyError, TypeError, ValueError) as e:
            raise UsageError(f"node {nid!r}: need numeric w,h") from e
        if w <= 0 or h <= 0:
            raise UsageError(f"node {nid!r}: w,h must be > 0")
        nodes[nid] = (w, h)
        order.append(nid)
    edges = []
    for i, e in enumerate(spec.get("edges", []) or []):
        if not (isinstance(e, (list, tuple)) and len(e) == 2):
            raise UsageError(f"edges[{i}]: must be a [src, dst] pair")
        s, d = str(e[0]), str(e[1])
        for ep in (s, d):
            if ep not in nodes:
                raise UsageError(f"edges[{i}]: endpoint {ep!r} not in nodes")
        edges.append((s, d))
    opts = spec.get("options") or {}
    if not isinstance(opts, dict):
        raise UsageError('"options" must be an object')
    direction = str(opts.get("direction", "TB")).upper()
    if direction not in ("TB", "LR"):
        raise UsageError(f"options.direction must be TB|LR, got {direction!r}")

    def num(key, default):
        try:
            v = float(opts.get(key, default))
        except (TypeError, ValueError) as e:
            raise UsageError(f"options.{key} must be numeric") from e
        if v < 0:
            raise UsageError(f"options.{key} must be >= 0")
        return v

    return (
        nodes,
        order,
        edges,
        direction,
        num("layer_gap", DEFAULT_LAYER_GAP),
        num("node_gap", DEFAULT_NODE_GAP),
    )


# --- 规范化 -------------------------------------------------------------
# origin = 布局包围盒左下角：最左/最下节点盒边贴 0，所有坐标非负


def normalize(coords, nodes):
    minx = min(cx - nodes[i][0] / 2 for i, (cx, _) in coords.items())
    miny = min(cy - nodes[i][1] / 2 for i, (_, cy) in coords.items())
    return {i: (cx - minx, cy - miny) for i, (cx, cy) in coords.items()}


# --- lualatex 后端 ------------------------------------------------------


def tex_driver(nodes, order, edges, direction, layer_gap, node_gap):
    """graphdrawing 驱动 tex。图内节点一律匿名成 n0..（免引号/特殊字符
    的转义坑），输出再映射回原 id。level/sibling distance 都是中心距，
    取「最大节点尺寸 + gap」保证任意相邻盒边隙 >= gap。"""
    alias = {nid: f"n{i}" for i, nid in enumerate(order)}
    if direction == "TB":
        grow = "down"
        level = max(h for _, h in nodes.values()) + layer_gap
        sibling = max(w for w, _ in nodes.values()) + node_gap
    else:
        grow = "right"
        level = max(w for w, _ in nodes.values()) + layer_gap
        sibling = max(h for _, h in nodes.values()) + node_gap
    lines = [
        r"\documentclass{standalone}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{graphs,graphdrawing}",
        r"\usegdlibrary{layered}",
        r"\begin{document}",
        r"\begin{tikzpicture}",
        f"\\graph[layered layout, grow={grow},",
        f"  level distance={level:.4f}cm, sibling distance={sibling:.4f}cm,",
        r"  nodes={rectangle, inner sep=0pt}] {",
    ]
    for nid in order:
        w, h = nodes[nid]
        lines.append(
            f"  {alias[nid]}/[minimum width={w:.4f}cm, minimum height={h:.4f}cm];"
        )
    for s, d in edges:
        lines.append(f"  {alias[s]} -> {alias[d]};")
    lines.append("};")
    lines.append(r"\makeatletter")
    for nid in order:
        a = alias[nid]
        lines.append(
            f"\\pgfextractx{{\\pgf@xa}}{{\\pgfpointanchor{{{a}}}{{center}}}}%\n"
            f"\\pgfextracty{{\\pgf@ya}}{{\\pgfpointanchor{{{a}}}{{center}}}}%\n"
            f"\\typeout{{FVPOS {a} \\the\\pgf@xa\\space\\the\\pgf@ya}}"
        )
    lines += [r"\makeatother", r"\end{tikzpicture}", r"\end{document}"]
    return "\n".join(lines) + "\n", alias


def run_lualatex(nodes, order, edges, direction, layer_gap, node_gap):
    if shutil.which("lualatex") is None:
        raise BackendError("lualatex not found in PATH")
    tex, alias = tex_driver(nodes, order, edges, direction, layer_gap, node_gap)
    with tempfile.TemporaryDirectory(prefix="fv-oracle-") as td:
        src = Path(td) / "layout.tex"
        src.write_text(tex)
        try:
            proc = subprocess.run(
                ["lualatex", "-interaction=nonstopmode", "-halt-on-error", src.name],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as e:
            raise BackendError("lualatex timed out") from e
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr)[-800:]
            raise BackendError(f"lualatex failed:\n{tail}")
        pos = {}
        for ln in proc.stdout.splitlines():
            m = FVPOS_RE.match(ln.strip())
            if m:
                pos[m.group(1)] = (
                    float(m.group(2)) / PT_PER_CM,
                    float(m.group(3)) / PT_PER_CM,
                )
    missing = [a for a in alias.values() if a not in pos]
    if missing:
        raise BackendError(f"lualatex output missing nodes: {missing}")
    return {nid: pos[alias[nid]] for nid in order}


# --- simple 后端（Sugiyama-lite）----------------------------------------


def break_cycles(order, edges):
    """Eades 式反馈边删除：DFS 中指向栈上祖先的边不参与分层。
    返回 (dag_edges, dropped)。自环天然被丢（起点压栈时即指自己）。"""
    adj = {i: [] for i in order}
    for s, d in edges:
        adj[s].append(d)
    color = dict.fromkeys(order, 0)  # 0 白、1 灰(栈上)、2 黑
    dag, dropped = [], []
    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(order) * 8 + 100))

    def dfs(u):
        color[u] = 1
        for v in adj[u]:
            if color[v] == 1:
                dropped.append((u, v))
                continue
            dag.append((u, v))
            if color[v] == 0:
                dfs(v)
        color[u] = 2

    for i in order:
        if color[i] == 0:
            dfs(i)
    return dag, dropped


def raw_forest(order, edges):
    """输入边本身是否森林（每点入度 <= 1）。auto 用它把纯树输入直接
    交给 simple 的 tidy 路径——lualatex Sugiyama 实测在纯树上打乱
    兄弟序、产生可见交叉。"""
    indeg = dict.fromkeys(order, 0)
    for _, d in edges:
        indeg[d] += 1
        if indeg[d] > 1:
            return False
    return True


def tidy_tree(nodes, order, children, roots, direction, layer_gap, node_gap):
    """森林 tidy 布局（Reingold-Tilford 轮廓法）：后序摆子树——兄弟按
    输入边序逐个横排，新子树沿各深度轮廓贴紧已摆兄弟（盒边隙 >=
    node_gap），父盒居中于首末子中心中轴；等深同层。入度 <= 1 保证
    全图可从 roots 到达。返回 coords{id:(x,y)}（未归一化）。"""
    axi = 0 if direction == "TB" else 1  # 横轴尺寸：TB 比宽，LR 比高
    off = {}  # v -> 相对父盒中心的横轴偏移（根相对虚拟原点）
    lcon, rcon = {}, {}  # v -> {相对深度: 子树最左/右缘（v 中心为 0）}

    def place(kids):
        """kids 按序横排：每个子树贴紧已摆兄弟的右轮廓，返回偏移列表。
        union_r[d] = 已摆子树群在相对深度 d 的最右缘。"""
        offs, union_r = [], {}
        for c in kids:
            o = 0.0
            if offs:
                o = max(
                    (
                        union_r[d] + node_gap - lv
                        for d, lv in lcon[c].items()
                        if d in union_r
                    ),
                    default=0.0,
                )
            offs.append(o)
            for d, rv in rcon[c].items():
                if d not in union_r or o + rv > union_r[d]:
                    union_r[d] = o + rv
        return offs

    post = []  # 后序：先子后父，同 root 内保持 DFS 序
    for r in roots:
        stack = [(r, False)]
        while stack:
            v, done = stack.pop()
            if done:
                post.append(v)
                continue
            stack.append((v, True))
            for c in reversed(children[v]):
                stack.append((c, False))

    for v in post:
        half = nodes[v][axi] / 2
        ch = children[v]
        if not ch:
            lcon[v], rcon[v] = {0: -half}, {0: half}
            continue
        offs = place(ch)
        mid = (offs[0] + offs[-1]) / 2  # 首末子中心中轴
        lc, rc = {0: -half}, {0: half}
        for c, o in zip(ch, offs):
            off[c] = o - mid
            for d, val in lcon[c].items():
                k, cur = d + 1, off[c] + val
                if k not in lc or cur < lc[k]:
                    lc[k] = cur
            for d, val in rcon[c].items():
                k, cur = d + 1, off[c] + val
                if k not in rc or cur > rc[k]:
                    rc[k] = cur
        lcon[v], rcon[v] = lc, rc

    u = dict(zip(roots, place(roots)))  # 多根树并排：根的横轴绝对坐标
    depth = dict.fromkeys(roots, 0)
    stack = list(roots)
    while stack:
        v = stack.pop()
        for c in children[v]:
            u[c] = u[v] + off[c]
            depth[c] = depth[v] + 1
            stack.append(c)

    n_layers = max(depth.values()) + 1
    dsz = [0.0] * n_layers
    for v, dv in depth.items():
        dsz[dv] = max(dsz[dv], nodes[v][1 - axi])
    ctr = [0.0] * n_layers
    for li in range(1, n_layers):
        ctr[li] = ctr[li - 1] + (dsz[li - 1] + dsz[li]) / 2 + layer_gap

    coords = {}
    for v in order:
        if direction == "TB":  # 层 0 在顶，兄弟左→右按输入边序
            coords[v] = (u[v], -ctr[depth[v]])
        else:  # LR：层 0 在左，兄弟上→下按输入边序
            coords[v] = (ctr[depth[v]], -u[v])
    return coords


def run_simple(nodes, order, edges, direction, layer_gap, node_gap):
    """纯 python 布局。返回 (coords{id:(x,y)}, dropped edges)。
    环断后每点入度 <= 1（纯树/森林）走 tidy_tree；其余 Sugiyama-lite。"""
    dag, dropped = break_cycles(order, edges)
    succ = {i: [] for i in order}
    pred = {i: [] for i in order}
    for s, d in dag:
        succ[s].append(d)
        pred[d].append(s)
    if all(len(pred[i]) <= 1 for i in order):
        roots = [i for i in order if not pred[i]]
        coords = tidy_tree(nodes, order, succ, roots, direction, layer_gap, node_gap)
        return coords, dropped
    # longest-path 分层（Kahn 拓扑序上递推）
    indeg = {i: len(pred[i]) for i in order}
    queue = [i for i in order if indeg[i] == 0]
    topo = []
    while queue:
        u = queue.pop(0)
        topo.append(u)
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    layer = dict.fromkeys(order, 0)
    for u in topo:
        for v in succ[u]:
            layer[v] = max(layer[v], layer[u] + 1)
    n_layers = max(layer.values()) + 1
    rows = [[] for _ in range(n_layers)]
    for i in order:  # 层内初始序 = 输入序
        rows[layer[i]].append(i)
    pos = {v: k for row in rows for k, v in enumerate(row)}

    # barycenter 两遍扫：下行按 pred 重心排、上行按 succ 重心排
    def sweep(nei, seq):
        for li in seq:
            bc = {}
            for v in rows[li]:
                ns = [pos[n] for n in nei[v]]
                bc[v] = sum(ns) / len(ns) if ns else pos[v]
            rows[li].sort(key=lambda v: (bc[v], pos[v]))
            for k, v in enumerate(rows[li]):
                pos[v] = k

    sweep(pred, range(1, n_layers))
    sweep(succ, range(n_layers - 2, -1, -1))

    coords = {}
    if direction == "TB":  # 层 = 行（层 0 在顶），行内左→右排
        rw = [sum(nodes[v][0] for v in row) + node_gap * (len(row) - 1) for row in rows]
        max_w = max(rw, default=0.0)
        yc, cy, prev_mh = [], 0.0, 0.0
        for li, row in enumerate(rows):
            mh = max(nodes[v][1] for v in row)
            cy = -mh / 2 if li == 0 else yc[-1] - (prev_mh + mh) / 2 - layer_gap
            yc.append(cy)
            prev_mh = mh
        for li, row in enumerate(rows):
            x = (max_w - rw[li]) / 2  # 各行对中最宽行的中轴
            for v in row:
                w, _ = nodes[v]
                coords[v] = (x + w / 2, yc[li])
                x += w + node_gap
    else:  # LR：层 = 列（层 0 在左），列内上→下排
        ch = [sum(nodes[v][1] for v in col) + node_gap * (len(col) - 1) for col in rows]
        max_h = max(ch, default=0.0)
        xc, cx, prev_mw = [], 0.0, 0.0
        for li, col in enumerate(rows):
            mw = max(nodes[v][0] for v in col)
            cx = mw / 2 if li == 0 else xc[-1] + (prev_mw + mw) / 2 + layer_gap
            xc.append(cx)
            prev_mw = mw
        for li, col in enumerate(rows):
            y = -(max_h - ch[li]) / 2  # 各列对中最高列的中轴
            for v in col:
                _, h = nodes[v]
                coords[v] = (xc[li], y - h / 2)
                y -= h + node_gap
    return coords, dropped


# --- 主入口 -----------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="layout_oracle.py",
        description="DAG/拓扑布局求解器：输入节点尺寸+边，输出中心坐标 JSON（cm）",
    )
    ap.add_argument("spec", type=Path, help="IN.json")
    ap.add_argument(
        "--backend",
        choices=["auto", "lualatex", "simple"],
        default="auto",
        help="auto=纯树走 tidy，否则先试 lualatex 失败回退 simple（默认）",
    )
    ap.add_argument(
        "--emit-tex",
        action="store_true",
        help="JSON 之后追加 \\coordinate (id) at (x,y); 行",
    )
    args = ap.parse_args(argv)

    try:
        nodes, order, edges, direction, layer_gap, node_gap = load_spec(args.spec)
    except UsageError as e:
        print(f"ERR oracle: {e}", file=sys.stderr)
        return 2

    warns = []
    coords, used = None, None
    # 纯树输入 auto 直接走 simple 的 tidy 路径（lualatex Sugiyama 实测
    # 在纯树上兄弟乱序出可见交叉）；显式 --backend lualatex 不受影响
    tree_in = args.backend == "auto" and raw_forest(order, edges)
    if args.backend in ("auto", "lualatex") and not tree_in:
        try:
            coords = run_lualatex(nodes, order, edges, direction, layer_gap, node_gap)
            used = "lualatex"
        except BackendError as e:
            if args.backend == "lualatex":
                print(f"ERR oracle: {e}", file=sys.stderr)
                return 1
            warns.append(f"lualatex backend failed ({e}); fell back to simple")
    if coords is None:
        coords, dropped = run_simple(
            nodes, order, edges, direction, layer_gap, node_gap
        )
        used = "simple"
        if dropped:
            warns.append(
                f"dropped {len(dropped)} feedback edge(s) to break cycle(s): "
                + ", ".join(f"{s}->{d}" for s, d in dropped[:6])
            )
    coords = normalize(coords, nodes)

    for w in warns:
        print(f"warn oracle: {w}", file=sys.stderr)
    out = {i: [round(coords[i][0], 3), round(coords[i][1], 3)] for i in order}
    print(json.dumps(out, ensure_ascii=False))
    if args.emit_tex:
        for i in order:
            x, y = coords[i]
            print(f"\\coordinate ({i}) at ({x:.3f},{y:.3f});")
    print(
        f"ok: backend={used} nodes={len(order)} edges={len(edges)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
