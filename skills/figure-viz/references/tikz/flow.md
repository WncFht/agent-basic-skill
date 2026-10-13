# flow 语法 — 流水线、泳道与阶段链

数据/控制沿阶段流动的图：pipeline、泳道角色图、通信模式、决策门、反馈回路。

## 结构件

- **阶段带/泳道：** 水平或垂直的共享基线行/列，左侧放 `\small\bfseries` 角色/阶段标签。背景带首选声明式 `\node[band, fit=(成员a)(成员b)..., inner sep=8pt] (laneX) {}`（`fit` 库，放 `pgfonlayer{bg}`）——带盒由成员包围盒算出，成员挪动带自动跟随，「带子漂移」整类错误在构造时就不存在。成员未定、要先画容器再填内容时退回手算式 `\fill[band] (sw) rectangle (ne)` + `\vzbbox{laneX}{sw}{ne}`；第三选择 `\begin{scope}[local bounding box=L]...\end{scope}` 后用 `($(L.south west)+(-6pt,-4pt)$)` 围带（需 calc）。
- **算子节点：** 处理块一律以 `model` 样式打底再叠 `fill=`/`draw=` 语义色；比较/门控用小圆（`mdot=<族色>` 或空心 circle）；总线分叉用实心圆点。一个节点一个动作；永远同行的两个块合并。不自造样式名——vizstyle 已备好 `vstage`（阶段标签）、`vsym`/`vshape`/`vnote`（字号层）、`varr`（箭头）、`vbrace`（直角括号描边）、`vcurly`（花括号）、`mean`（底部含义框）、`band`（底带填充）。
- **连接器：** `varr` 箭头沿主向；反馈回路走外侧 `-|` 绕行并在通道里写回读标签；分支汇合用实心圆点作 bus。每条连接器画完立即镜像一条 `\vzwire`（见审计要点），「不穿非端点盒」才有机器背书。
- **语义色：** 按角色定色相（来源/变换/决策/评测各一色），不按视觉位置。
- **决策门：** 判负才介入的门用 `vcoral`，常态放行路径用主角色相；否决/接管路径单独画分支。门形默认小圆（`mdot`/空心 circle）；菱形判定门要 `\usetikzlibrary{shapes.geometric}`——不在 `.frag` 自动 preamble 名单里，需要菱形就改写 standalone `.tex` 自备导言。

## 布局规则

- 阶段带间 $\ge1.5g$；带内对象沿基线等距；列标签与列同中轴。纵向行距按「块高 + CROWD 阈值 10pt」算下限：两行 ~1.1cm 高的 `model` 块中心距实测须 ≥1.5cm，凭「等距摆开」拍 y 坐标必告警。
- 箭头标签写在箭头上方通道里，不贴在相邻对象上；注释列放图外右侧通道，与对应行对齐。
- 顶部放主张链或公式（`观测 → 类型化问题 → 校准分布` 这类契约链也合法）；底部含义框常用标签：**对象**（色 → 角色映射）与**机制**（频率/代价/触发条件）。
- 频次、代价、触发条件是 flow 图的论据——写在连接器标签或含义框里，别只画拓扑。

## 审计要点

