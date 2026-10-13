# 覆盖扫描、渲染回读与调试覆盖图 — TikZ 审计三件套

vizaudit 只看得见埋过点的对象；三件套回答「埋点够不够、对不对、渲染出来撞没撞」：

- `check_coverage.py`：源文件里哪些画出来的东西审计根本看不见（未埋点）。
- `check_readback_tex.py`：渲染出的 PDF 里哪些文字实际越过了 audited 盒。
- `render_tex.py --overlay`：把审计视角画出来——每个埋点盒/声明线段叠在原图上。

三者全部 warn-only，不改 exit code；`render_tex.py` 默认在 check_audit 之后依次跑 coverage 与 readback，`--no-coverage` / `--no-readback` 可分别关闭。

## check_coverage.py — 源文件静态扫描

```
python3 scripts/check_coverage.py FIG.tex
```

按 statement 扫描 `\node/\draw/\path/\fill/\filldraw/\coordinate/\pic`（一条 statement 从命令词扫到花括号深度为 0 的 `;`，可跨行）。「已覆盖」判据按种类：

- 任何 statement 带 `vaudit=` key，或其选项引用的样式定义体（`.style`/ `.append style`/`\tikzstyle` 定义，含 `every node` 这类全局样式）里带 `vaudit=` → 该处已埋点。样式级 vaudit 按 TeX 语义只审路径上最后一个 typeset 的 node。
- `\node (名)` / `\pic (名)`：名字出现在文件任意 `\vaudit{名}{...}` 重标或 `\vzbbox{名}{..}{..}` 区域行里 → 已覆盖（solid 方言的 `ssolid` pic 不自注册，按惯例 `命名 + \vzbbox` 成对写）。
- `\draw/\path/\fill/\filldraw`：语句里所有 `(名字)` / `($...$)` calc 内引用的节点名都出现在某条 `\vzwire` 的途经点、`endpoint=` 或 `via=` 名单 → 连接器已被声明折线镜像。`via=` 的值就是逗号分隔的节点名名单（锚点后缀剥到基名）——导线要穿过自己路径上的标签盒时，把标签名写进 `via=` 即合法。
- 同一语句的 `rectangle` 两端坐标与某条 `\vzbbox` 的两角一致（顺序无关、空白归一化）→ 区域已注册。

`\draw/\path` 内嵌 `node` 操作（路径中段的 `node[opts] (name) at .. {text}`）是独立审计对象：语句级豁免只盖路径墨水，每个带非空文本的内嵌节点要在自己的 `[opts]` 里写 `vaudit=`——唯一例外是路径**最后一个**内嵌节点，按 TeX `append after command` 语义它继承整条路径的 `vaudit=`。

其余产生墨的 statement 报 `warn coverage: line N: \命令 <片段>`；始终 exit 0，文件缺失 exit 2。

### 内建降噪

| 情形                           | 处理                                                                          |
| ------------------------------ | ----------------------------------------------------------------------------- |
| `\coordinate`                  | 跳过——不是绘制对象                                                            |
| 文本为空的 `\node ... {}`      | 跳过——点标记 / fit 目标（仍是合法锚点）；但带 `fill=`/`shade=`/               |
|                                | `pattern=`/`draw=`（非 none）或带文本的 `label=`/`pin=`（含 `pin=60:t` 无括号 |
|                                | 写法）的空文本节点是真墨水，照常要 `vaudit=`                                  |
| 不画不填且无文字节点的 `\path` | 跳过                                                                          |
| 装饰语句                       | 跳过——选项只含 `lead/vbrace/vcurly` 或 `grid`                                 |
|                                | 操作、不出现任何语义样式 key，且语句无文字墨水                                |
|                                | （节点文本/label/pin 或内嵌文字节点——纯颜料墨水                               |
|                                | fill/draw 不挡豁免）                                                          |
| `% fv:noaudit`                 | 行尾豁免——落在 statement 任一行即整条豁免；                                   |
|                                | 自定义宏体内的 `\draw`/`\node` 字面量照样被                                   |
|                                | 扫（vizstyle.tex 自家宏不扫只是文件位置差异——                                 |
|                                | 扫描只覆盖目标文件），宏定义行挂 `% fv:noaudit`                               |
|                                | 是合法用法：每次展开的实例各有自己的                                          |
|                                | `\vzwire`/`\vaudit` 镜像承担审计                                              |
| `% fv:coverage off` … `on`     | 区域豁免——两行之间全部 statement 不扫                                         |

语义样式名单即 vizstyle 全套（`varr/inh/model/card/mdot/msq/lab/gtag/gcell/ mean/band/vstage/vsym/vshape/vnote` + recipes 族 `lat/obs/const/plate/plab/ vadd/nskip/nskipe/lifeline/act/snkeep/snghost/snret/snroot`）：装饰判定一见语义 key 即放弃豁免，所以 `\draw[lead]` 放行而 `\draw[varr]`、`\draw[nskip]` 必须配 `\vzwire`。

