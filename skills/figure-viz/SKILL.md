---
name: figure-viz
description: 渲染可审计的研究图，双引擎一套调色板：符号/结构/机制图走 TikZ 轨（张量块图、流水线泳道、通信并行、注意力掩码、时间线谱系、分类板设计空间、pgfplots 混合示意、伪 3D 立体块），真实数据图表走 matplotlib 轨（bar/donut/line/radar/scatter、hist/ecdf/kde/box/violin 分布族、contour/quiver 场族、sankey 流向、image 图版、sig 检验标注）。一句话路由：形状结构机制本身就是论证 → TikZ；数据驱动可复现图表 → matplotlib；编辑级通用架构图归 diagram-design，快速行内示意归 mermaid。
---

# figure-viz

把一条主张渲染成一张紧凑、编译级、机器可审计的图。图的存在理由是**论证**——让形状、结构或数据关系一眼可读；装饰和陈列性面板宁可删掉。

## 路由

- **TikZ 轨**：公式、张量形状、算法机制、谱系、设计空间——「形状/结构/机制本身就是论证」
- **matplotlib 轨**：有真实数据的图表（bar/donut/line/radar/scatter、hist/ecdf/kde/box/violin 分布族、contour/quiver 场族、sankey 流向、image 图版、sig 检验标注），可复现脚本
- 编辑级通用架构/流程图（HTML/SVG，无数学）→ `diagram-design`
- 笔记里快速结构示意 → mermaid fenced block
- 半定量（真实曲线叠示意结构）→ TikZ 轨 `references/tikz/plot.md` 的 pgfplots 语法
- ≥8 节点的 DAG/通信拓扑：仍是 `flow` 语法，坐标交给 `scripts/layout_oracle.py` 打底再回手排纪律；几何台账直接成图用 `scripts/codegen.py`（均见 `references/tikz/flow.md` 末节）

三个相邻边界再判别：

| 易混对                     | 判别                                                                                                         |
| -------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `plot` vs spec             | 示意结构本身是论证、真实曲线只是定量衬底 → TikZ `plot`；图的全部内容就是数据关系 → mpl spec                  |
| `flow` vs `diagram-design` | 机制流程、且节点/连线承载数学对象或张量语义 → `flow`；编辑级通用架构图（无数学、HTML/SVG）→ `diagram-design` |
| `board` vs bar             | 设计空间/分类的二维排布（轴含义是范畴不是纯数值）→ `board`；纯数值大小比较 → mpl bar                         |
| `tensor` vs `solid`        | 平面分片/平行四边形堆叠承载语义 → `tensor`；体积与层序本身是论证（层栈、机架、KV cache）→ `solid`            |

两轨共用同一调色板：`assets/tikz/vizstyle.tex` 与 `assets/mpl/fvstyle.py` 的 hex 一一对应，`scripts/check_palette.py` 机检防漂移。9 个语义色相（vteal/vorange/vcoral/vviolet/vgreen/vgold/vblue/vrose/vgray）+ 2 中性色（vink/vmist）；每行代数最多四个活跃色相族 + 中性灰，先变明度再加色相。

## 工作流（两轨共用前半）

1. **归约主线：** 一张图论证一件事。去掉等价目标、诊断项、次要指标；九个以上节点考虑拆成两张。
2. **语义台账：** 每个绘制对象对应恰好一个语义对象。对每个符号/块/卡片/系列记录：语义类别、数据类型或域、一个元素代表什么、取值范围（有意义时）、生产者与消费者。分数、索引、掩码是不同的对象，不得合并成一个标签。
3. **几何台账：** 为每个轴值/列带/时间坐标分配名义物理量；等价类内的对象必须等大。台账先行，坐标后填。两份台账随源文件走、不留在对话里：spec 写进 `meta.ledger` 字符串（缺失时 lint `missing-ledger` 警告）、tex 写进导言区注释、imperative 写进脚本 docstring。`meta` 同层还有 `meta.caption`（底部标识行文本，见风格节）与 `meta.usermeta`（键值透传进 savefig metadata）。
4. **分轨：**
    - 符号/结构 → TikZ：按下表选语法，读对应 `references/tikz/*.md`
    - 数据 → matplotlib：按信息任务选图型（比较→bar、趋势→line、相关→scatter、组成→donut、多维→radar、分布→hist/ecdf/kde/box/violin、场→contour/quiver、流向→sankey、图版→image、检验标注→sig），读 `references/charts/*.md` 与 `scripts/examples/` 最小模板
