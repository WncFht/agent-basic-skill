#!/usr/bin/env python3
r"""check_coverage.py — 对 figure .tex 源码做静态审计覆盖扫描。

  check_coverage.py FILE.tex

走查每条 \node/\draw/\path/\fill/\filldraw/\pic 语句（一条语句到
depth-0 的 ';' 为止，可跨行）。当审计机制能看到它时，该语句算
COVERED：

  - 语句自身带 'vaudit=' style 键                  （node/region 导出）
  - 经由 style 触及 'vaudit='：name/.style= 或 name/.append style=
    的 body 内含 'vaudit='（在 \tikzset 块、picture 选项或内联 defs
    里）就标记该 style；在语句的 option 键里用它就算已埋点。建立在
    审计 style 之上的 style 传递继承，'every node' 带 vaudit 则覆盖
    每个 \node。定义点单独收集——style body 里的 vaudit= 本身不算
    某条语句的埋点，只有使用才算。
  - 其 node/pic 名被某处 '\path \vaudit{N}{..}' 重打 tag，或被某条
    '\vzbbox{N}{..}{..}' region 行承载
  - \draw/\path/\filldraw：每个具名引用都出现在某条 \vzwire 的
    waypoints/endpoint=/via= 名中（connector 被 wire 镜像）
  - \fill/\draw rectangle 两角等于某 \vzbbox 的两角
    （即文档化的 '\fill[band] (sw) rectangle (ne)' + \vzbbox 对）
  - \pic：其 (name) 像 node 一样被重打 tag/\vzbbox——solid 方言 pic
    （ssolid）不自我注册，须显式 name + \vzbbox

语句级豁免只覆盖 path 墨迹：嵌在本来干净的语句里的 'node' op 是
独立墨迹，单独检查——每个带非空文本或可见墨迹（fill=/shade=/
pattern= 键，或 draw= 非 'none'）的嵌入 node 都需要在自己 options
里带 'vaudit='（直接或经审计 style）、名字被 \vaudit/\vzbbox 重打
tag，或吃到语句的 '% fv:noaudit' / off-region 豁免。
与 TeX 语义一致的例外：带 vaudit 的 path 恰好只审计其上最后排版
的那个 node（append after command 只触发一次），所以最后一个嵌入
node 继承 path 的 vaudit，更早的嵌入 node 仍需自己的。

其余一切被画出的东西都是几何审计看不到的语义对象：
  warn coverage: line N: <stmt>

内置降噪：

  - \coordinate 语句不是被画出的对象                      （跳过）
  - 文本组为空且不画墨迹的 \node 语句                    （跳过——
    无 fill=/shade=/pattern= 键、无 draw=none 以外的 draw=、无带
    文本的 label=/pin= 子项；填了色或带标签的空 node 仍是墨迹，
    与其他 node 一样需要 vaudit）
  - 什么都不画且无文本 node 的 \path 语句                （跳过）
  - 装饰性语句：option 键全部出自 vizstyle 的装饰集
    {lead,vbrace,vcurly} 或 'grid' path 操作，且不出现语义性
    vizstyle 键（varr/inh/model/card/mdot/msq/lab/gtag/gcell/
    mean/band/vstage/vsym/vshape/vnote 均失格）且语句不带文本
    墨迹——其中任何非空 node 文本或 label=/pin=
  - '% fv:noaudit'  在语句任一行行尾                     （豁免）
  - '% fv:coverage off' ... '% fv:coverage on'            （区间豁免）

输出行为 'warn coverage: <msg>'；恒退出 0（仅 warn），
文件缺失/用法错误时退出 2。
"""

import argparse
import re
import sys
from pathlib import Path

# 开启一条语句的绘制命令；\coordinate 会被扫到但跳过
DRAW_RE = re.compile(r"\\(node|draw|path|filldraw|fill|coordinate|pic)\b")
COMMENT_RE = re.compile(r"%")