### 判定边界与已知局限

- `% fv:noaudit` / `% fv:coverage off` 只豁免 check_coverage 的静态扫描—— `check_readback_tex` 照样抓跨过 audited 盒的渲染文字，豁免注释管不住回读侧。
- `\node[label={..}] / pin=`：label/pin 带非空文本即算墨水（剥掉 `[opts]` 与 `pos:` 前缀判空，花括号写法与 `pin=60:t` 无括号写法都算）——要审计就给它埋 `vaudit=`（或 `% fv:noaudit`）。已知盲区：已审计节点身上的 `label=`/`pin=` 文本不是独立审计盒——label 压邻盒时覆盖扫描只管父节点已埋点，越界文字靠 readback 词盒兜底。
- `\vzbbox` 三个参数按花括号配对收取：角点写 calc `$(...)$`（含内层括号）同样注册——rectangle 四角配对与区域名重标都吃得到。
- WIRE-CROSS 穿深语义（check_audit 侧）：线段对盒的穿深取「弦端点 + 盒中线交点」上的 max——端点落在浅盒**对边**仍按 ~半盒高计穿腹，没有浅盒特例；只有停在近边（≤`--edge`，默认 2pt）的端点才豁免。跨薄盒的连线别把途经点钉在对边，要么写 `via=` 要么端点收在入边。
- `\foreach` 体内的 `\node/\draw` 按源码字面扫一次；体外的 `\vzwire/\vaudit` 引用是全文正则收集的，循环内声明同样有效——但循环展开出的多个实例只按一次判定，属可接受的 warn-only 近似。
- `\draw[vaudit]` 画在非 node 路径上：覆盖扫描当已埋点放行，TeX 侧 vizaudit 的 request/dump 平衡会单独警告（两条通道互补）。
- `vaudit={}` 空标签合法：只把盒子注册进审计（照常参与 COLLIDE/NEST/相切检查）、不进任何断言——无同伴等大/对齐要求的一次性对象用它。
- `vaudit` 的 pgfkeys handler 写法（`vaudit/.expand once={\mymacro}` 等）按已埋点识别；经宏间接传值 `vaudit={\mymacro}` 同样成立——`\write` 侧宏照常展开，扫描侧认 `vaudit=`。
- 纯坐标 `\draw`（`\draw (0,0)--(4,1)` 这类不引用任何节点名的轴线、泳道基线）永远过不了「名字 ⊆ wires」判据——先把端点 `\coordinate` 命名、让名字进 `\vzwire` 途经点；确实无审计价值的装饰线用 `% fv:noaudit`。轴断口斜杠、刻度小线、非语义描边这类纯坐标装饰线也不在装饰豁免内（豁免只认 `lead/vbrace/vcurly`/`grid` 选项且无文字墨水），逐条挂 `% fv:noaudit`。
- `\draw` 内嵌节点花括号文本先经 `strip_brace_text` 摘除（嵌套感知、只剥 `{...}` 组）再扫名字引用——`node[midway]{f(x)}` 的 `(x)` 不再伪造成节点名。残余：`[...]` 选项列表与 `($...$)` calc 不剥—— `pin=60:f(x)` 这类选项内非花括号文本里的圆括号仍会进名字集；花括号不闭合的语句按原文全扫。
- 垂足/正交坐标表达式（`(a |- b)`、`(0,3 |- node.east)`）的括号内容是坐标运算不是节点引用，扫描器解析不出其中的 `a`/`b`/`node`——需要这类落点的连线在落点处放一个命名 `\coordinate`，`\draw` 与 `\vzwire` 都引用这个名字。
- `\vzwire{名}{途经点}{}` 第三参数留空合法——两端裸坐标、无 `endpoint=`/`via=` 可声明的自由指示线、轴箭头用它完成镜像。
- `matrix` 单元格、`edge` 操作等派生绘制：扫描只看字面 statement，判据同 `\draw`——名字引用全被 `\vzwire` 提及才算镜像。
- `\pic` 按节点判据：`(名)` 被 `\vaudit`/`\vzbbox` 重标即覆盖；无名 pic 一律报——solid 方言的 pic 体内不注册外接盒，审计看不见就是看不见。
- 锚点引用支持多词锚名：`(l1.north east)`、`(a.south west)` 解析到 `l1`/ `a`——与 tikz 合法锚名一致。
- 豁免指令必须写在注释里且区分大小写；`% fv:coverage off` 忘记配 `on` 会静默豁免到文件尾——扫完没警告不一定是图干净，先看是不是整个后半段都在 off 区里。

## check_readback_tex.py — 渲染回读