5. **布局：** 先规划互不重叠的阶段通道与包围盒再落笔；把每个文本都当包围盒算。
6. **渲染—审计循环：** 渲染 → 机器审计 → 看图 → 修。几何不变量与压字交给机器，语义与美感留给自己。

## TikZ 语法索引

| 语法     | 适用                                                                | 参考                          |
| -------- | ------------------------------------------------------------------- | ----------------------------- |
| tensor   | 矩阵分块、元素热力、分片条带、堆叠张量、注意力、TP、einsum          | `references/tikz/tensor.md`   |
| flow     | 流水线、泳道、阶段链、通信算子、分支/合流、反馈回路                 | `references/tikz/flow.md`     |
| board    | 分类板、设计空间、leaderboard、象限——列带 + 卡片网格 + 双通道编码   | `references/tikz/board.md`    |
| timeline | 谱系、时间线、代际图——分段线性轴、泳道基线、引线标签                | `references/tikz/timeline.md` |
| plot     | pgfplots 真实曲线与示意结构混合（半示意半定量）                     | `references/tikz/plot.md`     |
| solid    | 伪 3D 等距立体块——层栈、机架、KV cache（`ziso`/`ssolid`/`vshadow`） | `references/tikz/solid.md`    |

组合语法只在每种都贡献信息时进行；一张图一个主语法，其余降级为附属元素。

## 必须遵守的不变量（全语法通用）

**语义**

- 一个绘制对象 = 一个语义对象；首次使用即定义符号的类别、域与含义。
- 离散链路必须闭合：连续分数 → 离散索引 → gather/route/mask → 被选值，每步有显式算子。
- 颜色即语义：每个角色/族/rank 一色到底；换含义才换色相，换强度只表幅度。同一张图里 TikZ 与 matplotlib 的同一语义必须同一色相。

**几何**（TikZ 可用 vizaudit 机器验证）

- 名义边长一致：同一符号轴值在整张图里是同一物理长度；形状相同 ⇒ 包围盒全等。
- 正方形就是正方形；转置必须真换宽高；收缩维两侧物理等长；分片精确铺满父块（等分片等大、省略用省略号、不拉伸冒充）。
- 只在显式的 reshape/transpose/split/concat 算子处改变几何，并写出轴恒等式（如 $(h/p)d_h=d/p$）。
- 每个对象都是包围盒：无关包围盒间距 $\ge g$（$g\ge1\,\mathrm{em}$），阶段带间 $\ge1.5g$；相切算碰撞。重叠只允许发生在已声明的组合体内部，且声明有通道：铺满的分片 `tiles=`、嵌套 `inside=`、堆叠纸张式部分重叠 `overlap=`、贴近相邻 `adjacent=`、连接器端点 `endpoint=`。
- 连接器在背景层、对象在主层、文字在前景层；连接器不穿过非端点包围盒；标签白衬底只盖自身连线。
- 放不下时：删次要注释、扩大裁剪、加行距、整段换行——绝不缩字号、压间距、互相覆盖。

**风格**

- 统一经 `\input{vizstyle}`（TikZ）或 `import fvstyle`（mpl）取 token；不手写散落 hex。
- 字号层级（TikZ）：`\large` 主张、`\small\bfseries` 阶段标签、`\Large` 算子、`\small` 符号、`\scriptsize` 形状/弱化、`\small` 底部说明。
- 支持结构先于幅度：已知零留白；对角/三角/掩码只填结构支持集；要表达被掩掉的位置，画 vmist 弱格（ghost cell）并说明含义，不算违反支持集纪律。稠密示意张量用 2–3 个非周期明度层级，禁棋盘格。
- 底部一个全宽低对比含义框，一列阅读栏、至多三行固定标签（**轴/对象/机制**或按图型改写，如 board 用**判决/稳定性**）；框外居中一行 `\scriptsize` 中性灰标识文字，只描述实际可视化内容。含义框约束结构/机制图（TikZ 轨与示意面板）；数据图承载不了三行语义框，mpl 轨只保留底部居中一行小号中性灰标识行——spec 侧填 `meta.caption` 由渲染器落位（缺失时 lint `missing-caption` 警告），imperative 侧 `fig.text(0.5, …, ha="center")` 小号字、色取 `fv.NEUTRALS` 灰。
- 顶部至多两行紧凑主张（公式或一句话）；默认不加标题；白底、`standalone` 自然裁剪，不强制 16:9。
- 示意单元格数 ≠ 真实维度可以，但只声明一次，且不放宽任何几何不变量。

