# recipes 配方族 — 专项图形的 token 包

四套面向高频专项图形的 vizstyle 配方：pgm plate（概率图板记号）、nn-blockstack（残差跳连层栈）、seq-lifeline（UML 序列/生命线图）、搜索树 sn-edge 三态。每套给 token、骨架与审计埋点处方；几何/语义不变量与 `flow.md` 同一套（一个绘制对象 = 一个语义对象、连接器配 `\vzwire`、贴近写 `adjacent=`）。

## pgm plate — 概率图板记号

适用：贝叶斯网/生成模型 plate notation（LDA、GMM、变分推断图）。tikz-bayesnet 四件套：潜在变量空心圆 `lat`、观测变量阴影圆 `obs`（`vgray!45` 填充）、超参无边小字 `const`、重复采样细框板 `plate`；板角计数标签用 `plab` 通道。

板用 `fit` 库把成员圈进：`fit=(z)(w)` 的成员未定边距给不对称值——`inner xsep=10pt, inner ysep=14pt`，加深 y 口袋让角标落在成员圆下方的空隙里。嵌套板直接 `fit=(theta)(plateN)` 圈住内板节点。

```tex
\node[const, vaudit={}] (al) at (-1.6,1.4) {$\alpha$};
\node[lat, vaudit={class=rv}] (th) at (0,1.4) {$\theta$};
\node[lat, vaudit={class=rv,inside=pl}] (z) at (0,-0.6) {$z$};
\node[obs, vaudit={class=rv,inside=pl}] (w) at (1.7,-0.6) {$w$};
\node[plate, fit=(z)(w), inner xsep=10pt, inner ysep=14pt, vaudit={}] (pl) {};
\node[plab, anchor=south east, vaudit={inside=pl,adjacent=w}]
  at ($(pl.south east)+(-3pt,3pt)$) {$N$};
\draw[varr] (th) -- (z);
\vzwire{tz}{th;z}{endpoint=th,z via=pl}   % 穿过板缘的连线把板写进 via=
```

审计埋点处方：

- **RV 等大**：全部 `lat`/`obs` 圆打同一 `class=rv`（直径已由 `minimum size` 钉死）。
- **成员关系**：`inside=` 是被验证的断言——成员必须真在板内，逐层写（`inside=pl,inside=pl2`）；板 `fit` 自带名字但照样要 `vaudit={}` 才进审计。
- **角标**：`plab` 标签写 `inside=板` + `adjacent=<最近成员>`——角标贴成员是 plate 记号的结构特征，不是排版瑕疵。
- **via= 宁多勿少**：完全在板内的连线也「穿过」板（审计量穿透深度不是边界穿越）——每个包线的板都进 `via=`，多层板全列。

陷阱：`const` 与 `lat`/`obs` 不要混 `class`（无边字 vs 有框圆尺寸必异）；`fit` 之后再挂 `label=`/`pin=` 不参与 fit 计算会溢出板外，角标一律走 `plab` 节点。`const` 节点有无边字的真实盒高——与顶部 claim/公式行间距 <10pt 吃 CROWD，板图上方放公式给 ≥0.5cm 净空或写 `adjacent=`。

双层套娃（外板圈「内板 + 内板角标」）逐层把 `inside=` 写全——成员、内板、内板角标都要声明进外板：

```tex
\node[lat, vaudit={class=rv,inside=pl,inside=pM}] (z) at (0,-0.6) {$z$};
\node[obs, vaudit={class=rv,inside=pl,inside=pM}] (w) at (1.7,-0.6) {$w$};
\node[plate, fit=(z)(w), inner xsep=10pt, inner ysep=14pt,
      vaudit={inside=pM}] (pl) {};                       % 内板本身是外板成员
\node[plab, anchor=south east,
      vaudit={inside=pl,inside=pM,adjacent=w}] (plN)
  at ($(pl.south east)+(-3pt,3pt)$) {$N$};
\node[plate, fit=(pl)(plN), inner xsep=14pt, inner ysep=18pt,
      vaudit={}] (pM) {};                               % 外板圈 内板 + 内板角标
\node[plab, anchor=south east,
      vaudit={inside=pM,adjacent=pl,adjacent=plN}]      % 最近邻居两个都写
  at ($(pM.south east)+(-3pt,3pt)$) {$M$};
```

