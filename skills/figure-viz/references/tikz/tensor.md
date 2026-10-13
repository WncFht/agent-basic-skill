# tensor 语法 — 张量/矩阵公式图

把一个公式或张量代码路径转换为紧凑的三段式图：顶部公式、中部计算、底部含义。

## 视觉语法选择

- **元素色块：** 掩码、稀疏性、因果结构、逐元素操作，或小矩阵中的行/列角色。
- **行/列条带：** 分片、设备归属、张量并行、通道组——关键事实是整条轴分区时。
- **堆叠切片/面板：** $B\times T\times d$ 或 $B\times h\times T\times d_h$ 的 3D/4D 张量；深度编码额外的轴。
- **箭头与通信节点：** AllReduce、AllGather、ReduceScatter、转置、重塑、拆分、拼接、数据移动。

单元格变化可为稠密张量提供纹理，但已知零必须留白；掩码、对角线、稀疏性和分区必须编码精确结构。

## 公式与形状规则

- 代数公式中绝不使用形状下括号；形状只标在中部对应分块下方。
- 符号紧贴分块下方居中，形状下一行居中；维度语义进底部含义框，不重复形状列表。
- 显式展示被收缩的维度：$(m\times k)(k\times n)\rightarrow(m\times n)$。
- 末维线性层保留前导轴：$(B\times T\times d_{\mathrm{in}})(d_{\mathrm{in}}\times d_{\mathrm{out}})\rightarrow B\times T\times d_{\mathrm{out}}$。
- 区分全局形状与每 rank 本地形状；写明转置、广播、归约、重塑、拆分、拼接的轴顺序。
- 元素矩阵用独立单元格 + 窄白色间隙 + 0.5–1pt 圆角；括号/外框用 `black!55`–`black!70` 细线，不用高饱和轮廓，不铺连续网格。额外轴用浅层堆叠或重复面板。

## 符号语义与离散对象

- 每个不显然符号归类：值、分数/对数几率、概率、索引/坐标、秩/顺序、计数、ID、掩码/支持集、置换、形状参数——写清域与「一个元素代表什么」。
- 选择/路由闭合全链：分数 → 索引/ID → gather/scatter/mask/route → 被选值；区分 `TopKValues` 与 `TopKIndices`，都用了就画两个输出。
- 首次使用定义索引记号与范围，如 $S_t=(s_{t,1},\ldots,s_{t,k})$，$s_{t,r}\in\{0,\ldots,t\}$；区分源位置轴 $s$ 与槽位/秩轴 $r$；说明排序、重复、填充、可变基数。
- 至少展示一次地址映射，如 $G[b,t,r,:]=X[b,S[b,t,r],:]$；同时展示掩码时写 $M[b,t,s]=\mathbf 1[s\in S_{b,t}]$——整数索引与布尔掩码不是同一对象。
- 索引画成有序槽位/位置标签/gather 线；掩码画成二值支持集；分数与值画成幅度色块——三者不要用同一语法。
- 索引在头/rank/分支间共享时，只画一次共享选择器，标清广播/复用轴。

## 几何不变量（tensor 补充）

- 矩阵面 $a\times b$ → 高 $a$、宽 $b$；批量/堆叠张量用最后两轴作平面，前导轴只做深度或重复面板。
- 转置、收缩、分片的机器验证：`vaudit={twin=...}`、`vaudit={eqwh=...}`、`vaudit={tiles=父块}`、`vaudit={class=...}`（见 SKILL.md 审计表）；堆叠切片的错台半重叠写 `vaudit={overlap=相邻片}`。
- 分块乘法在顶部公式与相关中部面板都展开代数：

$$ \mathbf X\mathbf W = [\mathbf X\mathbf W^{(1)}\mid\cdots\mid\mathbf X\mathbf W^{(p)}] = [\mathbf H^{(1)}\mid\cdots\mid\mathbf H^{(p)}], $$

$$ [\mathbf H^{(1)}\mid\cdots\mid\mathbf H^{(p)}] \begin{bmatrix} \mathbf W^{(1)}\\ \vdots\\ \mathbf W^{(p)} \end{bmatrix} = \sum_r\mathbf H^{(r)}\mathbf W^{(r)} = \sum_r\mathbf P^{(r)}. $$

## Kimi 风格