# vizstyle.tex 样式名 ------------------------------------------------------------
DECOR_KEYS = {"lead", "vbrace", "vcurly"}  # 细引线/花括号
SEMANTIC_KEYS = {
    "varr",
    "inh",
    "model",
    "card",
    "mdot",
    "msq",
    "lab",
    "gtag",
    "gcell",
    "mean",
    "band",
    "vstage",
    "vsym",
    "vshape",
    "vnote",
    # recipes 族（references/tikz/recipes.md）：pgm / nn / seq / 搜索树
    "lat",
    "obs",
    "const",
    "plate",
    "plab",
    "vadd",
    "nskip",
    "nskipe",
    "lifeline",
    "act",
    "snkeep",
    "snghost",
    "snret",
    "snroot",
}
GRID_RE = re.compile(r"\bgrid\s*[\(\[]")

AUDIT_CMD_RE = re.compile(r"\\(?:vaudit\s*\{|vzbbox\s*\{|vzwire\s*\{)")
# vaudit= 也可经 pgfkeys handler 链命中——vaudit/.expand once=、
# vaudit/.expanded=、'=' 之前任意 '/.<handler>(args)' 段。
VAUDIT_KEY_RE = re.compile(r"\bvaudit(?:\s*/[^=,{}\[\]]+)*\s*=")

# body 内可能携带 vaudit= 的 style 定义：name/.style={...}、
# name/.append style={...}，出现在 \tikzset 块或任意 option 列表中；
# 已废弃的 \tikzstyle{name}=[...] 形式在下方单独收集。
STYLE_DEF_RE = re.compile(
    r"([A-Za-z0-9_@. -]+?)\s*/\.(?:append style|prefix style|style)\s*="
)
TIKZSTYLE_RE = re.compile(r"\\tikzstyle\s*\{([^{}]*)\}\s*=\s*\[")

VAUDIT_RE = re.compile(r"\\vaudit\s*\{([^}]*)\}")
VZBBOX_RE = re.compile(r"\\vzbbox\s*\{")
VZWIRE_RE = re.compile(r"\\vzwire\s*\{[^}]*\}\s*\{([^}]*)\}\s*\{([^}]*)\}")

PAREN_RE = re.compile(r"\(([^()]*)\)")
# 多词锚点是合法 tikz：(l1.north east)、(a.south west)——基础名仍取
# 首个 '.' 之前的部分
NAME_RE = re.compile(r"^[A-Za-z_][\w@. -]*$")
CALC_NAME_RE = re.compile(r"\(([A-Za-z_][\w@.]*)\)")
RECT_RE = re.compile(r"(\([^()]*\))\s*rectangle\s*(\([^()]*\))")
NODE_RE = re.compile(r"\bnode\b")

NOAUDIT = "fv:noaudit"
COV_OFF = "fv:coverage off"
COV_ON = "fv:coverage on"


def split_comment(line):
    """(code, comment)——未被反斜杠转义的 % 是注释起点。"""
    for m in COMMENT_RE.finditer(line):
        i = m.start()
        bs = 0
        while i - bs - 1 >= 0 and line[i - bs - 1] == "\\":
            bs += 1
        if bs % 2 == 0:
            return line[:i], line[i:]
    return line, ""


def norm_ws(s):
    return " ".join(s.split())


def norm_coord(s):
    return re.sub(r"\s+", "", s)


def opt_keys(stmt):
    """语句首个 [..] 块内 depth-0 逗号分隔的键集合。"""
    m = re.search(r"\[", stmt)
    if not m:
        return set()
    depth, start = 0, m.start()
    for i in range(start, len(stmt)):
        if stmt[i] == "[":
            depth += 1
        elif stmt[i] == "]":
            depth -= 1
            if depth == 0:
                body = stmt[start + 1 : i]
                keys = set()
                for piece in body.split(","):
                    piece = piece.strip()
                    if not piece:
                        continue
                    keys.add(piece.split("=")[0].strip())
                return keys
    return set()


def opt_body(stmt):
    """语句首个 [..] option 块的 body（缺省 ''）。"""
    m = re.search(r"\[", stmt)
    if not m:
        return ""
    j = _match(stmt, m.start(), "[", "]")
    return stmt[m.start() + 1 : j] if j >= 0 else stmt[m.start() + 1 :]