外板角标的 `adjacent=` 目标组合是最近邻居集——内板盒与内板角标都贴它，两个都写（`adjacent=pl,adjacent=plN`）；漏一个就吃 CROWD。

## nn-blockstack — 残差跳连层栈

适用：Transformer block 层栈、ResNet 块栈——主干一串 `model` 层块 + `vadd`（$\oplus$）汇合圆 + tap 分接点（`mdot=vink`）+ 侧通道 identity 跳连。配色按子层语义（attn/mlp/embed/head 各一族色）。

```tex
\node[mdot=vink, vaudit={class=tap}] (s1) at (0,1.1) {};
\node[model, draw=vviolet, fill=vviolet!14, vaudit={class=blk,alignx=emb}] (sub) at (0,2.4) {attn};
\node[vadd, vaudit={class=add,alignx=emb}] (ad1) at (0,3.7) {$+$};
% 跳连成对宏（通道 x 自定，西负东正）：
\nskipw{s1}{ad1}{-2.3}{sk1}{via=bandB1}                         % 西通道：draw+vzwire 一条语句
\nskipwe{s1}{ad1}{2.3}{sk2}{}                                   % 东通道镜像宏（双通道同起止也行）
% 等价底层写法（即宏的展开形态；手写时代替宏用，别与宏并写——同一条旁路画两遍）：
\draw[nskip=-2.3] (s1) to (ad1);                                % 样式式：四段正交旁路一行
\vzwire{sk3}{s1.west;(-2.3,0 |- s1.west);(-2.3,0 |- ad1.west);ad1.west}{endpoint=s1,ad1}
```

`nskip=<x>` 是 `to path` 样式：从 `tap.west` 绕通道 x 回 `add.west`（`nskipe=<x>` 走东缘），路径与 `varr` 同型带圆角；`\nskipw`/`\nskipwe` 把样式 draw 与同形 `\vzwire` 打包成一条（第五参接 `via=` 等附加声明，无则 `{}`）。起止必须给命名节点/coordinate——样式内部取 `.west`/`.east` 锚。

审计埋点处方：

- **层叠等大**：`class=blk` 层块、`class=add` 汇合圆、`class=tap` 分接点各打一类；单列主干用 `alignx=<底块>` 链锁中轴。
- **带关系**：block 容器带用 `band, fit=(...)`；带内成员写 `inside=带`；跳连穿带（进出都算）把带写进 `via=`。
- **tap 贴带无中间态**：分接点要么整体进带（`inside=`）要么离带边 ≥10pt，贴带缘是必撞区。

陷阱：`vadd` 不带 `node contents`（与 `vaudit` 的 append-after-command 冲突），汇合文本照常写 `{$+$}`；`\draw[nskip]` 内建 `varr`，不要再叠箭头样式；块名 `model` 多行文本按行数×行距+inner sep×2 估实测高再排 y——名义尺寸≠实测尺寸是本族最大卡点。`\nskipw`/`\nskipwe` 无沿线 label 参——跳连的 identity 标注手写独立 `\node[lab]`（内嵌 midway 节点会自撞 wire），并把标签名补进该线宏第五参 `via=`。「×L 重复」无一等表达——借 pgm-plate 的 `plab` 角标 + `band fit` 组合（框内单元照旧全画）；非对称带缘（只有一侧要撑边）手放 phantom `\coordinate` 进 `fit=` 名单——phantom 不产墨只参与包围盒，y 同样计入、逐侧各放各的。

### 层栈节距台账

残差栈先把几何台账钉死再放节点——纵坐标一律从台账公式算出来，不逐点拍脑袋：

