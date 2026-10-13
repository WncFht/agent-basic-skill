# plot 语法 — pgfplots 曲线 + 示意混合

图的一半是真实函数曲线/参数化轨迹，另一半是示意结构：理论 bound、相图、机制几何。

## 结构件

- **axis 环境：** `axis lines=left`、`Stealth` 箭头轴、`trim axis left/right`；非线性用 `xmode=log`、`x dir=reverse` 等真实变换，不手绘假轴。
- **曲线族：** 同一族用同色不同明度（`black!45/70/blue`），legend 极简或改节点标注；参数化曲线用 `domain`+`samples`。
- **标注点与轨迹：** 关键点 `\addplot[only marks]`，跨图的运动方向用粗 `Stealth` 弧线 + sloped 标签，写「谁向哪动」。
- **混合排版：** 示意块与 axis 用 `minipage[t]` 并排于同一 `tikzpicture` 之外，或两个 `tikzpicture` 并排；子图标记 `(a)`/`(b)` 用小字居中在各自下方。
- **示意侧：** 条形/块用矩形填充直接画，坐标与曲线侧共享几何台账（同一根 $\delta$ 轴两侧刻度必须同尺度或明确断裂）。

## 规则

- 曲线必须真算：bound、密度、轨迹写真实函数式或数据点，不画「示意图式曲线」冒充定量关系；纯示意就离开 axis 环境。
- 示意侧与曲线侧共享符号颜色：同一变量同色。
- 区间底色带（warmup 段、相区）画在 `bg` 层，上下边取 current axis 的边界而非手写 y 值（ylim 一改手写值就错位）。注意 `axis cs:` 坐标不能直接进 `a |- b` 直角语法（坐标解析器不认）——先把轴点落成具名坐标再取直角分量：

    ```tex
    \path (axis cs:x0,0) coordinate (wx0) (axis cs:x1,0) coordinate (wx1);
    \begin{pgfonlayer}{bg}
      \fill[band] (wx0 |- current axis.south west) rectangle (wx1 |- current axis.north east);
    \end{pgfonlayer}
    ```

    这段 `\fill` 整体挪到 `\end{axis}` 之后同样成立：`current axis` 与 `\coordinate` 落名在轴外仍有效，且更贴「审计轴外」的摆法——轴内/轴外两种位置二选一。

- `axis cs` 里的 text node 会进 audit 包围盒：区间标注、轴内图例字都算 COLLIDE 候选，放置时把曲线与别的文字一起算间距。
- 底部含义框标签常写 **轴/判读**（曲线怎么读）与 **机制**（训练把点推向哪）。

## 骨架

```tex
\begin{minipage}[t]{0.40\linewidth}\centering
\begin{tikzpicture} ... 示意条 ... \end{tikzpicture}\\[1pt]
{\scriptsize (a)}
\end{minipage}\hfill
\begin{minipage}[t]{0.56\linewidth}\centering
\begin{tikzpicture}
\begin{axis}[xmode=log, x dir=reverse, axis lines=left, ...]
  \addplot[black!45, thick] {0.02*(ln(0.02/x)-1)};
  \draw[-{Stealth}, very thick, vcoral] (axis cs:...) .. controls .. (axis cs:...)
      node[pos=0.6, sloped, below, vcoral]{训练方向};
\end{axis}
\end{tikzpicture}\\[1pt]
{\scriptsize (b)}
\end{minipage}
```

## 审计埋点处方

- **埋点位置：** `\vzbbox`/`\vzwire` 一律放 `\end{axis}` **之后**——这两个两段式宏在 axis 体内会被 pgfplots 的延迟执行拆散，报 `No shape named vz@a` 且 `\pgfextra` 字面量漏进排版。口诀「墨可轴内（bg 层 `\fill` 可用）、审计轴外」：axis 体内只留 `\coordinate` 落名。
- **示意侧的块**照常埋点：`vaudit={class=blk}` 锁等大、跨图呼应的块用 `eqwh`/`aligny` 与对照块挂钩。
- **轴内标注节点** `vaudit={}` 进 COLLIDE 检查——`axis cs` 里的 text node 本来就计入包围盒，埋点让它显式可查。
- **区间带与整轴框**是区域不是节点：先 `\coordinate` 落轴点，再 `|-` 取直角分量注册 `\vzbbox`（第四参数可挂 `inside=`/`adjacent=` 标签）：

    ```tex
    \path (axis cs:x0,0) coordinate (wx0) (axis cs:x1,0) coordinate (wx1);  % axis 体内
    % \end{axis} 之后：
    \vzbbox{warmup}{(wx0 |- current axis.south west)}{(wx1 |- current axis.north east)}
    \vzbbox{plotbox}{(current axis.south west)}{(current axis.north east)}
    ```

    coverage 把 `\fill` 矩形与 `\vzbbox` 按四角点对匹配：两处角点表达式必须逐字节相同（仅空白归一化）——`\fill` 里写了什么，`\vzbbox` 就原样照抄，换成等价写法就认不出是同一矩形。

