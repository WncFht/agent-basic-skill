"""fvagg.py — spec 数据契约的上游：原始记录 → 预聚合行。

fvspec 只消费预聚合表（rows/columns/csv/{fields,map}），本模块把实验
脚本里反复手写的聚合 glue 固化成 stdlib helper——group-by 聚合、
tuple-key dict 炸行、网格完整性检查、csv round-trip、派生列。
不引入 DataFrame：rows 一律 list[dict]，与 spec 的 data.rows 契约
零阻抗。纯 stdlib（csv/statistics/collections），实验脚本不需要
numpy——mpl 只出现在渲染侧。

    import fvagg
    rows = fvagg.agg_rows(raw, keys=["arm", "K"],
                          aggs={"med": ("kl", "median"),
                                "q25": ("kl", "q25"),
                                "q75": ("kl", "q75"),
                                "n":   ("kl", "n")})
    spec = {"data": {"grid": rows}, ...}

统计量：n/mean/median/q25/q75/min/max/std，或任意 callable(list)->数。
q25/q75 用 statistics.quantiles(n=4, method="inclusive")，与
np.quantile 默认 linear 法一致；std 在单点组取 0.0（组内无散布
可言），median/min/max 单点组取该点。

csv round-trip：dump_csv 写出的表经 load_csv 读回，与经 fvspec 的
{csv: path} 入口读回完全一致——两侧共用 coerce_cell。bool 落盘写
'true'/'false'；csv 没有 None 表示：None 写空串、读回 ''——含
None 的列请走 rows/columns 形，不要落 csv。

诊断/派生 helper：pareto_front 两目标支配过滤（默认产 on_front 布
尔列，一份数据集同时喂散点分色与 `where:{on_front:true}` 前沿折线；
mark=None 时只返回前沿子集）；calibration_bins 可靠性分箱（等宽/等
质量、bin-mean/bin-center 两种 x 约定、顺带 ECE/MCE）；jitter 点层
抖动列物化（strip/raincloud）；rank 组内名次列（bump 图）。全部纯
函数：返回新行副本，不改输入。数值字段遇 float NaN 一律响亮报错
——NaN 进 sort/比较会静默污染结果。
"""

from __future__ import annotations

import bisect
import csv
import math
import random
import statistics
from pathlib import Path

__all__ = [
    "add_field",
    "agg_rows",
    "calibration_bins",
    "cells_present",
    "coerce_cell",
    "dump_csv",
    "jitter",
    "keyed_to_rows",
    "load_csv",
    "pareto_front",
    "rank",
]

STATS = ("n", "mean", "median", "q25", "q75", "min", "max", "std")


def coerce_cell(s):
    """CSV cell coercion: int -> float -> bool -> str。

    fvspec 的 {csv: path} 入口逐字同语义——round-trip 恒等的根基。
    """
    try:
        return int(s)
    except (ValueError, TypeError):
        pass
    try:
        return float(s)
    except (ValueError, TypeError):
        pass
    if isinstance(s, str) and s.lower() in ("true", "false"):
        return s.lower() == "true"
    return s


def _stat(vals, stat):
    if callable(stat):
        return stat(vals)
    if stat == "n":
        return len(vals)
    if stat == "mean":
        return statistics.fmean(vals)
    if stat == "median":
        return statistics.median(vals)
    if stat in ("q25", "q75"):
        if len(vals) < 2:
            return vals[0]
        qs = statistics.quantiles(vals, n=4, method="inclusive")
        return qs[0] if stat == "q25" else qs[2]
    if stat == "min":
        return min(vals)
    if stat == "max":
        return max(vals)
    if stat == "std":
        return statistics.stdev(vals) if len(vals) > 1 else 0.0
    raise ValueError(f"unknown stat {stat!r} (one of {STATS} or a callable)")


