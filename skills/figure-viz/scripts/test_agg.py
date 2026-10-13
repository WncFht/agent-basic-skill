#!/usr/bin/env python3
"""test_agg.py — fvagg 聚合 helper 的隔离测试（纯 stdlib，不经 uv）。

覆盖：coerce_cell 各型、agg_rows 分组与统计量语义（对照 statistics
直算）、keyed_to_rows 双向、cells_present 缺格、dump/load csv
round-trip 恒等、add_field 派生列。
"""

import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "mpl"))

import fvagg
from testkit import FAILS, check


def coerce():
    cases = [
        ("3", 3),
        ("03", 3),
        ("3.5", 3.5),
        ("-2", -2),
        ("1e3", 1000.0),
        ("true", True),
        ("False", False),
        ("x", "x"),
        ("", ""),
        (None, None),
    ]
    for raw, want in cases:
        got = fvagg.coerce_cell(raw)
        check(
            f"coerce-{raw!r}", got == want and type(got) is type(want), f"got {got!r}"
        )


def agg_basic():
    raw = [
        {"arm": "b", "K": 2, "v": 1.0},
        {"arm": "a", "K": 2, "v": 10.0},
        {"arm": "b", "K": 2, "v": 3.0},
        {"arm": "a", "K": 2, "v": 20.0},
        {"arm": "b", "K": 2, "v": 2.0},
        {"arm": "b", "K": 4, "v": 7.0},
    ]
    rows = fvagg.agg_rows(
        raw,
        keys=["arm", "K"],
        aggs={
            "med": ("v", "median"),
            "q25": ("v", "q25"),
            "q75": ("v", "q75"),
            "n": ("v", "n"),
            "mx": "v",  # 裸字段名 -> 默认 median
        },
    )
    check(
        "agg-shape",
        [tuple(r[k] for k in ("arm", "K")) for r in rows]
        == [("a", 2), ("b", 2), ("b", 4)],
        f"order {[tuple(r[k] for k in ('arm', 'K')) for r in rows]}",
    )
    b2 = rows[1]
    check("agg-median", b2["med"] == 2.0 and b2["n"] == 3, f"{b2}")
    qs = statistics.quantiles([1.0, 2.0, 3.0], n=4, method="inclusive")
    check(
        "agg-quantiles",
        b2["q25"] == qs[0] and b2["q75"] == qs[2],
        f"q25={b2['q25']} want {qs[0]}; q75={b2['q75']} want {qs[2]}",
    )
    check("agg-default-stat", b2["mx"] == 2.0, f"mx={b2['mx']}")
    a2 = rows[0]
    check(
        "agg-sorted-keys",
        a2["med"] == statistics.median([10.0, 20.0]),
        f"a2={a2}",
    )


def agg_edges():
    single = fvagg.agg_rows(
        [{"g": 1, "v": 5.0}], keys=["g"], aggs={"s": ("v", "std"), "m": ("v", "median")}
    )
    check(
        "agg-single-group",
        single == [{"g": 1, "s": 0.0, "m": 5.0}],
        f"{single}",
    )
    try:
        fvagg.agg_rows([{"g": 1, "v": 1.0}], keys=["g"], aggs={"x": ("v", "bogus")})
        check("agg-unknown-stat", False, "no raise")
    except ValueError:
        check("agg-unknown-stat", True)
    cust = fvagg.agg_rows(
        [{"g": 1, "v": 2.0}, {"g": 1, "v": 4.0}, {"g": 2, "v": 9.0}],
        keys=["g"],
        aggs={"rng": ("v", lambda vs: max(vs) - min(vs))},
    )
    check(
        "agg-callable",
        [r["rng"] for r in cust] == [2.0, 0.0],
        f"{cust}",
    )
    mixed = fvagg.agg_rows(
        [{"g": "x", "v": 1.0}, {"g": 5, "v": 2.0}],
        keys=["g"],
        aggs={"m": ("v", "median")},
    )
    check(
        "agg-mixed-key-order",
        [r["g"] for r in mixed] == ["x", 5],
        f"{[r['g'] for r in mixed]} (首见序兜底)",
    )