def split_opts(body):
    """按 depth-0 逗号切 option 片段——'{..}','[..]','(..)' 屏蔽值内
    逗号（label={a,b}）。"""
    parts, cur, depth = [], [], 0
    for ch in body:
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])" and depth:
            depth -= 1
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def inks_node(opts):
    """option body -> node 即使文本为空也画墨迹：fill=/shade=/pattern=
    键，或 draw= 非 'none'。"""
    for piece in split_opts(opts):
        k, _, v = piece.partition("=")
        k, v = k.strip(), v.strip()
        if k in {"fill", "shade", "pattern"} or (k == "draw" and v != "none"):
            return True
    return False


def _label_text(v):
    """label=/pin= 值 -> 其排版文本：剥掉前缀 '[opts]' 块与 depth-0
    'pos:' 前缀，再解一层 {}。"""
    v = v.strip()
    if v.startswith("["):
        j = _match(v, 0, "[", "]")
        v = v[j + 1 :].strip() if j >= 0 else ""
    depth = 0
    for i, ch in enumerate(v):
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif ch == ":" and depth == 0:
            v = v[i + 1 :].strip()
            break
    if v.startswith("{") and _match(v, 0, "{", "}") == len(v) - 1:
        v = v[1:-1].strip()
    return v


def label_ink(opts):
    """option body -> node 带非空 label=/pin= 子项——即使自身 {} 组
    为空，那文本也是真墨迹。"""
    for piece in split_opts(opts):
        k, _, v = piece.partition("=")
        if k.strip() in {"label", "pin"} and _label_text(v):
            return True
    return False


def name_refs(stmt):
    """形如 (name)/(name.anchor) 的引用 + $(calc)$ 内的名字。"""
    out = set()
    for content in PAREN_RE.findall(stmt):
        content = content.strip()
        if content.startswith("$"):
            out.update(n.split(".")[0] for n in CALC_NAME_RE.findall(content))
        elif NAME_RE.match(content):
            out.add(content.split(".")[0])
    return out


def wire_names(text):
    """\vzwire 的 waypoints 与 endpoint=/via= tags 提到的全部节点名。"""
    out = set()
    for wps, tags in VZWIRE_RE.findall(text):
        for wp in wps.split(";"):
            wp = wp.strip()
            if not wp:
                continue
            if wp.startswith("("):
                out.update(name_refs(wp))
            else:
                out.add(wp.split(".")[0])
        for clause in tags.split():
            k, _, v = clause.partition("=")
            if k.strip() in {"endpoint", "via"}:
                out.update(n.strip().split(".")[0] for n in v.split(","))
    return out


def vzbbox_rows(text):
    """每条 \\vzbbox{name}{a}{b} -> (name, corner_a, corner_b)——corner
    实参可含带嵌套括号的 calc '$(...)$' 段，所以三个实参靠花括号配对
    取出，不用扁平正则。"""
    out = []
    for m in VZBBOX_RE.finditer(text):
        i = m.end() - 1
        args = []
        while len(args) < 3 and i < len(text) and text[i] == "{":
            j = _match(text, i, "{", "}")
            if j < 0:
                break
            args.append(text[i + 1 : j])
            i = _skip_ws(text, j + 1)
        if len(args) == 3:
            out.append((args[0], args[1], args[2]))
    return out


def bbox_pairs(text):
    return {(norm_coord(a), norm_coord(b)) for _n, a, b in vzbbox_rows(text)}


def region_names(text):
    return {n.strip() for n, _a, _b in vzbbox_rows(text)}


def rect_pair(stmt):
    m = RECT_RE.search(stmt)
    if not m:
        return None
    return norm_coord(m.group(1)), norm_coord(m.group(2))


def node_name(stmt):
    """裸 \\node 语句的名字；stmt body 形如 '[opts] (name) at .. {..}'
    （\\node 命令本身已被 scan 消费，不在 stmt 内）。"""
    m = re.match(r"\s*(?:\[[^]]*\])?\s*\(([^)]+)\)", stmt)
    return m.group(1).strip() if m else None