def agg_rows(rows, keys, aggs):
    """group-by 聚合 → spec 就绪行。

    rows: list[dict] 原始记录；keys: 分组字段名列表；aggs:
    {输出列：输入列 | (输入列，统计量) | (输入列，callable)}——裸字段名
    默认 median。每组产一行 {key…, 输出列…}；行序按 key 元组排序，
    不可比 key（混合类型）退回首见序。
    """
    groups = {}
    order = []
    for r in rows:
        k = tuple(r[f] for f in keys)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    try:
        order = sorted(order)
    except TypeError:
        pass  # 混合类型 key 无法排序——首见序兜底
    out = []
    for k in order:
        grp = groups[k]
        row = dict(zip(keys, k))
        for col, spec in aggs.items():
            if isinstance(spec, (tuple, list)):
                if len(spec) != 2:
                    raise ValueError(f"agg {col!r}: (field, stat) 需要两项")
                field, stat = spec
            else:
                field, stat = spec, "median"
            vals = [r[field] for r in grp]
            row[col] = _stat(vals, stat)
        out.append(row)
    return out


def keyed_to_rows(fmap, fields):
    """{tuple_key: metric_dict} → list[dict] 行。

    fvspec {fields,map} 消费的镜像：实验代码里最自然的累积结构
    res[(arm,lev,K)] = {"med":.., "q25":..} 直接炸成平铺行。fmap 键
    可为 tuple/list（按 fields 逐项命名）；fields 只给一列时标量键
    也合法。
    """
    out = []
    for k, v in fmap.items():
        ks = k if isinstance(k, (list, tuple)) else (k,)
        if len(ks) != len(fields):
            raise ValueError(f"key {k!r} 有 {len(ks)} 段，fields 给了 {len(fields)} 列")
        out.append(dict(zip(fields, ks)) | dict(v))
    return out


def cells_present(rows, x="x", y="y"):
    """(x,y) 笛卡尔积里缺席的组合列表；空 list = 满格。

    heat 长表形进 spec 前的自查：缺格会被画成 mist 空洞——真稀疏
    （补 None 占位）还是漏跑（删列/补数据）由调用方决定，但先要知道
    缺了哪些。
    """
    xs = list(dict.fromkeys(r[x] for r in rows))
    ys = list(dict.fromkeys(r[y] for r in rows))
    seen = {(r[x], r[y]) for r in rows}
    return [(a, b) for a in xs for b in ys if (a, b) not in seen]


def add_field(rows, name, fn):
    """派生列：返回 [{**r, name: fn(r)}]，不原地改原行。"""
    return [{**r, name: fn(r)} for r in rows]


def _check_no_nan(rows, fields, who):
    for r in rows:
        for f in fields:
            v = r[f]
            if isinstance(v, float) and math.isnan(v):
                raise ValueError(f"{who}: 字段 {f!r} 含 NaN")


def _group_keys(rows, keys):
    """按 keys 分组的 (key -> rows) dict，组序为首见序。"""
    groups = {}
    order = []
    for r in rows:
        k = tuple(r[f] for f in keys)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    return order, groups