- 同列/同泳道的块：`vaudit={class=列id}` 保证等大，`alignx`/`aligny` 保证中轴对齐。
- 泳道带：fit 节点自带名字，但**必须**在样式里带 `vaudit={}` 才会进审计文件——成员写 `inside=laneAbox` 而带盒没埋点会报 `inside: refers to unaudited`；`inside=` 是被验证的断言，子块真越出声明的父盒同样报 ERR。手算带用 `\vzbbox{laneA}{sw}{ne}` 注册，区域要挂标签用第四参数 `\vzbbox{laneA}{sw}{ne}[inside=panel]`。带间半重叠会被 COLLIDE 拦下。
- **连接器 `\vzwire`：** 每条 `\draw` 连接器镜像一条 `\vzwire{名}{途经点}{endpoint=端点盒}`——途经点写节点名、`节点.anchor` 或裸坐标 `x,y`，分号分隔（多词锚名必须 paren-wrap `(s6.north east)`，裸写剥光空格见陷阱节）；`via=` 声明有意穿过的中间件（bus 点、中继块），逗号分隔多目标：

    ```tex
    \draw[varr] (a) -- (b);             \vzwire{ab}{a;b}{endpoint=a,b via=laneAbox}
    \draw[varr] (bus) -| (ans.south);   \vzwire{ba}{bus;ans.south}{endpoint=bus,ans}
    \draw[varr] (a) -| (mid) |- (b);    \vzwire{amb}{a;mid;b}{endpoint=a,b via=mid}
    \draw[varr] (s) -- (t);             \vzwire{st}{s;t}{endpoint=s,t via=epool,lab1}
    % via=epool,lab1：一条线合法穿盒 + 穿自己路径上的标签盒，同句声明
    ```

    WIRE-CROSS（error）：线段进入既非 `endpoint=` 也非 `via=` 的 audited 盒超过 `--edge`（默认 2pt）——**带盒也算盒**：整条都在泳道带内的连线必须把带名写进 `via=`，否则报「穿带」。CROWD（warn）只管盒 - 盒：两个无声明关系的 audited 盒间距 < `--gap`（默认 10pt）时告警，有意贴近的两盒任一侧写 `adjacent=<对方>` 即豁免（判定对称，单边声明就够）。bus 分叉点与端口的接触不算碰撞——豁免在语义层，检查只管 audited 盒子。`via=` 不带 `endpoint=` 也合法——两端是裸坐标、没有端点盒可声明的干线就这么写。

    曲线边（`to[out,in]` 自环/弧）的镜像用三点折线逼近——途经点写「起点锚 + 顶点裸坐标 + 终点锚」：

    ```tex
    \draw[varr] (a.east) to[out=30,in=-30,looseness=5] (a.east);   % 自环
    \vzwire{aa}{a.east;1.8,0.7;a.east}{endpoint=a}                 % 顶点取弧顶坐标
    \draw[varr] (a.north) to[out=60,in=120] (b.north);             % 弧边
    \vzwire{ab}{a.north;3.2,1.6;b.north}{endpoint=a,b}
    ```

    WIRE-CROSS 按折线段查穿盒——顶点偏离真实弧线的部分只影响穿深读数，不影响穿/不穿判定；弧线有意擦过某盒就把该盒写进 `via=`。

- **声明式边列表：** 边多节点少时 `\usetikzlibrary{graphs}` 一次写全拓扑：`\graph[use existing nodes] { a ->[varr] b; a ->[varr] c; };`——节点位置照旧手排，graphs 只连边；每条边仍要配 `\vzwire` 才有 WIRE-CROSS 覆盖。

## 骨架

```tex
\node[vstage] at (1.0,0) {阶段 1};
\node[model, draw=vviolet, fill=vviolet!14,
      vaudit={class=laneA,inside=laneAbox}] (a) at (4,0) {...};
\node[model, draw=vteal, fill=vteal!14,
      vaudit={class=laneA,inside=laneAbox}] (b) at (8,0) {...};
\begin{pgfonlayer}{bg}
  \node[band, fit=(a)(b), inner sep=8pt, vaudit={}] (laneAbox) {};   % 成员先画，带后 fit
\end{pgfonlayer}
\draw[varr] (a) -- (b) node[midway, above, vshape]{频率/语义};
\vzwire{ab}{a;b}{endpoint=a,b via=laneAbox}   % 带内连线把带盒写进 via=
```

## 陷阱