def keyed():
    fmap = {
        ("frozen", 2): {"med": 0.3, "q25": 0.25},
        ("live", 4): {"med": 0.2, "q25": 0.15},
    }
    rows = fvagg.keyed_to_rows(fmap, fields=["arm", "K"])
    check(
        "keyed-tuple",
        sorted(rows, key=lambda r: (r["arm"], r["K"]))
        == [
            {"arm": "frozen", "K": 2, "med": 0.3, "q25": 0.25},
            {"arm": "live", "K": 4, "med": 0.2, "q25": 0.15},
        ],
        f"{rows}",
    )
    rows1 = fvagg.keyed_to_rows({2: {"v": 1}, 4: {"v": 2}}, fields=["K"])
    check(
        "keyed-scalar",
        sorted(rows1, key=lambda r: r["K"]) == [{"K": 2, "v": 1}, {"K": 4, "v": 2}],
        f"{rows1}",
    )
    try:
        fvagg.keyed_to_rows({(1, 2): {"v": 1}}, fields=["a"])
        check("keyed-arity", False, "no raise")
    except ValueError:
        check("keyed-arity", True)


def cells():
    full = [{"x": a, "y": b} for a in (1, 2) for b in ("p", "q")]
    check("cells-full", fvagg.cells_present(full) == [], f"{fvagg.cells_present(full)}")
    sparse = full[:-1]  # 缺 (2,'q')
    check(
        "cells-missing",
        fvagg.cells_present(sparse) == [(2, "q")],
        f"{fvagg.cells_present(sparse)}",
    )


def csv_roundtrip():
    rows = [
        {"arm": "a", "K": 2, "med": 0.30000000000000004, "ok": True},
        {"arm": "b", "K": 4, "med": 0.125, "ok": False, "extra": "x"},
    ]
    with tempfile.TemporaryDirectory(prefix="fv-agg-") as td:
        p = Path(td) / "t.csv"
        fvagg.dump_csv(rows, p)
        back = fvagg.load_csv(p)
    check(
        "csv-cols",
        list(back[0]) == ["arm", "K", "med", "ok", "extra"],
        f"{list(back[0])}",
    )
    check(
        "csv-values",
        back[0]
        == {"arm": "a", "K": 2, "med": 0.30000000000000004, "ok": True, "extra": ""},
        f"{back[0]}",
    )
    check(
        "csv-types",
        isinstance(back[0]["K"], int)
        and isinstance(back[0]["med"], float)
        and back[0]["ok"] is True,
        f"{back[0]}",
    )
    with tempfile.TemporaryDirectory(prefix="fv-agg-") as td:
        p = Path(td) / "t.csv"
        fvagg.dump_csv(back, p)
        back2 = fvagg.load_csv(p)
    check("csv-stable", back2 == back, "dump→load→dump→load 应收敛")


def derived():
    rows = [{"a": 1}, {"a": 2}]
    out = fvagg.add_field(rows, "b", lambda r: r["a"] * 10)
    check(
        "add-field",
        out == [{"a": 1, "b": 10}, {"a": 2, "b": 20}] and "b" not in rows[0],
        f"{out} / orig {rows}",
    )