def pareto_front(rows, x, y, senses=("min", "max"), by=None, mark="on_front"):
    """两目标帕累托前沿过滤。

    senses: (x 方向，y 方向)，各取 'min'|'max'——'min' 表示该目标越小越
    好，四种组合全支持。支配语义：行 p 支配行 q 当且仅当 p 在两目标上
    都不劣于 q 且至少一处严格更优；(x,y) 完全相同的重复点只留首行——
    前沿折线本来也画不出重影点。
    by: 分组字段名或字段名列表，各组独立求前沿（多族前沿场景）。
    mark: 布尔输出列名——返回全行副本加该列，行序与输入一致；这是默
    认形态，一份数据集经 `where:{mark:true}` 出前沿折线、经
    `by:mark` 出前沿/被支配双色散点。mark=None 时只返回前沿子集
    （全字段副本），组内按 x 升序、组间按组首见序。

    x/y 须为数值；float NaN 响亮报错。spec 侧前沿线配
    `draw:'steps-post'`：min-x 前沿的可达域在曲线右下（post 正确）；
    max-x 前沿阶梯方向相反，按可达域语义换 'steps-pre'。
    """
    xs, ys = senses
    for s in (xs, ys):
        if s not in ("min", "max"):
            raise ValueError(f"pareto_front: senses 取 'min'/'max'，收到 {senses!r}")
    keys = [by] if isinstance(by, str) else list(by or [])
    _check_no_nan(rows, (x, y), "pareto_front")
    order, groups = _group_keys(rows, keys)
    front_ids = set()
    front_rows = []
    for k in order:
        grp = groups[k]
        # 稳定排序两轮：先 y 偏好向再 x 偏好向——同 x 时最优 y 先扫到
        scan = sorted(grp, key=lambda r: r[y], reverse=(ys == "max"))
        scan = sorted(scan, key=lambda r: r[x], reverse=(xs == "max"))
        best = None
        front = []
        for r in scan:
            v = r[y]
            if best is None or (v > best if ys == "max" else v < best):
                best = v
                front_ids.add(id(r))
                front.append(r)
        front.sort(key=lambda r: r[x])
        front_rows.extend(front)
    if mark is None:
        return [dict(r) for r in front_rows]
    return [{**r, mark: id(r) in front_ids} for r in rows]


def calibration_bins(
    rows,
    conf,
    acc,
    bins=10,
    strategy="width",
    x="mean",
    empty="skip",
    domain=(0.0, 1.0),
):
    """可靠性/校准分箱 → (spec 就绪行，汇总统计)。

    rows: 每行一个样本；conf: 置信度字段名；acc: 逐样本正确性字段名
    （0/1、bool 或 [0,1] 软标签，箱内取均值）。
    bins: 箱数 M。strategy: 'width' 在 domain=(lo,hi) 上等宽 | 'mass'
    等质量（样本分位数作边界，conf 堆积处可出零宽箱→空箱）。
    x: 输出 x 列取值约定——'mean' 箱内平均置信度（sklearn
    calibration_curve 惯例，偏斜置信分布下横坐标诚实）| 'center' 箱
    中点（Guo 柱状 reliability diagram 惯例）。
    empty: 'skip' 丢空箱 | 'keep' 保留（n=0，acc/conf/se/gap=None，
    x 按 center 或 None 落）。
    domain: 仅 'width' 用；界外样本钳入边箱并计入 stats['oob']。

    返回 (bin_rows, stats)。bin_rows 每箱一行 {bin,lo,hi,center,x,
    conf,acc,n,se,gap}：conf=箱均值置信度、acc=箱均值正确率、
    se=sqrt(acc(1-acc)/n) 插值二项标准误、gap=conf-acc 有符号差距。
    stats={n,bins,nonempty,ece,mce,oob}: ECE=Σ_b n_b/N·|acc_b−conf_b|
    （恒按箱均值置信度计，与绘图 x 约定无关）、MCE=argmax_b|gap| 的
    有符号值；N=0 时 ece/mce=None、bin_rows=[]。
    """
    if strategy not in ("width", "mass"):
        raise ValueError(
            f"calibration_bins: strategy 取 'width'/'mass'，收到 {strategy!r}"
        )
    if x not in ("mean", "center"):
        raise ValueError(f"calibration_bins: x 取 'mean'/'center'，收到 {x!r}")
    if empty not in ("skip", "keep"):
        raise ValueError(f"calibration_bins: empty 取 'skip'/'keep'，收到 {empty!r}")
    if not isinstance(bins, int) or bins < 1:
        raise ValueError(f"calibration_bins: bins 须为正整数，收到 {bins!r}")
    _check_no_nan(rows, (conf, acc), "calibration_bins")
    n_total = len(rows)
    if n_total == 0:
        return [], {
            "n": 0,
            "bins": bins,
            "nonempty": 0,
            "ece": None,
            "mce": None,
            "oob": 0,
        }
    if strategy == "width":
        lo, hi = domain
        if not lo < hi:
            raise ValueError(f"calibration_bins: domain 需 lo<hi，收到 {domain!r}")
        w = (hi - lo) / bins
        edges = [lo + i * w for i in range(bins + 1)]
    else:
        vals = sorted(r[conf] for r in rows)
        cuts = (
            statistics.quantiles(vals, n=bins, method="inclusive")
            if len(vals) > 1
            else []
        )
        edges = [vals[0], *cuts, vals[-1]]
    binned = [[] for _ in range(bins)]
    oob = 0
    for r in rows:
        c = r[conf]
        if c < edges[0] or c > edges[-1]:
            oob += 1
        i = bisect.bisect_right(edges, c) - 1
        binned[max(0, min(i, bins - 1))].append(r)
    out = []
    ece = 0.0
    mce = None
    nonempty = 0
    for i, grp in enumerate(binned):
        lo_i, hi_i = edges[i], edges[i + 1]
        center = (lo_i + hi_i) / 2
        if not grp:
            if empty == "keep":
                out.append(
                    {
                        "bin": i,
                        "lo": lo_i,
                        "hi": hi_i,
                        "center": center,
                        "x": center if x == "center" else None,
                        "conf": None,
                        "acc": None,
                        "n": 0,
                        "se": None,
                        "gap": None,
                    }
                )
            continue
        nonempty += 1
        n = len(grp)
        mc = statistics.fmean(r[conf] for r in grp)
        ac = statistics.fmean(r[acc] for r in grp)
        se = (ac * (1 - ac) / n) ** 0.5
        gap = mc - ac
        ece += n / n_total * abs(gap)
        if mce is None or abs(gap) > abs(mce):
            mce = gap
        out.append(
            {
                "bin": i,
                "lo": lo_i,
                "hi": hi_i,
                "center": center,
                "x": mc if x == "mean" else center,
                "conf": mc,
                "acc": ac,
                "n": n,
                "se": se,
                "gap": gap,
            }
        )
    stats = {
        "n": n_total,
        "bins": bins,
        "nonempty": nonempty,
        "ece": ece,
        "mce": 0.0 if mce is None else mce,
        "oob": oob,
    }
    return out, stats