**高频踩坑**（e2e 语料实证，judge 与对抗复核命中率最高的七类）

- 图面文字禁止出现内部 token：`vteal`/`vmist`/`!60` 这类调色板变量名不属于读者面向文本——含义框配色声明用 ■ 色块或自然语言色名。
- 同一语义对象全图同一记号：下标粒度（$a_i$ vs $a_{ij}$、$g$ vs $g_i$）前后漂移等于引入第二个对象。
- 合成/示意数据显式声明：合成曲线、占位日期、示意格阵必须标「示意」或 `(illustrative)`；实心真实感标记冒充真实读数即语义造假。
- 边型即通道语义：数据通路、权重/控制通路、依赖通路必须分线型或分色相——实线并入 ⊕ 一律被读作加性输入。
- 拓扑必然穿越要么改道要么声明 + 跨桥：同色十字与无结点线线交叉会被读成连接，半圆跨桥是标准消歧手段。
- 结构边界退出角色色相：设备虚线框、带名、泳道这类结构元素用中性色（vink/vmist 系），占一个角色色相即撞义。
- 省略号、落针、装饰 glyph 也是绘制对象：要么埋点要么 `% fv:noaudit`/`% fv:coverage off` 显式豁免——审计盲区散件会被 judge 按未埋点碰撞问。

## TikZ 轨：渲染与审计

引擎：可编辑 TikZ，standalone 文档；中文用 `\usepackage[UTF8,fontset=fandol]{ctex}`（XeLaTeX）——**手写 standalone 含 CJK 必须挂 ctex/xeCJK**：缺了它 xelatex 静默吞掉全部汉字字形，vizaudit/coverage/readback 三层全盲 exit 0（render_tex 的 cjk-no-ctex preflight 会 warn）。需要 pgfplots 时 `\pgfplotsset{compat=1.18}`。

```
preamble: \input{vizstyle}   % 调色板、字号/箭头 token、bg 背景层、语法样式（model/card/mdot/lab/lead/gtag/inh）
          \input{vizaudit}   % 不变量埋点（可选但推荐；不埋点 = 审计零覆盖，不算通过）
render:   python3 <skill>/scripts/render.py fig.tex            # → pdf/png/透明png/svg
          python3 <skill>/scripts/render.py fig.frag           # 片段自动包 preamble（等价 --frag）
```

`.frag` 的自动 preamble 固定为 `standalone[border=8pt]` + `ctex[UTF8,fontset=fandol]` + `amsmath/amssymb` + `tikz` + `pgfplots`（`compat=1.18`）+ `\usetikzlibrary{arrows.meta,positioning,calc,decorations.pathreplacing,fit,matrix,graphs}` + bg 层声明 + `\input{vizstyle}`/`\input{vizaudit}`——frag 直接审计，体内不要再自行 `\input{vizaudit}`（重复引入经守卫静默 no-op）。preamble 没有追加 `\usepackage` 的逃生舱：需要名单外的库（如菱形判定门的 `shapes.geometric`）就改写 standalone `.tex` 自备导言。片段体必须是完整 `\begin{tikzpicture}...\end{tikzpicture}`——preamble 自动包、环境不自动包，顶层裸 `\node`/`\draw` 语句会报 Undefined control sequence。standalone 文档同理：`\input{vizaudit}` 必须放在导言区顶层；在正文或 tikzpicture 内 `\input` 会被守卫响亮跳过（body 里引入会泄漏隐形行盒、弄坏 standalone 裁剪），症状是 `.audit` 缺 origin 行、readback 降级。

