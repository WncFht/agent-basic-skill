# timeline 语法 — 谱系与时间线

事件沿时间轴分布、按泳道分族的图：技术谱系、代际演进、里程碑。

## 结构件

- **时间轴：** 用 `declare function` 定义分段线性坐标映射（如 2024 后放大 3 倍），放大区画阴影底带 + 分界虚线 + `\tiny` 注记；顶部主轴画刻度与年份。
- **泳道：** 每族一条水平基线（族色相 0.9pt 线）+ 左侧 `gtag` 标签（族号、含义、年跨）；带底色用 `\fill[band=<族色>]`（= 族色!8 + 圆角）。
- **事件点：** 用形状区分对象类型（圆点 `mdot=<族色>` = 模型/系统，方点 `msq=<族色>` = 数据集/基准），族色填充；重点事件加第三色。
- **标签：** `lab` 样式（白底圆角 `\scriptsize`）错位排布，`lead` 细灰线指回真实时间点——标签可以漂移，点必须在真实坐标上。
- **图例：** 左上空白区列点型语义。

## 布局规则

- 事件点坐标一律经坐标函数生成，禁手算平移；拥挤段上下交替摆标签。
- 引线 `gray!55` 0.35pt，只连点与标签，不穿别的对象；标签白衬底只盖自己的引线头。
- 泳道底带/放大区底带一律 `\begin{pgfonlayer}{bg}`——`bg` 层由 vizstyle 统一声明，不要引 `backgrounds` 库的 `background` 层（两套层名混用会让底带盖到主层上）。
- 底部含义框常改为「读法」行：点型、颜色、放大区的读法一次说清。
- 尺寸账：漂移 `lab` 两行文本实测半高 ~10.6pt——带内放标签要求泳道带半高 ≥~1.3cm、相邻基线距 ≥~3.2cm；CROWD 阈值 `--gap` 默认 10pt 比直觉严（~3.5mm 间距也告警），贴带/贴点标签提前写 `adjacent=`。带高预算起点：单行 `\small\bfseries` 主张行 + 单行 `\scriptsize` 注记行 ≈1.35cm 净高。

## 骨架

```tex
declare function={tx(\t)= (\t<2024.75) ? (\t-2016)*0.95 : 8.3125+(\t-2024.75)*3.0;}
\begin{pgfonlayer}{bg}
  \fill[band=vteal] (-0.35,-1.3) rectangle (15.55,1.3);                    % 泳道底带
\end{pgfonlayer}
\vzbbox{lane0}{(-0.35,-1.3)}{(15.55,1.3)}                                   % 带区注册
\foreach \y in {2016,...,2027}
  \draw[gray!16, line width=0.4pt] ({tx(\y)},-1.2) -- ({tx(\y)},1.2);       % 年网格 fv:noaudit
\node[mdot=vteal, vaudit={class=evtc,inside=lane0}] (e0) at ({tx(2022.292)},0) {};
\node[msq=vteal, vaudit={class=evts,inside=lane0}] (e1) at ({tx(2023.5)},0) {};
\node[lab, vaudit={inside=lane0}] (l0) at (6.05,0.95) {LayoutLMv3\\{\tiny 2022.04}};
\draw[lead] (e0) -- (l0.south);                                             % 引线指向标签锚点
\vzwire{le0}{e0;l0.south}{endpoint=e0,l0 via=lane0}                         % 过带写 via=, 落点盒写 endpoint=
\draw[inh] (e0) -- (e1);
\vzwire{ie}{e0;e1}{endpoint=e0,e1 via=lane0}
\node[gtag, vaudit={aligny=e0,adjacent=lane0}] (g) at (-0.6,0) {族 A};       % 贴带标签声明 adjacent
```

## 审计埋点处方