def jitter(
    rows, col, by=None, amount=0.1, seed=0, name=None, offset=0.0, mode="uniform"
):
    """物化一列抖动坐标（strip/raincloud 点层）。

    col 全数值时 base=原值（在该坐标上抖）；否则 base=类别索引（首见
    序 0 起，与 spec 类目轴 pos=enumerate(cats) 一致——数值型类别码
    想按类目位抖动请先经 add_field 落成位置列）。offset 平移 base：
    raincloud 单侧点带如 offset=0.08 + amount=(0,0.14)。
    amount 标量 → 窗 (-a,+a) 对称；二元组 (lo,hi) → 窗 (lo,hi)
    单侧/偏心。mode='uniform'（默认）：delta~U(lo,hi) seeded 随机流；
    by 分组字段名（列表）——每组一条独立随机流，种子由 (seed,
    组键 repr) 派生：组间增删行不改他组抖动，行序与过滤稳定。
    mode='even'：组内在窗内等距摊开（delta 取 bin 中心
    lo+(hi-lo)*(i+.5)/n，n 为组内行数）——确定性排版，与 seed 无关；
    数值 col 组内按值排序落位，类别 col 按行序落位；组内行数变化会
    整体重排点位（没有 uniform 的跨过滤稳定性）。
    name: 输出列名，缺省 f"{col}_j"。返回新行，不改原行。
    """
    if mode not in ("uniform", "even"):
        raise ValueError(f"jitter: mode 取 'uniform'/'even'，收到 {mode!r}")
    if isinstance(amount, (tuple, list)):
        lo, hi = amount
    else:
        lo, hi = -amount, amount
    name = name or f"{col}_j"
    keys = [by] if isinstance(by, str) else list(by or [])
    vals = [r[col] for r in rows]
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)
    if numeric:
        _check_no_nan(rows, (col,), "jitter")
    cat_pos = {}
    if not numeric:
        for v in vals:
            if v not in cat_pos:
                cat_pos[v] = len(cat_pos)

    def base(r):
        return r[col] if numeric else cat_pos[r[col]]

    if mode == "even":
        groups, order = {}, []
        for i, r in enumerate(rows):
            k = tuple(r[f] for f in keys) if keys else None
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(i)
        deltas = [0.0] * len(rows)
        for k in order:
            idx = groups[k]
            if numeric:
                idx = sorted(idx, key=lambda i: rows[i][col])
            m = len(idx)
            for j, i in enumerate(idx):
                deltas[i] = lo + (hi - lo) * (j + 0.5) / m
        return [{**r, name: base(r) + offset + deltas[i]} for i, r in enumerate(rows)]

    streams = {}
    out = []
    for r in rows:
        k = tuple(r[f] for f in keys) if keys else None
        if k not in streams:
            streams[k] = random.Random(f"{seed}" if k is None else f"{seed}|{k!r}")
        out.append({**r, name: base(r) + offset + streams[k].uniform(lo, hi)})
    return out