def empty_node(stmt):
    """语句最后一个 {} 组（node 文本）为空/缺失时为 true。

    node 文本是 ';' 之前最后一个花括号组——针对裸 \node 语句。混合
    'node{real}' 与 'node{}' 的语句仍算有文本。
    """
    has_text = False
    i = 0
    while True:
        j = stmt.find("{", i)
        if j < 0:
            return not has_text
        depth = 1
        k = j + 1
        while k < len(stmt) and depth:
            if stmt[k] == "{":
                depth += 1
            elif stmt[k] == "}":
                depth -= 1
            k += 1
        if stmt[j + 1 : k - 1].strip():
            has_text = True
        i = k


def drawn_path(stmt):
    """\\path 语句是否产生墨迹：draw/fill 选项或 node 文本。"""
    keys = opt_keys(stmt)
    if keys & {"draw", "fill", "filldraw", "shade", "pattern", "clip"}:
        return True
    return NODE_RE.search(stmt) is not None and not empty_node(stmt)


def text_ink(stmt, kind):
    """语句带有装饰豁免不得掩盖的真实文本墨迹：\\node 自身的非空
    文本或 label=/pin=，或带非空文本 / label=/pin= 的嵌入 node op。
    （颜料墨迹——fill/shade/draw——不计入这里；带颜料墨迹的嵌入 node
    单独审计。）"""
    if kind == "node" and (not empty_node(stmt) or label_ink(opt_body(stmt))):
        return True
    for eopts, _n, etext, _s in embedded_nodes(stmt):
        if etext.strip() or label_ink(eopts):
            return True
    return False


def is_decorative(stmt, kind):
    keys = opt_keys(stmt)
    if keys & SEMANTIC_KEYS:
        return False
    if not (keys & DECOR_KEYS or GRID_RE.search(stmt)):
        return False
    return not text_ink(stmt, kind)


def _match(s, i, open_ch, close_ch):
    """闭合 s[i]==open_ch 的定界符下标；不配对时返回 -1。"""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == open_ch:
            depth += 1
        elif s[j] == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return -1


def _skip_ws(s, i):
    while i < len(s) and s[i] in " \t\n":
        i += 1
    return i


def strip_brace_text(stmt):
    """剥掉每个配对 {...} 组后的语句（感知嵌套）。

    花括号体是排版出的 node 文本或键值体——其中的括号是字面标签
    字符，绝不是坐标或名字引用。option 列表 [...] 原样保留，所以
    'at (...)' / '($...$)' / 'of=' 子句仍会被扫描。不配对的尾部
    原样保留而非丢弃。
    """
    out, i = [], 0
    while True:
        j = stmt.find("{", i)
        if j < 0:
            return "".join(out) + stmt[i:]
        out.append(stmt[i:j])
        k = _match(stmt, j, "{", "}")
        if k < 0:
            return "".join(out) + stmt[j:]
        i = k + 1


def audit_styles(text):
    """body 内携带 'vaudit=' 的 /.style=/..append style= style 名。

    凡模式出现处都收集定义（\\tikzset 块、tikzpicture option 列表、
    内联语句 options）；body 只引用另一个审计 style 的 style 传递继承
    该 tag。
    """
    defs = []
    for m in STYLE_DEF_RE.finditer(text):
        name = m.group(1).strip()
        i = _skip_ws(text, m.end())
        if i < len(text) and text[i] == "{":
            j = _match(text, i, "{", "}")
            body = text[i + 1 : j] if j >= 0 else text[i + 1 :]
        else:  # 无花括号 body 延伸到下一个逗号
            j = text.find(",", i)
            body = text[i:] if j < 0 else text[i:j]
        defs.append((name, body))
    for m in TIKZSTYLE_RE.finditer(text):
        j = _match(text, m.end() - 1, "[", "]")
        defs.append(
            (m.group(1).strip(), text[m.end() : j] if j >= 0 else text[m.end() :])
        )
    tagged = {n for n, b in defs if VAUDIT_KEY_RE.search(b)}
    changed = True
    while changed:  # keep/.style={beam, ...} 继承 beam 的审计
        changed = False
        for n, b in defs:
            if n in tagged:
                continue
            keys = {p.split("=")[0].strip() for p in b.split(",")}
            if keys & tagged:
                tagged.add(n)
                changed = True
    return tagged