- **事件点**同型打同一 `class`（如 `evtc`/`evts`）：`mdot` 与 `msq` 名义尺寸相同但视觉大小不同（同径圆点看起来比方点小），分用两个 class 让同型等大、异型不强求。
- **泳道带/放大区底带**各一条 `\vzbbox{名}{sw}{ne}` 注册；带内对象写 `inside=带名`（现在是被验证的断言：带没埋点报 unaudited，对象越出带界报 escapes）消 NEST；有意贴边的相邻带/标签任一侧写 `adjacent=对方` 消 CROWD（对称判定）。**例外：** 横跨多条泳道、与泳道带只是部分相交的大背景带不要注册——它跟每条泳道带都是未声明半重叠，COLLIDE 无从豁免；只给泳道级带埋点。若大带完整包含泳道带，则可以注册并让泳道带写 `inside=大带名`。
- **漂移标签** `vaudit={inside=laneX}` 一并埋进——漂移布局要验的正是标签不互相压、不盖别人的点，且 `inside=` 顺带校验标签没漂出带区。
- **引线与继承箭头**逐条镜像 `\vzwire{名}{点;点.anchor;x,y}{endpoint=… via=…}`：`endpoint=` 写两端的端点盒（引线落在标签盒里时标签也算端点，裸坐标端不写），`via=` 写有意途经的盒——引线从带内点出发会进带区，所在泳道带必须进 `via=`；跨多条带的连线要把每条途经带（含非端点的中间带）都列全。穿非端点/未声明盒由 WIRE-CROSS（error）兜底。泳道基线 wire 横贯整条带：带自身也必须进 `via=`（`via=laneX`），否则每过一次带界吃一个 WIRE-CROSS。
- **gtag 泳道标签**与基线同高可机检 `vaudit={aligny=<基线上任一事件点>}`；标签紧贴带左缘是常态，补 `adjacent=带名` 消 CROWD。
- 埋点不是全部对象都要：年网格线、刻度这类纯装饰不用埋；埋的是「错了就是图错了」的对象。

## 陷阱

- 时间轴缩放走 `declare function` 的坐标映射（如 `tx()`），不用 `[scale=]`——scale 只缩坐标不缩点径字号，事件点会偏离刻度；要整体改比例改函数系数。
- 节点名在整个 `tikzpicture` 内全局：`\foreach` 年网格/事件循环里复用同一名字会静默重绑锚点，循环体内一律带索引命名（`(e\i)`）；`local bounding box` 只在所在 `scope` 内可见。
- `right of=A`/`below of=A` 是弃用语法（中心距）；positioning 库写 `right=of A`/`below=2pt of A`（边到边）。漂移标签本来就是手摆坐标——别为了对齐退回旧语法。
- `to[out=,in=]` 跨泳道弧线的控制点计入画布包围盒，会把时间轴画布撑出空白边；必要时 `\useasboundingbox` 钉住或弧线加 `overlay`。
- 图例若要规整点型矩阵可用 `\matrix[matrix of nodes]`：`column sep`/`row sep` 默认 `between borders`，等距格点写 `{between origins}`；格子**不要**在 `nodes={}` 里挂 `vaudit`（排版前读锚坐标作废，会报假 COLLIDE），要审计就事后 `\path \vaudit{M-1-1}{...}` 逐格补标签——注意空单元格默认不生成节点，要 retag 空格须加 `nodes in empty cells`。
- 密集相邻事件点之间的 `inh` 箭头会被 tikz 按两点距自动收缩——点距近到一定程度箭头尖会缩没或反翘成怪形，视觉上像断线。密集段（相邻点距 < ~8pt）别逐点画继承箭头：改用 `inh` 的 shorten 版本、改成无头连线，或把整段折成一条带刻度的母线。
- 拥挤段里漂移标签难免落在**相邻**事件点 ~7pt 处——`adjacent=` 要逐对补到「标签↔邻居点」，只声明「标签↔自己的点」「标签↔带」不够（按对生效，不传递）。
- 距分界虚线 ±~1 个月的事件点会物理擦线：审计侧有边缘豁免不报错，但视觉擦边真实存在。缓解三选一：分段边界本是设计选择就挪开、缩小点半径，或接受擦线并把标签引开别让冲突叠起来。