def pareto():
    pts = [
        {"cost": 1.0, "acc": 0.5, "tag": "a"},
        {"cost": 2.0, "acc": 0.7, "tag": "b"},
        {"cost": 3.0, "acc": 0.65, "tag": "c"},  # 被 (2,.7) 支配
        {"cost": 4.0, "acc": 0.9, "tag": "d"},
        {"cost": 0.5, "acc": 0.4, "tag": "e"},
        {"cost": 4.0, "acc": 0.8, "tag": "f"},  # 同 x 被 (4,.9) 支配
        {"cost": 4.0, "acc": 0.9, "tag": "g"},  # 与 d 完全同点——去重
    ]
    marked = fvagg.pareto_front(pts, "cost", "acc")
    want = {"a", "b", "d", "e"}
    got = {r["tag"] for r in marked if r["on_front"]}
    check(
        "pareto-mark",
        got == want
        and len(marked) == len(pts)
        and "on_front" not in pts[0]
        and [r["tag"] for r in marked] == [r["tag"] for r in pts],
        f"front {got} want {want}",
    )
    sub = fvagg.pareto_front(pts, "cost", "acc", mark=None)
    check(
        "pareto-subset",
        [(r["cost"], r["acc"]) for r in sub]
        == [(0.5, 0.4), (1.0, 0.5), (2.0, 0.7), (4.0, 0.9)],
        f"{[(r['cost'], r['acc']) for r in sub]}",
    )
    quad = [
        {"u": 1, "v": 0.5},
        {"u": 2, "v": 0.7},
        {"u": 3, "v": 0.65},
        {"u": 4, "v": 0.4},
    ]
    for senses, want in [
        (("min", "max"), [1, 2]),
        (("max", "max"), [2, 3, 4]),
        (("min", "min"), [1, 4]),
        (("max", "min"), [4]),
    ]:
        got_ids = [
            r["u"] for r in fvagg.pareto_front(quad, "u", "v", senses=senses, mark=None)
        ]
        check(
            f"pareto-sense-{senses}",
            got_ids == want,
            f"{senses}: {got_ids} want {want}",
        )
    fams = [
        {"fam": "A", "u": 1, "v": 0.95},  # 全局最优：支配所有 B 点
        {"fam": "B", "u": 2, "v": 0.5},  # 全局被支配，组内是前沿
        {"fam": "B", "u": 3, "v": 0.4},  # 组内也被 (2,.5) 支配
    ]
    bm = fvagg.pareto_front(fams, "u", "v", by="fam")
    check(
        "pareto-by",
        [bool(r["on_front"]) for r in bm] == [True, True, False],
        f"{[(r['fam'], r['u'], r['on_front']) for r in bm]}",
    )
    try:
        fvagg.pareto_front(pts, "cost", "acc", senses=("low", "max"))
        check("pareto-bad-sense", False, "no raise")
    except ValueError:
        check("pareto-bad-sense", True)
    try:
        fvagg.pareto_front([{"u": float("nan"), "v": 1}], "u", "v")
        check("pareto-nan", False, "no raise")
    except ValueError:
        check("pareto-nan", True)


def calib():
    rows = [
        {"c": 0.05, "y": 1},
        {"c": 0.07, "y": 0},  # bin0: n2 mc.06 acc.5
        {"c": 0.11, "y": 1},
        {"c": 0.12, "y": 1},
        {"c": 0.19, "y": 0},  # bin1: n3 mc.14 acc 2/3
        {"c": 0.55, "y": 0},
        {"c": 0.59, "y": 0},  # bin5: n2 mc.57 acc0
        {"c": 0.91, "y": 1},  # bin9: n1 mc.91 acc1
    ]
    br, st = fvagg.calibration_bins(rows, "c", "y", bins=10)
    check(
        "calib-shape",
        [r["bin"] for r in br] == [0, 1, 5, 9]
        and [r["n"] for r in br] == [2, 3, 2, 1]
        and st["nonempty"] == 4
        and st["n"] == 8,
        f"{[(r['bin'], r['n']) for r in br]} stats {st}",
    )
    b0, b1, b5, b9 = br
    check(
        "calib-values",
        abs(b0["conf"] - 0.06) < 1e-9
        and abs(b0["acc"] - 0.5) < 1e-9
        and abs(b0["x"] - 0.06) < 1e-9
        and abs(b0["center"] - 0.05) < 1e-9
        and abs(b1["conf"] - 0.14) < 1e-9
        and abs(b1["acc"] - 2 / 3) < 1e-9
        and abs(b5["gap"] - 0.57) < 1e-9
        and abs(b0["se"] - (0.5 * 0.5 / 2) ** 0.5) < 1e-9,
        f"b0 {b0} b1 {b1} b5 {b5}",
    )
    ece = (2 * 0.44 + 3 * abs(2 / 3 - 0.14) + 2 * 0.57 + 1 * 0.09) / 8
    check(
        "calib-ece-mce",
        abs(st["ece"] - ece) < 1e-9 and abs(st["mce"] - 0.57) < 1e-9,
        f"ece {st['ece']} want {ece}; mce {st['mce']}",
    )
    bc, _ = fvagg.calibration_bins(rows, "c", "y", bins=10, x="center")
    check(
        "calib-x-center",
        all(abs(r["x"] - w) < 1e-9 for r, w in zip(bc, [0.05, 0.15, 0.55, 0.95])),
        f"{[r['x'] for r in bc]}",
    )
    bk, _ = fvagg.calibration_bins(rows, "c", "y", bins=10, empty="keep")
    check(
        "calib-keep",
        len(bk) == 10
        and bk[3]["n"] == 0
        and bk[3]["acc"] is None
        and bk[3]["x"] is None
        and bk[0]["n"] == 2,
        f"{[(r['bin'], r['n']) for r in bk]}",
    )
    bm, sm = fvagg.calibration_bins(rows, "c", "y", bins=4, strategy="mass")
    check(
        "calib-mass",
        [r["n"] for r in bm] == [2, 2, 2, 2] and sm["oob"] == 0,
        f"{[(r['bin'], r['n'], r['lo'], r['hi']) for r in bm]}",
    )
    bo, so = fvagg.calibration_bins(
        [{"c": 1.05, "y": 1}, {"c": -0.02, "y": 0}, {"c": 0.5, "y": 1}],
        "c",
        "y",
        bins=4,
    )
    check(
        "calib-oob",
        so["oob"] == 2 and sum(r["n"] for r in bo) == 3,
        f"oob {so['oob']} bins {[(r['bin'], r['n']) for r in bo]}",
    )
    bez, sez = fvagg.calibration_bins([], "c", "y")
    check(
        "calib-empty",
        bez == [] and sez["ece"] is None and sez["mce"] is None and sez["n"] == 0,
        f"{bez} {sez}",
    )
    for kw, val in [
        ("strategy", "bogus"),
        ("x", "bogus"),
        ("empty", "bogus"),
        ("bins", 0),
    ]:
        try:
            fvagg.calibration_bins(rows, "c", "y", **{kw: val})
            check(f"calib-bad-{kw}", False, "no raise")
        except ValueError:
            check(f"calib-bad-{kw}", True)