def embedded_nodes(stmt):
    """语句 body 内每个 'node' op 的 (opts, name, text, src)。

    宽松解析 'node[opts] (name) at (coord) {text}'——option/name/at
    子句可按任意次序重复；src 是该 node 的原始源码片段。只有定界符
    深度 0 处的 'node' 关键字是真正的 path 级 op——{text}、(coords)
    或 [opts] 内的 'node' 字样（如字面文本 '{use node{x}}'、'every
    node'）不是 op，直接丢弃；后面跟不到 option/name/text 子句的
    关键字同样丢弃。
    """
    # 每个位置之前的定界符深度——真正的 node op 在 depth 0
    lvl = [0] * (len(stmt) + 1)
    d = 0
    for i, ch in enumerate(stmt):
        lvl[i] = d
        if ch in "{[(":
            d += 1
        elif ch in "}])":
            d -= 1
    out = []
    for m in NODE_RE.finditer(stmt):
        if lvl[m.start()] != 0:
            continue
        i = _skip_ws(stmt, m.end())
        opts, name, text, parsed = "", None, "", False
        while i < len(stmt):
            if stmt[i] == "[":
                j = _match(stmt, i, "[", "]")
                if j < 0:
                    break
                opts += stmt[i + 1 : j] + ","
                i = _skip_ws(stmt, j + 1)
            elif stmt[i] == "(":
                j = _match(stmt, i, "(", ")")
                if j < 0:
                    break
                if name is None:
                    name = stmt[i + 1 : j].strip()
                i = _skip_ws(stmt, j + 1)
            elif stmt[i] == "{":
                j = _match(stmt, i, "{", "}")
                text = stmt[i + 1 : j] if j >= 0 else stmt[i + 1 :]
                i = j + 1 if j >= 0 else len(stmt)
                parsed = True
                break
            elif stmt.startswith("at", i) and (
                i + 2 >= len(stmt) or not (stmt[i + 2].isalnum() or stmt[i + 2] in "_@")
            ):
                i2 = _skip_ws(stmt, i + 2)
                if i2 >= len(stmt) or stmt[i2] != "(":
                    break
                j = _match(stmt, i2, "(", ")")
                if j < 0:
                    break
                i = _skip_ws(stmt, j + 1)
            else:
                break
            parsed = True
        if parsed:
            out.append((opts, name, text, stmt[m.start() : i]))
    return out