元素级矩阵分块是核心或用户要求 Kimi 风格时，绘制前用图像查看器检查 `assets/tikz/kimi-matrix-style-reference.png`；只校准单元格间距、圆角、中性括号、克制色相、明度区分与结构留白——不复制其公式/内容，不把该资源嵌入输出。

## 备选写法：matrix of nodes

规整元素矩阵可换 `\usetikzlibrary{matrix}` 的 `\matrix[matrix of nodes]` 一次排格，免去逐格坐标台账：单元格自动命名 `M-行-列`，`nodes={gcell, minimum size=...}` 统一打底，`row \i column \j`、`column \i` 样式钩子按位置改色。装了 tikz-ext 时 `matrix.skeleton` 库还能在矩阵骨架上叠 fit 框与格级标签。

注意一个审计陷阱：**不要**在 `nodes={}` 里挂 `vaudit`——格子埋点在矩阵排版前读锚点，坐标作废且会报假 COLLIDE；事后补登也因「先注册者赢」救不回坐标。要审计的格子只在 `\matrix` 之后用 `\path \vaudit{M-1-1}{class=cell,square};` 逐格注册——此时读到的是排版后坐标。空单元格默认不生成节点，要 retag 空格须加 `nodes in empty cells`（否则报 "no shape named"）。不规则结构（逐格异色、掩码形状）仍用逐格 `\node` 展开式写法。

## 陷阱