- 整体缩放：`[scale=1.4]` 只缩坐标，节点文字、线宽、`minimum size` 原样——泳道带与阶段块的相对尺寸当场失衡。要连节点一起缩用 `transform shape`；更好的做法是改几何台账的单位长度，不碰 scale。
- 节点名在整个 `tikzpicture` 内全局：`\foreach` 里复用同一名字会静默重绑（后画的顶替先画的锚点）；`local bounding box` 相反，只在所在 `scope` 内可见，出 scope 引用报 "no shape named"。跨 picture 引用要 `remember picture` + `overlay` + 两遍编译。
- `right of=A`/`below of=A` 是弃用语法，按中心距摆放；positioning 库的 `right=of A`/`right=2.2 of A` 按边到边。同图混用两种，间距规则分裂——统一写新语法。
- `.. controls ..` 与 `to[out=,in=]` 的控制点计入画布包围盒：反馈回路的外绕弧线常把画布撑出一圈空白。用 `\useasboundingbox` 钉住画布，或给曲线段加 `overlay` 再手补留白。
- matrix 备选写法的间距：`column sep`/`row sep` 默认 `between borders`（边框到边框），想要格点等距写 `{between origins}`；单元格内容参差时用 `nodes={minimum width=.., minimum height=..}` 钉齐再谈对齐。
- `pgfonlayer{bg}` 只放填充与底带，文字/标签一律留在主层：bg 层文字会被同层后画的填充或主层对象盖住，而审计只查几何盒不查层序——这种压字机器发现不了，只能靠目检。
- **bus+tap 扇出**：一根总线分叉到多个下游块，别逐条从源点画放射线——先落一个实心 bus 圆点（`mdot`），干线 `\draw (src) -- (bus)`，每条支路 `\draw (bus) -- (dst)`；`\vzwire` 同样按干线/支路拆成多段写，bus 点进各段的 `endpoint=`。放射线共用一个起点盒时线段互相在对方盒边进出，WIRE-CROSS 解释成本反而更高。
- **卡片高度估算**：`model` 块多行内容时按 $\text{行数}\times\text{行距}+\text{inner sep}\times2$ 先算再摆——手写 y 坐标不估行高，带 `fit` 的泳道带会把超高内容撑破带盒或反过来压到邻带；两行以上文字一律 `\begin{tabular}` 或 `align=` 加 `text width` 钉住，别靠猜。
- **`class=` 等大断言不管行数**：`text width` 只钉宽度不钉行数——同 class 的多行节点行数不齐照样高度不等、等高断言照报；要么对齐行数，要么统一 `minimum height`。
- **fit 带的标签膨胀**：`fit=(a)(b)` 的带盒由成员包围盒 + `inner sep` 算出——`fit` 之后再用 `label=`/`pin=` 往带节点上挂文字，标签不进 fit 计算，会溢出带外压到邻居；带标题用带盒外缘锚点手动摆并 `adjacent=` 声明，或把标签节点一并塞进 `fit=(a)(b)(lbl)`。
- **fit 带内标签的膨胀级联**：反过来，塞进 `fit=` 名单的宽标签会把带缘向外撑，级联成与带外对象的一串碰撞（实测一个宽标签把带缘推出 0.4cm、下游连带 9 条 CROWD）——先缩标签本身（`text width`/`\\` 换行/降字号层），别逐条追次生碰撞。
- **`via=` 宁多勿少**：`\vzwire` 的 `via=` 写「线有意穿过的 audited 盒」——泳道带、bus 点、中继块都算；宁可把贴边擦过的盒也写上，也别漏——漏一个就是一条 WIRE-CROSS error，而多写一个合法穿过盒零成本（检查只看「穿了没声明的」）。
- **`node[midway]` 内嵌标签自撞**：路径中段的 node 是独立审计对象（要自己带 `vaudit=`），而 `\vzwire` 声明折线正穿它而过——一埋点就撞自己的导线报 WIRE-CROSS。做法：标签画成独立命名 `\node`，再把标签名写进该导线的 `via=`。
- **多条 `fit` 泳道带等宽**：各带宽度由该行最外成员决定，成员不齐的带用幻影 `\coordinate` pad 撑边——`\coordinate (pad) at (x,y);` 塞进 `fit=` 名单，phantom 不产生墨只参与包围盒。注意 pad 的 y 同样计入带盒：多行共用同一对 pad 会把每条带纵向拉到 pad 高度、带间互相 COLLIDE——pad 必须逐行一对，落在各行自己的 y 上。
- **窄带缝塞标签必撞**：<0.6cm 的带间缝隙里放标签几乎必然触发 CROWD/COLLIDE——预期路径是给相邻带/块写 `adjacent=` 声明，不是反复微调坐标。
- **含义框随动件按锚点跟**：`mean`/claim 类文本框实际高度不可预估——非 CJK 独有：纯英文长文案 `text width` 折行同样实测框高超估算 ~70%（CJK 实例 3.8cm vs 估算 ~1.3cm）——框下标识行、跟随注释别写死 y，用 `($(meanbox.south)+(0,-d)$)` 相对框底落位。可靠摆法：`anchor=north` 钉顶 + 先渲染读 `.audit` 实测盒再摆邻件，别按估算高度一次摆死。
- **卡片内数学式宽度预实测**：`\newlength` + `\settowidth` + `\typeout` 一次量出真实排版宽度再定 `text width`，比逐轮盲调省迭代。
- **node text 内别开字号组**：`{\small$..$}` 的 `}` 会提前闭合 text 花括号组、报 Giving up on this path——字号走 `font=` 键（`font=\small`）。
- **多行标签要显式 `align=`**：`vshape`/`vnote`/`lab` 等文字样式默认不带 `align`，`\\` 被吞成单行——多行标签写 `align=center`。
- **`\vzwire` 裸途经点剥光所有空格**：途经点首字符不是 `(` 就按裸节点名处理、内部空格全删再套括号——多词锚名 `s6.north east` 被折成 `(s6.northeast)`，编译报 `Unknown function 'northeast'`。多词锚一律 paren-wrap `(s6.north east)`：`(` 开头的途经点原文透传，内部空格保留。
- **容器节点作途经点必须写锚**：fit 带/父块这类容器节点进 `\vzwire` 途经点要写 `laneAbox.west`/`laneAbox.east`——裸名取中心锚，折线从盒心出发穿透带内已审计子块照样报 WIRE-CROSS；`.west`/`.east` 让线贴边出盒，再配 `via=` 声明合法穿件。