def rank(rows, col, by=None, order="desc", ties="min", name="rank"):
    """组内名次列（bump/排名图）。

    在 by 字段（列表）定义的每个组内按 col 排名；by=None 全表一组。
    order='desc' 最大者第 1（默认——分数/指标越大越好的通常语义），
    'asc' 最小者第 1。ties 并列处理：'min' 竞赛名次（1,2,2,4，默认）
    |'dense'（1,2,2,3）|'first'（组内首见序破并列，名次互异——sorted
    稳定序保证确定性）|'average'（并列取均值名次，可出 .5）。
    返回新行副本、原行序不变，name 列存名次（int 或 average 的 float）；
    col 含 float NaN 响亮报错（NaN 进 sort 静默乱序）。
    """
    if order not in ("desc", "asc"):
        raise ValueError(f"rank: order 取 'desc'/'asc'，收到 {order!r}")
    if ties not in ("min", "dense", "first", "average"):
        raise ValueError(f"rank: ties 取 min/dense/first/average，收到 {ties!r}")
    keys = [by] if isinstance(by, str) else list(by or [])
    _check_no_nan(rows, (col,), "rank")
    groups = {}
    order_k = []
    for i, r in enumerate(rows):
        k = tuple(r[f] for f in keys)
        if k not in groups:
            groups[k] = []
            order_k.append(k)
        groups[k].append(i)
    ranks = [None] * len(rows)
    for k in order_k:
        srt = sorted(groups[k], key=lambda i: rows[i][col], reverse=(order == "desc"))
        j = 0
        dense = 0
        while j < len(srt):
            v = rows[srt[j]][col]
            e = j + 1
            while e < len(srt) and rows[srt[e]][col] == v:
                e += 1
            for t in range(j, e):
                if ties == "first":
                    ranks[srt[t]] = t + 1
                elif ties == "min":
                    ranks[srt[t]] = j + 1
                elif ties == "dense":
                    ranks[srt[t]] = dense + 1
                else:
                    ranks[srt[t]] = (j + 1 + e) / 2
            dense += 1
            j = e
    return [{**r, name: ranks[i]} for i, r in enumerate(rows)]


def _csv_fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):  # 先于 int 判：bool 是 int 子类
        return "true" if v else "false"
    return v


def dump_csv(rows, path):
    """list[dict] → csv 文件。列 = 全行 key 的首见序并集；缺键写空串。

    float 走 str() 最短 repr，读回逐位相同；bool/None 见模块 docstring。
    返回 path 便于链式写 spec {csv: ...}。
    """
    keys = list(dict.fromkeys(k for r in rows for k in r))
    path = Path(path)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: _csv_fmt(r.get(k)) for k in keys})
    return str(path)


def load_csv(path):
    """csv → list[dict]，cell 经 coerce_cell——与 fvspec {csv} 入口同语义。"""
    with open(path, newline="") as f:
        return [{k: coerce_cell(v) for k, v in r.items()} for r in csv.DictReader(f)]