- **单元 pitch**：一个残差单元 = tap 分接点 → 层块 → `vadd` 汇合。记块实测高 `h`（`minimum height` 与多行文本实测取大）、tap→块底间距 `g1`、块顶→add 间距 `g2`、add→下一 tap 间距 `g3`，则 pitch `P = g1 + h + g2 + g3`；第 k 单元的 tap 放 `y0 + kP`，blk/add 同步平移。P 全栈一致比绝对值更要紧——参差 pitch 肉眼即错位。
- **旁路通道宽**：通道 x 取 `±(w_blk/2 + m)`，`w_blk` 是块实测宽（`text width` + inner sep×2 + 边框），`m ≥ 12pt`（≈0.42cm）——再小竖腿贴块缘既糊又可能蹭进 WIRE-CROSS 的 edge(2pt) 容差；多条并行通道逐级再让 ≥0.4cm 防竖腿重合。默认西侧负 x，西缘拥挤或成对跳连才上 `\nskipwe`。
- **vadd 落位**：汇合圆钉主链轴线（`alignx` 链锁中轴）、在所属块上方 `g2` 处；跳连回到 `add.west`/`add.east` 而非块顶——残差语义是「块输出与旁路在 add 相加」，汇到块顶就画成了穿线。tap 在下方 `g1` 对称。
- **穿带声明**：栈外套 `band`/`plate` 容器带时，旁路竖腿进出带缘一律把带写进宏第五参 `via=`；带内 tap 写 `inside=`。
- **×L 重复**：L 小逐单元全画全埋点；L 大两种画法——首尾两单元 + 中间 `$\vdots$` 占位节点（照样命名、`vaudit`、按 P 占位），省略段内不画 wire（审计只能核对画出的段）；或把一个单元用 `plate` 式 `fit` 框圈起、`plab` 角标写 `$\times L$` 表示整体重复。两法不混：省略段里出跳连是画了不存在的东西，板框内每单元照旧全画。

```tex
% 台账：h=1.0、g1=0.95、g2=0.72、g3=0.78 → P=3.45；通道 x=±2.3（test 的 NN_FRAG 即此账）
\node[mdot=vink, vaudit={class=tap}] (s1) at (0,1.15) {};
\node[model, draw=vviolet, fill=vviolet!14, text width=2.0cm,
      minimum height=1.0cm, vaudit={class=blk,alignx=emb}] (b1) at (0,2.60) {attn};
\node[vadd, vaudit={class=add,alignx=emb}] (ad1) at (0,3.82) {$+$};
\node[mdot=vink, vaudit={class=tap}] (s2) at (0,4.60) {};   % = s1+P，下一单元同此平移
\nskipw{s1}{ad1}{-2.3}{sk1}{}
```

## seq-lifeline — UML 序列/生命线图

适用：协议时序（选举、握手、心跳）、RPC 调用时序、actor 交互。件：参与者头盒（`model`+角色色）、`lifeline` 虚线、`act=<族色>` 激活条（钉宽 0.24cm、`anchor=north` 从条顶时刻向下长）、`\seqnum` 自增序号、`\selfmsg`/`vselfmsg` 自消息猪尾。

```tex
\node[model, draw=vteal, fill=vteal!12, minimum width=1.8cm, vaudit={class=hdr}] (S1) at (0,0) {S1};
\draw[lifeline] (S1.south) -- (0,-3.6);
\vzwire{lf1}{S1.south;(0,-3.6)}{endpoint=S1 via=a1}      % 生命线先画，via= 列全被盖条
\node[act=vteal, minimum height=2.0cm, vaudit={adjacent=S1}] (a1) at (0,-0.7) {};
                                            % 后续条写 vaudit={adjacent=..,eqww=a1} 锁等宽；
                                            % 别写 class=act——class= 断言宽高两全等，
                                            % 激活时长不同的条天然不等高，照抄即违例
\coordinate (m1a) at (0.12,-1.5); \coordinate (m1b) at (4.38,-1.5);   % 条缘端点
\draw[varr] (m1a) -- (m1b)
  node[midway, above=1pt, vnote, vaudit={}] {\seqnum~\texttt{RequestVote}};
\vzwire{mm1}{m1a;m1b}{endpoint=a1,a2}
\coordinate (s1o) at (0.12,-2.1);
\selfmsg{s1o}{a1}{m2}{\seqnum~become \textsc{candidate}}{}
\path \vaudit{m2l}{};          % 宏产标签节点补埋点（名字 = <id>l）
\coordinate (s2o) at (-0.12,-1.8);
\pic[selfw=-0.9, vaudit={}] at (s2o) {vselfmsg={a1}{m3}{\seqnum~checkpoint}{}};
                              % pic 形：出口写 at，vaudit 挂语句上即审计 <id>l
```

审计埋点处方：