def scan(src):
    """产出 (start_line, kind, text, line_set) 绘制语句。"""
    lines = src.splitlines()
    stmt = None  # [start, kind, parts, lines]
    depth = 0
    for i, raw in enumerate(lines):
        code, _ = split_comment(raw)
        pos = 0
        while True:
            if stmt is None:
                m = DRAW_RE.search(code, pos)
                if m is None:
                    break
                stmt = [i + 1, m.group(1), [], set()]
                pos = m.end()
            else:
                j = pos
                closed = -1
                while j < len(code):
                    ch = code[j]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                    elif ch == ";" and depth == 0:
                        closed = j
                        break
                    j += 1
                stmt[2].append(code[pos:j])
                stmt[3].add(i + 1)
                if closed >= 0:
                    yield stmt[0], stmt[1], " ".join(stmt[2]), stmt[3]
                    stmt = None
                    depth = 0
                    pos = closed + 1
                    continue
                break
    if stmt is not None:  # 未闭合的尾部——仍值得报告
        yield stmt[0], stmt[1], " ".join(stmt[2]), stmt[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tex", type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.tex.exists():
        print(f"no such file: {args.tex}", file=sys.stderr)
        return 2
    src = args.tex.read_text()
    lines = src.splitlines()

    # 逐行 region 状态 + noaudit 标记
    off = [False] * (len(lines) + 2)
    noaudit = [False] * (len(lines) + 2)
    state = False
    for i, raw in enumerate(lines):
        off[i + 1] = state
        _, comment = split_comment(raw)
        if NOAUDIT in comment:
            noaudit[i + 1] = True
        if COV_OFF in comment:
            state = True
        if COV_ON in comment:
            state = False

    # 剥注释供埋点正则用
    code_only = "\n".join(split_comment(ln)[0] for ln in lines)
    retag = {n.strip() for n in VAUDIT_RE.findall(code_only)}
    wires = wire_names(code_only)
    bboxes = bbox_pairs(code_only)
    regions = region_names(code_only)
    named = retag | regions  # 承载 node/region 审计行的名字
    tagged = audit_styles(code_only)  # 定义体内带 vaudit= 的 style

    total = 0
    warns = []
    for start, kind, text, touched in scan(src):
        total += 1
        if off[start] or any(noaudit[n] for n in touched):
            continue
        if kind == "coordinate":
            continue
        # 语句自己的 vaudit 必须在嵌入 node op 之外——先剥掉每个嵌入
        # node 的源码再测，否则 'node[vaudit]' 会把外围 path 也豁免
        nodes = embedded_nodes(text)
        stmt_text = text
        for _e, _n, _t, esrc in nodes:
            stmt_text = stmt_text.replace(esrc, "", 1)
        # 语句自己的 options 只认开头的 [..] 块——嵌入 node 的 [opts]
        # 不得把整条 path 标记成已审计
        keys = opt_keys(stmt_text) if stmt_text.lstrip().startswith("[") else set()
        stmt_va = (
            VAUDIT_KEY_RE.search(stmt_text) is not None
            or bool(keys & tagged)
            or (kind == "node" and "every node" in tagged)
        )
        # 嵌入 'node' op：自带墨迹，即使语句本身豁免或已覆盖也要查。
        # 带 vaudit 的 path 只审计其最后一个 node（TeX append-after-
        # command 语义）。
        for k, (eopts, ename, etext, esrc) in enumerate(nodes):
            if not etext.strip() and not inks_node(eopts) and not label_ink(eopts):
                continue
            ecov = (
                VAUDIT_KEY_RE.search(eopts) is not None
                or bool(opt_keys("[" + eopts + "]") & tagged)
                or "every node" in tagged
                or (ename is not None and ename in named)
                or (k == len(nodes) - 1 and stmt_va)
            )
            if not ecov:
                warns.append(
                    f"line {start}: \\{kind} embeds unaudited node {norm_ws(esrc)[:72]}"
                )
        if AUDIT_CMD_RE.search(text):
            continue
        if stmt_va:
            continue
        if is_decorative(text, kind):
            continue
        covered = False
        if kind == "node":
            if (
                empty_node(text)
                and not inks_node(opt_body(text))
                and not label_ink(opt_body(text))
            ):
                continue
            name = node_name(text)
            covered = name is not None and name in named
        elif kind == "pic":
            name = node_name(text)
            covered = name is not None and name in named
        elif kind == "path":
            if not drawn_path(text):
                continue
            bare = strip_brace_text(text)
            names = name_refs(bare)
            pair = rect_pair(bare)
            covered = (names and names <= wires) or (
                pair is not None and (pair in bboxes or pair[::-1] in bboxes)
            )
        else:  # draw / filldraw / fill
            bare = strip_brace_text(text)
            names = name_refs(bare)
            pair = rect_pair(bare)
            covered = (names and names <= wires) or (
                pair is not None and (pair in bboxes or pair[::-1] in bboxes)
            )
        if not covered:
            snippet = norm_ws(text)[:72]
            warns.append(f"line {start}: \\{kind} {snippet}")

    if not args.quiet:
        print(f"{args.tex.name}: {total} drawing statements scanned")
    for w in warns:
        print(f"  warn coverage: {w}")
    if not warns:
        print("  all drawing statements audited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