def jit():
    rows = [
        {"g": "a", "v": 1.0},
        {"g": "b", "v": 2.0},
        {"g": "a", "v": 3.0},
        {"g": "b", "v": 4.0},
    ]
    out = fvagg.jitter(rows, "v", amount=0.1, seed=7)
    check(
        "jit-range-name",
        all(abs(r["v_j"] - r["v"]) <= 0.1 for r in out)
        and "v_j" not in rows[0]
        and len(out) == 4,
        f"{[r['v_j'] for r in out]}",
    )
    out2 = fvagg.jitter(rows, "v", amount=0.1, seed=7)
    check(
        "jit-deterministic",
        [r["v_j"] for r in out] == [r["v_j"] for r in out2],
        "same seed 两次结果不同",
    )
    cat = fvagg.jitter(rows, "g", amount=(0.0, 0.14), offset=0.08, seed=1, name="xj")
    pos = {"a": 0, "b": 1}
    check(
        "jit-cat-oneside",
        all(0.08 + pos[r["g"]] <= r["xj"] <= 0.22 + pos[r["g"]] for r in cat),
        f"{[(r['g'], r['xj']) for r in cat]}",
    )
    # by 分组独立流：过滤掉 b 组行不改 a 组抖动
    allr = fvagg.jitter(rows, "v", by="g", amount=0.5, seed=3)
    only_a = fvagg.jitter(
        [r for r in rows if r["g"] == "a"], "v", by="g", amount=0.5, seed=3
    )
    check(
        "jit-by-stable",
        [r["v_j"] for r in allr if r["g"] == "a"] == [r["v_j"] for r in only_a],
        f"all {[r['v_j'] for r in allr]} a-only {[r['v_j'] for r in only_a]}",
    )
    try:
        fvagg.jitter([{"v": float("nan")}], "v")
        check("jit-nan", False, "no raise")
    except ValueError:
        check("jit-nan", True)

    # mode='even'：组内等距摊开（bin 中心），确定性、与 seed 无关。
    # 数值 col 组内按值排序落位：v=1,2,3,4 → delta -0.15,-0.05,0.05,0.15
    ev = fvagg.jitter(rows, "v", amount=0.2, mode="even")
    check(
        "jit-even-spread",
        sorted(round(r["v_j"] - r["v"], 9) for r in ev) == [-0.15, -0.05, 0.05, 0.15],
        f"{[r['v_j'] for r in ev]}",
    )
    check(
        "jit-even-seed-free",
        [r["v_j"] for r in fvagg.jitter(rows, "v", amount=0.2, mode="even", seed=1)]
        == [r["v_j"] for r in fvagg.jitter(rows, "v", amount=0.2, mode="even", seed=9)],
        "even 模式不应依赖 seed",
    )
    # by 分组各自摊开：a/b 各 2 行 → delta ±0.1
    evg = fvagg.jitter(rows, "v", by="g", amount=0.2, mode="even")
    check(
        "jit-even-by",
        sorted(round(r["v_j"] - r["v"], 9) for r in evg if r["g"] == "a") == [-0.1, 0.1]
        and sorted(round(r["v_j"] - r["v"], 9) for r in evg if r["g"] == "b")
        == [-0.1, 0.1],
        f"{[(r['g'], r['v_j']) for r in evg]}",
    )
    # 类别 col 按行序落位：a 组行 [r0,r2] → -0.2,+0.2；b 组同
    evc = fvagg.jitter(rows, "g", by="g", amount=0.4, mode="even", name="xj")
    pos = {"a": 0, "b": 1}
    check(
        "jit-even-cat",
        [round(r["xj"] - pos[r["g"]], 9) for r in evc] == [-0.2, -0.2, 0.2, 0.2],
        f"{[(r['g'], r['xj']) for r in evc]}",
    )
    # 单行组落 bin 中心 = 窗中点
    one = fvagg.jitter([{"v": 1.0}], "v", amount=(0.0, 0.14), mode="even")
    check("jit-even-single-mid", abs(one[0]["v_j"] - 1.07) < 1e-9, f"{one}")
    try:
        fvagg.jitter(rows, "v", mode="tri")
        check("jit-bad-mode", False, "no raise")
    except ValueError:
        check("jit-bad-mode", True)


