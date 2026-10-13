# board 语法 — 分类板、设计空间与榜单

项的集合被两个以上分类/评价维度切分的图：设计空间（族 × 判决）、leaderboard、象限、对比矩阵。

## 结构件

- **列带：** 每个族/类别一条 `band` 底色的列带（`\fill[band]` = vgray 弱填充 + 圆角，族带可 `band=<族色>`）+ 顶部族头（`\small\bfseries` 名 + `\scriptsize` 副标题）。列带等宽等高，间距均匀。
- **卡片：** 列带内等大的项卡，`text width` 统一、行距一致；编号与正文条目对应时把编号写进卡面。
- **双通道编码：** 填充色编码维度 A（如外部判决），边框编码维度 B（如自评），图例声明两个通道，读者可交叉读。
- **图例：** 内容角落一块白底小框，列出填充/边框/形状的全部语义；只有两个通道时也可并入底部含义框。
- **文字注记：** 列内「已验证先例」这类说明用 `\scriptsize` 中性灰放该列底部通道，不伪装成卡片。

## 布局规则

- 列带是声明容器：卡片 `vaudit={inside=带id}`；列带用 `\vzbbox` 或节点 + `\path \vaudit` 注册。
- 卡片网格 `class` 审计等大；同列卡片 `alignx` 对齐；列间距 vs 列带宽度的视觉平衡用几何台账先算。
- 顶部放主张句（`十六条路径：契约 → 族 × 判决`），底部含义框标签按图改写（如 **判决/稳定性**）+ 标识行。
- 竖向尺寸的「台账先行」实际是四轮循环：估计 → 渲染 → 读 .audit 实测盒高 → 回填台账（空估烧过三轮才长记性）。起步参考：CJK 两行族头 ≈31pt 高；`minimum height` 卡被 3 行正文撑到 ≈48pt；CROWD 默认 10pt 比直觉严（0.36cm 间距也告警）——行距安全起点「行 pitch ≥ 卡高 + 0.4cm」。

## 审计要点

- 列带 `\vzbbox{bandI}{sw}{ne}` 注册区域（骨架已示范）；区域要挂标签用第四参数 `\vzbbox{bandI}{sw}{ne}[inside=frame]`，有意贴边的两条带任一侧写 `[adjacent=bandJ]` 免 CROWD 告警（对称判定）。`adjacent=` 不限于带↔带——任意两个已埋点盒之间都生效（实测场景：紧贴含义框的说明行）。
- 卡片 `vaudit={class=card,inside=bandI}`：`class` 锁等大、`inside` 消 NEST——注意 `inside=` 是被验证的断言：带盒没埋点报 `refers to unaudited`，卡片真越出带界也报 ERR；同列卡片补 `alignx` 对齐中轴。
- 族头、图例、底部含义框都是包围盒——`vaudit={}` 或 `\vzbbox` 埋进去，压到卡片的文字会被 COLLIDE 拦下。含义框直接用 `\node[mean, text width=...]` 起。
- 双通道编码（填充色/边框色）只是视觉通道，不进审计标签；几何不变量只管等大与包含。
- 列带是「先画容器再填卡片」的顺序，用不了 `fit`——`fit` 必须等成员就位；这就是 board 骨架保留手算矩形 + `\vzbbox` 的原因。

## 骨架

```tex
\foreach \i/\x in {0/0,1/3.8,2/7.6,3/11.4}{
  \begin{pgfonlayer}{bg}
    \fill[band] (\x,0) rectangle (\x+3.4,8.6);
  \end{pgfonlayer}
  \vzbbox{band\i}{(\x,0)}{(\x+3.4,8.6)}
}
\node[card, fill=vorange!30, vaudit={class=card,inside=band0}] ...;
```

## 备选写法：matrix of nodes

卡片是规整网格时可换 `\usetikzlibrary{matrix}` 的 `\matrix[matrix of nodes]`：单元格自动成节点并按 `M-行-列` 命名，`row \i`、`column \j` 样式钩子做按列着色；装了 tikz-ext 可叠 `matrix.skeleton` 做格级 fit 框。审计注意：**不要**在 `nodes={}` 里挂 `vaudit`——格子埋点在排版前读锚点，坐标作废会报假 COLLIDE；要审计只在 `\matrix` 之后 `\path \vaudit{M-1-1}{class=card};` 逐格注册。空单元格默认不生成节点，要 retag 空格须加 `nodes in empty cells`。双通道边框、列内脚注这类异质定制走钩子反而更绕——列带 + 异质卡片的板仍用展开式写法。

## 陷阱

- 整体缩放：`[scale=]` 只缩坐标不缩卡片文字与线宽，列带宽度台账当场失真；要整体缩放用 `transform shape`，或改台账单位。
- 节点名在整个 `tikzpicture` 内全局：`\foreach` 列循环里 `band\i` 这类带索引名是义务而非习惯——重名静默重绑锚点；`local bounding box` 只在所在 `scope` 内可见。
- `right of=A`/`below of=A` 是弃用语法（中心距）；卡片堆叠用 positioning 库的 `below=of A`/`below=1.8 of A`（边到边），别两种混写。
- `.. controls ..`/`to[out=,in=]` 的控制点计入画布包围盒：斜向强调箭头会把板面撑出空白边，必要时 `\useasboundingbox` 钉住或 `overlay`。
- matrix 写法的间距：`column sep`/`row sep` 默认 `between borders`（边框到边框），等距格点要 `{between origins}`；列宽被最宽卡片撑歪时用 `nodes={text width=..}` 或 `minimum width` 钉齐。
- CROWD 的 `--gap` 默认 10pt 比直觉严格——2.5mm 的「明显分开」间距也告警，贴邻盒子提前写 `adjacent=`。含义框 `\node[mean, text width=..]` 内 CJK 长句静默折行会让盒高暴涨，症状只在下游以 COLLIDE/CROWD 出现——行宽估计留 ~10% 余量（CJK `\small` ≈9.7pt/字），框下方元素按渲染后的实测盒高排布，别按草稿行数算。
- 双通道图例的色块 chip：`\fcolorbox{edge}{white}{\rule}` 渲出来芯是黑的——`\rule` 恒为墨色、与底色无关。可用写法是盒内放零宽支撑 `\rule[-2pt]{0pt}{8pt}\hspace{10pt}`（撑高再给宽）。vizstyle 没有现成 chip 宏。
- xcolor 链式混合在 `\fcolorbox` 参数里炸：`#1!70!black` 若 `#1` 已是 `vteal!55` 这类混合式，展开成 `vteal!55!70!black` → `Undefined color '70'`。先用 `\colorlet` 预混成具名单色再传参，别在宏参数里二次链混。
- fandol 缺字形静默渲空白：★(U+2605)、①②③④ 圈号、■(U+25A0) 全中招（pdftotext 也无字）。替代：星 `$\bigstar$` 或 star shape、圈号 `\textcircled{\scriptsize N}`、方块用带色文字或小 `\fill`。