```
python3 scripts/check_readback_tex.py FIG.pdf [FIG.audit] [--depth BP]
```

`pdftotext -bbox` 报每个 word 的真实包围盒（poppler 坐标：左上原点、y 向下、bp=1/72in）；.audit 的盒是 pgf 坐标（pt=1/72.27in）。两坐标系靠 vizaudit 在每个 tikzpicture 结束时写的 `origin` 行桥接（无 `|`，check_audit 忽略它）：

```
origin <picid> <picminx> <picminy> <picmaxx> <picmaxy> <paperw> <paperh>
```

origin 行回指到上一条 origin 之间的 audit 行。standalone 裁切下 `border = (page − pic)/2`，盒映射 `x_pop=(x−picminx)·s+bx`、 `y_pop=pageH−((y−picminy)·s+by)`，`s=72/72.27`。

规则（全 warn，exit 0）：

- word 盒与 audited 盒两轴相交深度都超过 `--depth`（默认 1bp）且未被该盒完全包住 → `warn readback: word "X" crosses audited box "N"`——文字压框线、骑边 straddle（词心在盒内同报，不再要求词心在盒外）、未审计对象撞上盒边的签名；整词没入盒内不报（盒内隐藏文字归覆盖扫描管），纯盒外或贴边 <depth 也不报。
- `\vzwire` 声明折线（与盒同映射到 poppler 坐标）任一段穿进 word 盒超过 `--depth` → `warn readback: wire "N" crosses word "X"`——连接器压字的回读签名；折线任一端点距该词盒 ≤2bp 视为正常接线，该 (wire, word) 对豁免。与盒检查同门槛：只在单 picture 干净裁切校准成立时跑。
- 同页两个 word 盒相交深度超过 `--depth` → `warn readback: word "X" overlaps word "Y" (N.Nbp)`——词压词签名（未审计文本互撞、标签叠标签），审计盒体系完全看不见的那类事故。
- word 盒完全在页面裁切外 → `warn readback: word "X" outside page`——裁切参数吃掉内容的信号。
- word 盒部分跨出页面裁切边（一头在内一头在外）→ `warn readback: word "X" clipped at page edge`——半裁字，比整盒越界更隐蔽。

可见字符（非空白且 Unicode 类不在 P/S）少于 2 的 word 直接跳过——数学 glyph、装饰符号是主要噪声源；CJK 两字以上正常参与。

### 校准边界与已知误报

- 只为「单 picture + 单页 standalone」校准：多 origin 行、多页 PDF、页面除图外还有内容 → warn 并跳过盒检查（页面外检查照跑）。
- 推导边框超过 40bp → 认为页面不止一张图，warn 提示映射近似但继续检查。
- .audit 缺失 → 只跑页面外检查；audit 无 origin 行 → warn 降级同上，常见原因是 vizaudit 在正文或 tikzpicture 内被 `\input`（守卫会响亮跳过）——它必须在导言区顶层引入；嵌套 picture（pgfplots axis、fit 节点、pic）不会写 origin，只有最外层 picture 写。
- 旋转 / sloped 文字：pdftotext 报渲染后轴对齐盒，斜字天然越出声明盒——带 rotate 的标签触发 crosses 属预期，目检取舍。
- 多字符数学排版词（`\rightarrow` 等的成品词）偶尔过 2 字符阈值触发误报——压不住时调 `--depth`。
- CJK 全角标点两侧：pdftotext 词盒含 em bearings，相邻词盒横向叠 ~5bp 报 word-overlaps——放大目检确认无实际压字后按误报略过。
- `pdftotext` 不在 PATH：warn 后整体跳过，exit 仍 0。

## --overlay — 把埋点画出来

```
python3 scripts/render_tex.py FIG.tex --overlay
# 统一入口：python3 scripts/render.py FIG.tex --overlay
```

第二遍编译：临时 wrapper 先 `\newif\ifvzoverlay\vzoverlaytrue` 再 `\input` 原文档，jobname 落在 `<stem>.overlay` → 产 `<stem>.overlay.pdf`：

- 每个 audited node/region：橙色虚线框 + SW 角 `\tiny\ttfamily` 名签。
- 每条 `\vzwire`：紫色虚线声明折线 + 两端圆点。

属调试产物：不进 exit code、不参与 `ok:` 判定；覆盖层编译失败只 `warn overlay:`，正文产物不受影响。

典型用途：声明几何 vs 实际渲染对不上时（盒歪、`via=` 漏声明、折线画短）一眼定位；也可直接当「机器看到的图」给协作方看。

vizaudit 侧 flag 由 `\@ifundefined{ifvzoverlay}` 守卫——wrapper 已置真时不重复 `\newif`；探测不要用 `\ifdefined`（它展开参数，而 `\ifvzoverlay` 本身是条件，会报 Incomplete）。