## 布局 oracle（坐标求解器）

`scripts/layout_oracle.py` 把节点尺寸 + 边列表解成中心坐标——$\ge 8$ 节点的 DAG/通信拓扑、层级结构手排已经划不来时用它打底，再回到手排纪律。

```
python3 scripts/layout_oracle.py dag.json --emit-tex
# stdout 第 1 行 {"id":[x,y]}，其后可选 \coordinate (id) at (x,y); 行
# stderr 是状态行：ok:/warn oracle:/ERR oracle:
```

输入 `{"nodes":[{"id","w","h"}],"edges":[["a","b"]],"options":{"direction":"TB|LR","layer_gap","node_gap"}}`（cm）。输出是 tikzpicture 直角坐标（x 右 y 上），原点在布局包围盒左下角（最左/最下盒边贴 0）。`--backend auto`（默认）按输入形状选路：环断后每点入度 ≤1 的**纯树/森林**直接走 simple 的 tidy-tree 路径（Reingold-Tilford 轮廓法——lualatex Sugiyama 实测在纯树上打乱兄弟序出可见交叉，所以不试它）；其余图先试 lualatex——pgf graphdrawing 的 Sugiyama 实现，`\graph[layered layout]` 摆节点再 `\typeout` 回收中心坐标——不可用/失败回退内建 simple 分层器（longest-path 分层 + barycenter 两遍扫）并打 `warn oracle:`；显式 `--backend lualatex|simple` 可钉死（simple 端纯树同样走 tidy）。

- oracle 只产坐标：节点样式、语义色、`vaudit` 埋点、`\vzwire` 全照旧手排。坐标落进几何台账后微调是常态——层内对齐、给标签通道让位、把 oracle 摆烂的孤立点挪去注释列。
- `level/sibling distance` 是中心距，oracle 取「最大节点尺寸 + gap」的保守下限；要在层间塞连线标签就把 `layer_gap` 调大，别在产出后硬挤。
- 有向环（反馈回路）：simple 端丢反馈边再分层（`warn oracle:` 报丢了哪几条），回路本身照旧手绘外侧绕行；lualatex 端能摆但连线还是要人工走通道。
- 孤立节点进 layer 0 一字排开——占位可以，语义上多数该删或归注释列。

## codegen（语义台账 → 埋点骨架）

`scripts/codegen.py` 把几何台账直接翻成带 `vaudit` 埋点的 standalone 骨架——适合「台账已定、逐块手排太机械」的图，生成后再人工填语义与精修。

```
python3 scripts/codegen.py ledger.json -o fig.tex --assets ../assets/tikz
```

台账字段（cm，canvas 为正文区 `[0,w]x[0,h]`，mean/标识行自动落底边之下）：

| 字段      | 形状                                                                                                |
| --------- | --------------------------------------------------------------------------------------------------- |
| `canvas`  | `{"w","h"}` 名义正文区；缺失时按内容包围盒推 mean 位置并 `warn codegen:`                            |
| `boxes[]` | `id,class,style,x,y,text` + 审计键 `inside/alignx/aligny/eqwh/adjacent/overlap`（值可字符串或列表） |
| `bands[]` | `id,sw,ne`（`[x,y]` 或 `"x,y"`）+ 可选 `style`（缺省 `band`）/`tags`（进 `\vzbbox` 第四参数）       |
| `wires[]` | `id,pts,endpoint,via` + 可选 `style`（缺省 `varr`）；pts 元素可节点锚/`"x,y"` 裸坐标/`(..)` 原样段  |
| `mean`    | `{"text"}` 底部含义框（`text width` 取 canvas 宽 -1cm）                                             |
| `caption` | `{"text"}` 标识行；缺省时留注释占位，不造空节点                                                     |

- codegen 管几何正确性：自洽台账产出的骨架编译即审计全绿；不自洽处生成期就打 `warn codegen:`——未知引用、坐标越出 canvas、band 角点颠倒（自动交换）、`inside` 目标不覆盖 box 中心。
- 语义文字仍人写：`text` 字段是占位种子，分工是「机器摆盒子、人写论证」；生成物是普通 `.tex`，接管编辑后 codegen 不进交付链。
- 与手写/oracle 的关系：oracle 产坐标可以喂给台账的 `x,y`；复杂结构（matrix、fit 带、装饰唇、跨带回路）照旧手写或后补，别指望台账装下所有语法。