`scripts/render.py` 是统一入口：按扩展名分发——`.tex`/`.frag` 走 TikZ 轨，`.json`/`.spec.json` 走 mpl spec 轨；`--outdir`/`--dpi`/`--frag`/`--no-audit`（tex 轨即 `--no-check`）等旗标一致透传，`--no-readback` 与 `--overlay` 两轨各自实现、语义相同，`--no-coverage`/`--no-svg`/`--no-png` 是 tex 专有（喂给 `.json` 报错而非静默吞掉）；两个后端 CLI（`render_tex.py`/`render_mpl.py`）仍可单独调用。审计输出两轨同一格式：`ERR <rule>: <msg>` / `warn <rule>: <msg>`（mpl 侧 spec lint 为 `warn lint:<name>: <msg>`）；退出码 0=干净或仅 warn、1=有 error 级审计问题、2=输入/用法错误。

背景带用 `\begin{pgfonlayer}{bg}...\end{pgfonlayer}`——`bg` 层已由 vizstyle 与 `--frag` preamble 声明，勿再自备声明。

`render_tex.py` 把 `assets/tikz/` 注入 `TEXINPUTS`，`\input{vizstyle}` 直接可用；嵌入大型 tex 工程（非 standalone）时把 `assets/tikz/vizstyle.tex`、`assets/tikz/vizaudit.tex` 复制进工程目录。产物含 `.audit` 时自动跑 `check_audit.py`（render_tex 用 `--no-check`、统一入口用 `--no-audit` 关闭；`.audit` 是中间产物，不入库）。

审计埋点（写在 tikzpicture 内）：

```tex
\node[..., vaudit={class=col}] (s0) ...;   % 给正在画的节点打标签
\path \vaudit{A}{eqwh=B};                  % 给已画节点补标签
\vzbbox{stack}{(0,0)}{(4,1)}               % 审计无名矩形区域（顶层命令，勿加 \path 前缀）
```

| 标签                      | 检查                                                                |
| ------------------------- | ------------------------------------------------------------------- |
| `class=<id>`              | 同类节点宽高全等                                                    |
| `square`                  | 宽 == 高                                                            |
| `twin=<n>`                | 转置对：我宽高 == 对方高宽                                          |
| `eqww/eqhh/eqwh/eqhw=<n>` | 指定维度相等（收缩维：`eqwh`/`eqhw`）                               |
| `tiles=<n>`               | 分片互不重叠且并集铺满父节点                                        |
| `inside=<n>`              | 声明的嵌套（消除 NEST 警告）                                        |
| `overlap=<n>`             | 声明的部分重叠（消除 COLLIDE；对称、可验证——声明了却没相交会 warn） |
| `adjacent=<n>`            | 声明的贴近（消除 CROWD；对称）                                      |
| `alignx/aligny=<n>`       | 中心 x/y 对齐                                                       |

`inside=`/`tiles=`/`adjacent=`/`overlap=`/`alignx`/`aligny`/`twin`/`eqww`/`eqhh`/`eqwh`/`eqhw` 都是可重复键（`vaudit={inside=a,inside=b}`），但语义分两档：前四个的重复值是并列目标名单；`alignx`/`twin` 等断言键的重复值是成对链断言（`alignx=a,alignx=b` 即 a·b·我三者同轴），不要当名单用。`adjacent=`/`overlap=` 的目标除节点名外还收 `class:<id>`——展开到所有挂 `class=<id>` 的盒（自身除外），格阵/同族堆叠的逐对簿记压成一句；空 class 按悬空目标告警。`inside=` 声明不可传递：`inside=a` 只豁免「我在 a 里」这一对，a 外的 b 撞到我要自己声明（`inside=b` 或 `overlap=b`）。

未声明的半重叠是 `COLLIDE`（错误）；未声明的包含是 `NEST`（警告）。`check_audit.py --tol`（默认 1pt）与 `--edge`（默认 2pt，沿边相贴豁免）。

vizaudit 只看得见埋过点的对象——埋点够不够、对不对、渲染出来撞没撞由三件套补查（全 warn-only，不进退出码；`render_tex.py` 在 check_audit 后自动接跑，判据与豁免语法见 `references/tikz/coverage.md`）：

- `scripts/check_coverage.py`：静态扫未埋点的绘制对象（`\node/\draw/\path/\fill/\pic` 未挂 `vaudit=`、名字未被 `\vaudit`/`\vzbbox` 重标、`\draw` 引用无 `\vzwire` 镜像即报）；`% fv:noaudit` 行尾豁免、`% fv:coverage off/on` 区域豁免。`--no-coverage` 关闭。
- `scripts/check_readback_tex.py`：`pdftotext -bbox` 词盒经 `.audit` 的 origin 行映射回 pgf 盒，报 `crosses`（文字压 audited 盒）与 `outside-page`（裁切吃内容）；只校准单 picture 单页 standalone。`--no-readback` 关闭。
- `--overlay`：二遍编译产 `<stem>.overlay.pdf`——每个 audited 盒画橙虚线框 + 名签、每条 `\vzwire` 画紫虚线声明折线，「机器看到的图」调试用。