def ranking():
    rows = [
        {"m": "a", "s": 0.9},
        {"m": "b", "s": 0.7},
        {"m": "c", "s": 0.95},
    ]
    out = fvagg.rank(rows, "s")
    check(
        "rank-basic",
        [(r["m"], r["rank"]) for r in out] == [("a", 2), ("b", 3), ("c", 1)]
        and "rank" not in rows[0],
        f"{[(r['m'], r['rank']) for r in out]}",
    )
    check(
        "rank-asc",
        [r["rank"] for r in fvagg.rank(rows, "s", order="asc")] == [2, 1, 3],
        f"{[r['rank'] for r in fvagg.rank(rows, 's', order='asc')]}",
    )
    tied = [{"s": 0.9}, {"s": 0.9}, {"s": 0.7}]
    for ties, want in [
        ("min", [1, 1, 3]),
        ("dense", [1, 1, 2]),
        ("average", [1.5, 1.5, 3]),
        ("first", [1, 2, 3]),
    ]:
        got = [r["rank"] for r in fvagg.rank(tied, "s", ties=ties)]
        check(f"rank-ties-{ties}", got == want, f"{ties}: {got} want {want}")
    stages = [
        {"m": "a", "t": "s1", "s": 0.9},
        {"m": "b", "t": "s1", "s": 0.8},
        {"m": "a", "t": "s2", "s": 0.5},
        {"m": "b", "t": "s2", "s": 0.6},
    ]
    by = fvagg.rank(stages, "s", by="t")
    check(
        "rank-by",
        [(r["m"], r["t"], r["rank"]) for r in by]
        == [("a", "s1", 1), ("b", "s1", 2), ("a", "s2", 2), ("b", "s2", 1)],
        f"{[(r['m'], r['t'], r['rank']) for r in by]}",
    )
    try:
        fvagg.rank([{"s": float("nan")}], "s")
        check("rank-nan", False, "no raise")
    except ValueError:
        check("rank-nan", True)
    try:
        fvagg.rank(rows, "s", ties="bogus")
        check("rank-bad-ties", False, "no raise")
    except ValueError:
        check("rank-bad-ties", True)


def main():
    coerce()
    agg_basic()
    agg_edges()
    keyed()
    cells()
    csv_roundtrip()
    derived()
    pareto()
    calib()
    jit()
    ranking()
    print(f"--- done, {len(FAILS)} failed ---")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