- **条宽机检**：`act` 钉 `minimum width=0.24cm`，全图条等宽用 `eqww=<首条>` 链式断言（不等宽就是图错）。`class=` 断言宽高两全等——激活条时长不同天然不等高，`class=act` 只适用于等长条，一般情况是陷阱。
- **条贴头盒是常态**：条顶紧贴头盒底缘，间距 <10pt 触发 CROWD——在条上写 `adjacent=<头盒>` 豁免。
- **消息端点**：`\draw` 两端必须是条缘上的命名 `\coordinate`（条的 `.east/.west` 是纵向中点不是到达时刻）；跨中列消息把被穿的中间条写进 `via=`。
- **生命线**：`\draw[lifeline]` 先画、激活条后画（条的不透明填充盖掉中段虚线）；其 `\vzwire` 的 `via=` 列全被盖住的条名。
- **\selfmsg / vselfmsg**：`\selfmsg{出口坐标}{条名}{id}{标签}{附加tags}` 一次产折回 draw + `\vzwire{w<id>}`（endpoint=条名）+ 标签节点 `<id>l`；标签要进审计就 `\path \vaudit{<id>l}{};` 补埋点（分号不可省——`\vaudit` 是 `\pgfextra` 宏不是路径操作）。第五参附加声明追加进 `endpoint=` 后——猪尾要合法穿过 audited 件（如序号徽章）写 `{via=bdg}`，同 `\nskipw` 第五参惯例，无则 `{}`。pic 形等价写法 `\pic[.., vaudit={}] at (出口) {vselfmsg={条名}{id}{标签}{附加tags}}`——`vaudit=` 挂在 pic 语句上恰好审计 `<id>l`（语句的 vaudit 落在 pic 体内最后一个节点即标签上），同时让 coverage 认下这条 `\pic`。折回尺寸 `\tikzset{selfw=..,selfh=..}` 或 pic 选项里给 `selfw=..`（`selfw` 负值向左折）。标签节点已内建 `align`（右折 `align=left`、左折 `align=right`），长标签直接 `\\` 折行——单行右延超过生命线间距 −`selfw` 探出 −2×10pt CROWD 余量会伸进下一条生命线通道，被其 `\vzwire` 报 WIRE-CROSS，先折行再排。
- **序号徽章要自造样式**：`\seqnum` 只产裸数字（`\textbf{n}`），等大圆形徽章先定义 token——`\tikzset{bdg/.style={circle, draw=vink, fill=vink!14, inner sep=0.5pt, minimum size=0.3cm, font=\scriptsize\bfseries}}`，节点写 `\node[bdg, vaudit={class=bdg}] (bdg1) at .. {\seqnum};` 用 `class=` 锁全图等大；徽章压在消息线上的，该线 `\vzwire` 把徽章名写进 `via=`（坐线合法穿过）。

陷阱：`\seqnum` 是文档级计数器（`\setcounter{vzseq}{0}` 复位），图间记得清零；found/lost message 的图外端点必须钉命名 `\coordinate`（裸坐标 `\draw` 过不了 coverage）；pic 体内 `\vzwire` 默认记 pic 局部坐标——扫描不吃 `at` 平移、`\pgfpointanchor` 还逆变换——`vselfmsg` 内部把四个航点先过 `\pgfpointtransformed` 折成绝对坐标再以字面量交 `\vzwire`（重扫描原样透传），其他自制 pic 里直接 `\vzwire` 仍会落错位，要么同法折算要么把 wire 留在 pic 外；`vselfmsg` 的 pic 不要起 `(名)`——pic 名只当 name prefix（内部标签变 `<名><id>l`），不注册成可 `\vaudit` 的 shape。

## sn-edge — 搜索树三态边

适用：beam search、MCTS、trie、决策树——树形展开带剪枝与返回路径。三态 token 节点/边双用：存活 `snkeep`（vteal 实线箭头/浅填）、剪枝 `snghost`（vgray 虚线 ghost、无箭头、字色灰）、返回路径 `snret`（vorange 高亮），根用 `snroot`（vink）。`\draw` 取线色/箭头、`\node` 取边框/底/字色，同一 token 两侧一致。