## matplotlib 轨：spec 与 imperative

一条轨、两种写法，同一套调色板与审计：

**spec 路径（标准图首选）**：把图写成 `spec.json`（版本化 schema：theme/rc/size/colors/data/layout/panels/series/legend/arrange/output/audit），交给统一入口 `render.py`（内部即 `render_mpl.py` 后端）渲染。数据只收预聚合行——`make_figure(agg)` 边界的机器化，数值求解留在脚本 glue（聚合用 `fvagg` helper：`agg_rows`/`keyed_to_rows`/`calibration_bins`/`pareto_front`/`jitter`/`rank` + csv round-trip，见 `references/charts/spec.md` data 节）。可渲染样例收 `scripts/examples/spec_*.json`（15 个：单图型 + multipanel/matrix/spans 布局与 sankey/sig/waterfall 图族）。适合折线+band+ 参考线 + 分类散点这类标准实验图与可 replot 的落盘图。

```
uv run --with matplotlib --with numpy python <skill>/scripts/render.py fig.spec.json [--outdir DIR] [--dpi N] [--no-audit] [--no-readback] [--overlay]
# Python 内：import fvspec; fig = fvspec.render(spec_dict, base_dir=spec_dir)
```

schema 全量字段与示例读 `references/charts/spec.md`；spec 装不下的自由度用 `panels.*.raw` 逃生舱（`f(ax, ctx)`，audit 照跑；spec 所在目录渲染时自动进 sys.path，旁挂 `helper.py` 直接 `'helper:func'` 引用）。落盘产物可溯源：PNG/PDF/SVG 的 metadata 带 spec 内容哈希与 `meta.usermeta` 透传键，能从产物反查生成它的 spec 文本。

**imperative 路径（实验图）**：数值脚本先跑实验、聚合成行，再手写 mpl 画图——`fvstyle` 提供调色板/主题 token，`fv.audit` 提供同一套机器审计。多面板语法读 `references/charts/multipanel.md`，模板从 `scripts/examples/multipanel_demo.py`（1x4 实验图全流程）、单图型 demo 与配方 demo（`treemap_demo.py`、`sigbracket_demo.py`）改起，不从零写。

```
import fvstyle as fv            # assets/mpl 加入 sys.path 后导入
current = fv.apply_rc("paper") # paper / accent / mono 三套主题（serif 栈默认，栈尾挂 CJK fallback——中文标注直接用，勿手动 append 字体名）
colors  = fv.series_colors("paper", n)
problems = fv.audit(fig)       # fig.canvas.draw() 后跑全部 RENDER_RULES
```