- `\foreach` 循环体内写 `\ifnum` 等条件必须用大括号把整段动作包起来：`\foreach \i in {0,...,7} { \ifnum\i=0 ... \fi }`。不加大括号时 `\foreach` 只把到下一个分号为止的内容当循环体，`\ifnum...\fi` 被截断后产生莫名其妙的 compile error 或静默错位。
- 每个格子一个 `\node`/`rectangle` 的展开式写法优于一次 `\draw grid`——网格线画不出逐格 vaudit 埋点与异色填充。
- 整体缩放：`[scale=1.4]` 只缩坐标，节点文字、线宽、`minimum size` 原样——等价类等大关系当场破功。要连节点一起缩用 `transform shape`；更好的做法是改几何台账的单位常量，不碰 scale。
- 节点名在整个 `tikzpicture` 内全局有效：`\foreach` 循环里复用同一名字会静默重绑（后画的顶替先画的锚点），循环体内一律用 `(m\r\c)` 这类带索引名。`local bounding box` 相反，只在所在 `scope` 内可见，出 scope 引用即报 "no shape named"。
- `right of=A`/`below of=A` 是弃用语法，按中心距摆放；positioning 库的 `right=of A`/`right=2.2 of A` 按边到边。同一图混用两种，间距规则分裂——统一写新语法。
- `.. controls ..` 与 `to[out=,in=]` 的贝塞尔控制点计入画布包围盒：弯箭头常把画布撑出一圈空白边。用 `\useasboundingbox` 钉住画布，或给该段 `\draw` 加 `overlay` 再手补留白。
- matrix 间距语义：`column sep`/`row sep` 默认 `between borders`（边框到边框），想要格点等距写 `{between origins}`；单元格内容参差时用 `nodes={minimum width=.., minimum height=..}` 钉齐再谈对齐。**`between borders` 对 `tiles=` 是陷阱：** 描边单元格（`draw`）即使 sep=0 也在路径层留下线宽级缝隙，真实覆盖率扫描会报出假的未覆盖孔——要 `tiles=` 审计的格阵必须写 `{between origins}`（或格间显式留真缝）。
- 格子内画索引/坐标标注（$i,j$、槽位号）：标注字号降一档、用中性色（`black!55` 或 `vgray`），写在 cell 内锚点上不占额外节点——如 `label={[vsym,black!55]center:$\scriptstyle i$}` 或直接格内排版；标注若落成独立 `\node` 会与 cell 撞 CROWD/COLLIDE，要审计就挂 `inside=cell名`，不审计就留在 cell 内部文字里。
- 引用锚点的语句必须在被引用节点之后：`\draw (A.east) -- (B.west)` 引用还没定义的名字报 "no shape named"。把连线挪到 `pgfonlayer{bg}` 下层的正确姿势是先画完全部命名节点、再进层补线——不是把线提前写。
- `inside=`/`overlap=`/`adjacent=` 声明不传递：`inside=a` 只豁免「我在 a 里」这一对；a 外面还有 band 包住我时，与 band 的嵌套要另行 `inside=band`（部分重叠则 `overlap=band`），否则 NEST/COLLIDE 照报。
- 逐格审计的声明账本是 O(n²)：每格 `inside=<外框>` 之外还要对**每个邻居**写 `adjacent=`（9×9 格阵逐对裸写实测 272 对）。给格子统一挂 `class=<id>` 后改用 `adjacent=class:<id>`——一句断言展开到全组（自身除外，`overlap=` 同样收 `class:` 目标），格阵簿记压成每格一句；更异质的账本再退回 `\foreach \i/\j` 按索引算邻居名批量生成。
- 格内文字比 `minimum size` 宽会把格子撑大，`class=`/`square` 等大断言立刻 ERR（实测 `\tiny` 的 $-\infty$ 宽 13.9pt 撑爆 0.38cm 格）。顺序是先量字形宽度再定 `minimum size`——`\settowidth` 试排，或先渲染读 .audit 实测盒高宽——不是先画格子再塞字。
- **`minimum height` 是地板不是天花板**：多行 tile 文本超高时节点静默撑高越过父块，`tiles=`/`inside=` 声明照样断（宽度方向同款见上条）。定高单元格要么对齐行数、要么 `text height`/`text depth` 钉死排版盒；「先量后排」对高度同样成立。
- **`\hspace*` 在定宽 tile 文本内挪字盒**：`{\hspace*{<len>}文本}` 把词盒在节点内推移——审计盒（节点外框）纹丝不动，readback 的词盒相交却可借它绕开（把字从邻盒边挪开而不改几何台账）。
- 带视觉间隙的格阵用不了 `tiles=`：coverage 把间隙读成 hole=ERR。两条出路：逐格 `class=cell` + 邻居 `adjacent=`；或更干净——给格子 `outer sep` 造出审计槽位，`tiles=` 挂到父区域上。
- 贴面轴字母的 CROWD 陷阱：字母距面 ~9.6pt 仍在 10pt 阈值内告警——`adjacent=` 要对面区域**和**底部车道逐对各写一条，声明不传递（豁免了面不等于豁免车道）。
- 错台堆叠 batch sheet 的埋点单：每张片约 5 条 `overlap=`——面区域 1 + 穿过的 3 条车道 + 相邻兄弟片 1。照单全登，漏一条 COLLIDE 报一对。
- **硬缺口：** scope 自定义基向量（`x=`/`y=`）下，TikZ 的 `rectangle` 与节点形状只产轴对齐 AABB，不是平行四边形——斜格阵的格子全变成互叠的轴对齐砖块，逐格审计结构性无解（平行四边形 AABB 必然与邻居相交）。斜格阵的格线改用 `\draw` 连四个变换后角点手绘；审计上把片内部包进 `% fv:coverage off`，靠像素目检兜底。

## 审计埋点示例

```tex
% (m×k)(k×n)→(m×n)：收缩维物理等长
\node[draw, fill=vteal!15, minimum width=1.2cm, minimum height=2cm,
      vaudit={eqwh=B}] (A) ...;                    % A.w == B.h
\node[draw, fill=vviolet!15, minimum width=3cm, minimum height=1.2cm,
      vaudit={}] (B) ...;
% 列分片铺满父块
\node[..., vaudit={class=col,tiles=W}] (s0) ...;
% 转置
\node[..., vaudit={twin=Wt}] (W) ...;
% 无名区域注册；第四参数挂标签——有意贴边的两区域任一侧写 adjacent=对方 免 CROWD（对称判定）
\vzbbox{lhs}{(0,0)}{(4,3)}[adjacent=rhs]
% 堆叠切片/纸张：错台部分重叠的两块任一侧写 overlap=对方 免 COLLIDE（对称、被验证——
% 声明了却没相交 warn，真嵌套仍走 inside=）
\node[..., vaudit={overlap=sheet1}] (sheet2) ...;
% 连接箭头也审计：\vzwire 镜像 \draw 的途经点（节点名 / node.anchor / 裸坐标）
\draw[varr] (A) -- (B);
\vzwire{AB}{A;B}{endpoint=A,B}
```