```tex
\node[card, snroot, text width=0.9cm, minimum height=0.8cm, vaudit={class=tk}] (r) at (0,0) {$\langle s\rangle$};
\node[card, snkeep, text width=0.9cm, minimum height=0.8cm, vaudit={class=tk}] (a) at (-1.6,-1.3) {the};
\node[card, snghost, text width=0.9cm, minimum height=0.8cm, vaudit={class=tk}] (b) at (1.6,-1.3) {a};
\node[card, snret, text width=0.9cm, minimum height=0.8cm, vaudit={class=tk}] (c) at (-1.6,-2.6) {cat};
\snkids{r}{snkeep}{a}          % 存活子代：批量连边 + 逐边 vzwire（名 wr-a，竖树默认锚 south→north）
\snkids{r}{snghost}{b}         % 剪枝子代：同父不同态按态分组调用
\snkids{a}{snret}{c}           % 返回路径段
% \snkids[east,west]{父}{样式}{子}   % 横树/斜树换可选首参：父锚，子锚
```

审计埋点处方：

- **节点等大**：树节点文本宽度参差——先 `text width`/`minimum height` 钉死再 `class=`（`class=` 断言宽高全等）。`class=` 量的是渲染盒：多行卡片里 q/g 这类 descender 字符把行盒加深 ~2.7pt、各态边宽差异（`snkeep` 实线 vs `snghost` 虚线的 draw 宽度）同样进盒——`minimum height` 须超最深 descender 行高；只要单维对齐就改用 `eqww=`/`eqhh=` 分维链（宽/高分开断言）替代 `class=` 全等。
- **\snkids**：`\snkids[父锚,子锚]{父}{边样式}{子1,子2,...}` 一条语句产 N 条 `\draw`+N 条 `\vzwire`（wire 名 `w<父>-<子>`、`endpoint=父,子`）；声明折线钉边界锚——竖树默认 `south,north`（父底→子顶），横树/斜树给可选首参（`\snkids[east,west]`、自下而上 `[north,south]`）。裸节点名落中心点，心到心折线必穿端点盒内文字被 readback wire-crosses-text 全报——锚点不是可选项；树是边密集图，批量宏消掉每边 2 行的机械镜像。
- **mean/caption 贴近**：底部含义框与标识行间距 <10pt 时给标识行写 `adjacent=mean`。

陷阱：搜索树方向默认 TB（根在上）；oracle 对纯树/森林输入（环断后每点入度 ≤1）走 tidy-tree 路径——父盒居中首末子中轴、兄弟保序，坐标直接可用；非树图（带环/多父）两后端是分层器不是 tidy，>10 节点时坐标可拿 oracle 打底但父中轴要手工重排——见 `flow.md` oracle 节；`snghost` 边无箭头是刻意的（剪枝不再扩展），要方向感就换 `varr`+ghost 配色手写；`vaudit` 键写语句上不写进样式定义（coverage 是文本扫描，藏进 `\tikzset` 样式里的 `vaudit=` 扫不到）。

## 配方宏清单

| 宏                                            | 展开物                                      | 备注                                           |
| --------------------------------------------- | ------------------------------------------- | ---------------------------------------------- |
| `\seqnum`                                     | `\textbf{n}` 自增                           | `\setcounter{vzseq}{0}` 复位                   |
| `\nskipw{src}{tgt}{x}{名}{tags}`              | `\draw[nskip]` + `\vzwire`                  | 西通道                                         |
| `\nskipwe{src}{tgt}{x}{名}{tags}`             | `\draw[nskipe]` + `\vzwire`                 | 东通道镜像                                     |
| `\selfmsg{出口}{条}{id}{标签}{tags}`          | draw 折回 + `\vzwire{w<id>}` + 节点 `<id>l` | 几何调 `selfw/selfh`，tags 同 `\nskipw` 第五参 |
| `\pic at (P) {vselfmsg={条}{id}{标签}{tags}}` | 同上（pic 形，P=出口）                      | `vaudit=` 挂语句上审计 `<id>l`                 |
| `\snkids[锚对]{父}{样式}{子列表}`             | 逐子 `\draw`+`\vzwire`                      | wire 名 `w<父>-<子>`；锚对默认 `south,north`   |

宏展开出的 `\draw`/`\node` 不被 coverage 静态扫描看见（扫描只看字面命令），其覆盖由宏内建 `\vzwire` 行与可补埋点的命名标签承担——宏语句本身不产生 coverage 警告。pic 形（`vselfmsg`）的 `\pic` 语句会被扫到：语句上带 `vaudit=` 即认下（顺带审计标签节点 `<id>l`）。