- 图型选型与 spec 字段速查读 `references/charts/chart-families.md`；preset 轴含义读 `presets.md`；spec 读 `spec.md`；多面板读 `multipanel.md`。
- 运行：`uv run --with matplotlib --with numpy python fig.py`。自检一键入口：`python3 scripts/test_all.py`（palette → agg → selftest → spec 族（+atoms/kde/image/field/matrix/waterfall/sankey/sig）→ render → render-tex → audit 族（rules/mpl2/tikz）→ tikz-recipes → vlm-judge → oracle（+tree）→ solid → imperative demo 冒烟，mpl 步骤自动经 `uv run` 起子进程；`--tikz` 追加 TikZ 渲染冒烟）。
- 字符串里 CJK 与 `$..$` 混排时汉字被 mathtext（stix 字集无 CJK 字形）渲成豆腐块——标签要么纯中文要么纯数学，混排就拆成两个文本对象。
- 跨机/跨目录定位 `assets/mpl` 用 vendorable 定位器 `scripts/fvlocate.py`：脚本里 `import fvlocate; fvlocate.ensure()`，或 shell 侧 `PYTHONPATH=$(python3 <skill>/scripts/fvlocate.py)`；候选根含 env pin、安装位与 vendored 位置。`import fvlocate` 要 fvlocate.py 已在 `sys.path` 上——该写法只在 skill 仓内成立，仓外目录使用把 fvlocate.py 拷到脚本旁（或按其 docstring 的 vendored 方式）。
- **深审计**：`fv.audit(fig)` 除 COLLIDE 压字（旋转文本按四边形实测）、OFFPALETTE 离板色（cmap 化 artist 豁免）外还查数据层（log 轴非正数、出限裁剪、bar 基线截断）、跨面板一致性（facet-ylim 失配、同名异色/异 marker、tag 序列）、标注层（缺轴标、文字压数据线/点/柱、legend 压数据/覆盖不全/重复标签、文字出界、色相预算、palette 溢出）。spec 侧先过 spec-time lint（empty-series/hex-literal/pred-indistinct/tick-density/bar-count/hist-bin-sanity/violin-min-points/kde-min-points 等可抑制警告）与 `SpecError` 响亮报错（unresolved-color、未知键/版本等不可抑制），再落 draw。
- **回读层**（`rb-*` 与 `print-fit`）：draw 之后拿 renderer 实测 device-px 几何说话——`rb-text-outside`（文字越画布）、`rb-text-collide`（文本框按旋转四边形真相交 >20% 较小框）、`rb-label-diff`（spec 声明文本 vs 渲染文本差集，抓图例静默丢系列）、`print-fit`（tightbbox 交付宽 vs `size` 槽位缩印后 <5.5pt）。全 warn 级；`--no-readback` 只豁免 `rb-*` 三条，`--overlay` 产 `<stem>.overlay.png` 把 axes/legend/文本框画出来定位。规则语义与已知误报见 `references/charts/readback.md`。
- 刻意的违规（非零基线等）不静默：`audit(ignore_axes=[i])`/`audit(ignore=[rule])`/`audit(scoped_ignore=[(rule, axes_idx)])`（只豁免某条规则在某个 axes 上）或 spec 的 `audit.ignore`/`panel.audit_ignore` 显式声明；项目色注册进 `colors.extend`/`fv.register_colors()` 而不是跟 OFFPALETTE 对抗。inset 例外须知：mpl≥3.10 的 `indicate_inset_zoom` 返回的 InsetIndicator 挂在 `ax.artists` 上，对 series_map/OFFPALETTE 审计完全透明——指示器矩形与连线的配色须手动遵守调色板（inset axes 本身在 `child_axes` 里，照常可审可豁免）。
- preset 只在「复用 ≥2 次且是完整视觉策略」时才新增，否则在图内参数或 spec 字段表达。

## 交付前检查

1. 独立重算每个形状与关键坐标（TikZ）/每组数据与坐标轴含义（mpl）。
2. 语义台账闭合：无合并标签、无未解释符号、离散链路完整。
3. 机器审计零错误**且审计确实跑过**：TikZ 轨要产出 `.audit` 文件（vizaudit 埋点真实存在）且 `check_audit.py` 无 COLLIDE、NEST 警告逐一确认；mpl 轨要调过 `audit(fig)` 或走渲染 CLI 的审计分支，无 error 级问题。「零错误」不能靠不埋点/不调用达成。调色板改动后 `check_palette.py` 必须通过。
4. 语义评审（advisory，永不 block，**opt-in**）：默认不跑——仅在用户明确要求 VLM/语义评审时执行 `python3 scripts/vlm_judge.py fig.png --backend claude --intent <台账/NOTES 路径>`（一次一图，不进迭代循环）；评审单随案归档，CONCERN/FAIL 逐条人工复核处理。`--intent FILE` 收台账/spec/NOTES 文件路径当靶子——不是内联文本，且只截取文件头部（上限 ~8000 字符）：台账/主张写进文件头注释，尾部内容进不了评审单。审计管图有没有画错形，judge 追问图有没有说错话（主张 - 证据矛盾这类盲区）；exit 恒 0、不 emit `ERR`。判定指引与边界见 `references/vlm-judge.md`。
5. 目检 PNG 原尺寸与缩略图：无相交/相切/裁切/遮挡；色相数、明度层级、非周期纹理、底部框与标识行就位。
6. 违反任一必须不变量的图拒收重画。
7. 交付预览 PNG、一句话机制说明、可编辑源文件（tex/py）与矢量产物路径。

不要交付仅语法能编译的图——数学正确与视觉对齐缺一不可。