- **轴内连接器**（训练方向弧线等）同样可 `\vzwire`：途经点若是 `axis cs:` 坐标，先 `\coordinate` 命名再写进途经点列，避免坐标系串味。`via=` 也接受节点名——wire 可合法穿过自己路径上的标注盒（`via=标签名`），不算 WIRE-CROSS。
- 跨 tikzpicture 的两块（示意/曲线并排）无法互审——符号颜色一致性靠语义台账自查。

## 陷阱

- 轴的缩放走 `width`/`height`/`unit vector ratio`，不是 `[scale=]`——外层 tikzpicture 的 scale 只缩坐标不缩轴内字号与线宽，示意侧与曲线侧立刻失衡。
- pgfplots 的 `width=`/`height=` 含刻度标签与轴标的留白：声明 `width=6cm` 时轴框本身只有 ~5cm，剩下的是 tick label 与 label 的边距。几何台账按轴框算宽度时要留余量，或者用 `scale only axis` 让 `width` 只管轴框。
- 轴内 `\coordinate`/`\node` 名在同一 `tikzpicture` 内全局有效，`\end{axis}` 之后仍可引用（跨 picture 才要 `remember picture`）；`\foreach` 里复用名字静默重绑。
- `right of=A`/`below of=A` 是弃用语法（中心距）；标注摆放用 positioning 库的 `right=of A`/`above=2pt of A`（边到边）。
- `.. controls ..`/`to[out=,in=]` 的控制点计入路径包围盒：轴内默认 `clip=true` 裁得住出界弧线，但 axis 外的示意弧线与 `clip=false` 的轴内曲线会把画布撑出空白边——用 `\useasboundingbox` 钉住或弧线加 `overlay`。
- `\matrix[matrix of nodes]` 排图例/符号表时注意 `column sep`/`row sep` 默认 `between borders`，等距格点写 `{between origins}`；格子**不要**在 `nodes={}` 里挂 `vaudit`（排版前读锚坐标作废、假 COLLIDE），要审计就事后 `\path \vaudit{M-1-1}{...}` 逐格注册。
- `\vzwire` 途经点写 `axis cs:` 坐标必须连环境一起：`axis cs` 只在 `axis` 环境内有效（环境外写 `\vzwire{w}{a; (axis cs:0,0.1)}{...}` 编译报 `Missing \endcsname`——途经点被当成坐标系名解析失败），环境外的轴点一律先 `\coordinate` 落名再进途经点。途经点首尾是 `(` 时原文进 pgf 扫描器，`axis cs:` 与 `($...$)` calc 的内部空格都合法；非 `(` 开头按裸节点名处理、内部空格全删。
- `\vzwire` 审计的是声明的折线途经点，不是画出来的曲线本体：弧线连接器（`to[out=,in=]`、`.. controls ..`）在审计眼里是途经点连成的**弦**——弯出包围盒的弧腹穿盒检查不到。弧线穿敏感区时途经点沿弧腹多钉两点，别只写两端。
- 星形/正多边形节点标记（`star`、`regular polygon` 等 shape）需 `\usetikzlibrary{shapes.geometric}`——`.frag` 自动 preamble 未含且无追加逃生舱，改走 standalone `.tex` 自备导言；纯标记点也可用 `\addplot` 的 `mark=star`。
- fandol 没有 ★(U+2605) 字形：含义框里写字面 ★ 静默渲成空白，pdftotext 查无此字——文本侧 `$\bigstar$`，节点侧 `star` shape。
- `inside=` 是完全包含断言：标签骑跨带边会同时报「inside escapes declared parent」和 COLLIDE 两条——要么整体进带，要么改 `overlap=`。
- `\addplot table{data.csv}`、`\input{sub.tex}`、`\includegraphics{img.png}` 这类相对路径资源照常可用：编译虽在 tempdir 里跑，渲染器已把**源文件所在目录**注入 `TEXINPUTS`（同名冲突时编译目录优先）。裸文件名只查源目录直系与显式子目录路径——`sub/data.csv` 有效，深层目录里的裸文件名不解析。
- **pgfplots `at={(x,y)}` 不带单位按 pt 解析**：`at={(15.7,4.35)}` 落点是 15.7pt≈0.55cm 不是 15.7cm——轴被丢到原点附近，连带一串 COLLIDE/WIRE-CROSS 次生告警（首轮 16 ERR 实证）。axis 摆放坐标一律写全单位 `at={(15.7cm,4.35cm)}`——tikz 本体裸坐标默认 cm，pgfplots 的 `at` 键不同源，别混。
- **render_tex 失败路径只吐 stderr 尾部**：`FAIL xelatex` 只打印输出末 ~2500 字符，根因上下文常在更早处——失败时完整 build log 已落到输出目录 `<stem>.log`，排障先翻它，别在终端尾部找根因。
