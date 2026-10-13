# 图型 → spec 速查

按信息任务选图型，按表落到 spec 字段；spec 装不下的自由度用 `panels.*.raw` 逃生舱（`f(ax, ctx)`，audit 照跑）。组合图型与进阶配方见「配方节」；`cases/<key>/` 指姊妹仓 `incubator/figure-viz-e2e` 的验收案例目录（每案存 spec/源码 + 渲染图 + NOTES.md 判定记录），`scripts/examples/` 是随 skill 走的入库模板。

| 信息任务     | 图型                | spec 形态                                                                                                               | 要点                                                                                                                                                                                                                                                                                                                                                 |
| ------------ | ------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 比较         | `bar`               | `kind:'bar'`，`by` 自动 dodge 分组柱，`stack:true` 堆叠，`dir:'h'` 横条                                                 | 默认从 0 开始；`baseline` 非零需 `audit_ignore` 声明；`labels` 标柱顶值；stack 正负分向累加、宽度不按组数缩；`bottom`/`connect`/增量标值支撑瀑布图（配方节）；`x` 全数值 → 柱心落真实坐标                                                                                                                                                            |
| 趋势         | `line`              | `kind:'line'`，`by` 扇出多臂；band/pred/ref 用 `of` 挂到父系列                                                          | `marker`/`ls`/`draw`（如 `steps-post`）；`sort_x` 默认开                                                                                                                                                                                                                                                                                             |
| 相关/分布    | `scatter`           | `kind:'scatter'` + `by` 分色分 marker（dict 按键映射）                                                                  | `s` 点大小、`alpha`；白描边默认注入，`edgecolor` 一等字段（token 解析）或 props 同名键可顶替；`y` 收类别列自动槽位化（首见序 + 刻度标签）；`jitter` seeded 位移（配方节）                                                                                                                                                                            |
| 分布形状     | `hist`/`ecdf`/`kde` | `kind:'hist'` `{bins,range,density,cumulative}`；`kind:'ecdf'` 右连续阶梯；`kind:'kde'` `{bw,bw_adjust,grid,clip,fill}` | `by` 分组叠画对比；hist 多组默认 alpha .55 + vink 细描边；`bins` 出 5..200 lint `hist-bin-sanity`；kde 组 <10 点 lint `kde-min-points`                                                                                                                                                                                                               |
| 组间分布     | `box`/`violin`      | `kind:'box'`\|`'violin'`，`y` 数值列 + `by` 每组一只/把（组名落 x 刻度）                                                | violin 任一组 <10 点 lint `violin-min-points`（改 `box`）；violin `inner:'points'` 叠中性抖动散点                                                                                                                                                                                                                                                    |
| 组成         | `donut`             | donut 面板 + `kind:'donut'`，`{x=类别,y=值}` 每行一片                                                                   | 切片 ≤6；`labels` 默认直标，`'legend'` 走图例；不适合精确比较                                                                                                                                                                                                                                                                                        |
| 矩阵关系     | `heat`              | `kind:'heat'` 长表 `{x,y,z}` 或直给 `{matrix,xlabels,ylabels}`                                                          | confusion/correlation/win-rate/sensitivity 全走它；`cmap:'seq'\|'div'`、`vcenter`、`cbar`、`annotate`；`xlabels`/`ylabels` 可作类别顺序钉；`annotate:true` 格值整数 `:g`/其余 `.3g`（`'{v:.2f}'` 模板走 `str.format(v=v)`）；CSV 空洞靠省行（空串 z 撞 non-numeric `SpecError`）；`cmap:'div'` 恒取 `vc±max\|z−vc\|` 对称窗（显式 `vcenter` 同口径） |
| 数值场       | `contour`/`quiver`  | `kind:'contour'` 长表 `{x,y,z}` 或 matrix 直给；`kind:'quiver'` `{x,y,u,v[,m]}` `mode:'arrows'\|'stream'`               | 等值场/向量场；`cmap`/`vcenter`/`cbar` 与 heat 同口径；场 zorder 0.5 垫在数据系列之下（配方节）                                                                                                                                                                                                                                                      |
| 流向/守恒    | `sankey`            | `kind:'sankey'` 长表 `{x=src,y=dst,z=value}` 每行一条流                                                                 | 列布局/守恒校验/缎带几何全在 kind 层；独占 panel，只许 ref/span/note 中性 overlay（配方节）                                                                                                                                                                                                                                                          |
| 图版/栅格    | `image`             | `kind:'image'` `file`/`path`/`rgb` 三源互斥                                                                             | 方法×样本图版（全 image 网格放宽 64 格/边 16）、heat 叠图底图；`badge` 角标、`extent` 摆位（配方节）                                                                                                                                                                                                                                                 |
| 多维 profile | `radar`             | radar 面板 + `dims` 定轴序，line 可加 `fill:<alpha>` 铺面                                                               | 维度 ≤7、系列 ≤3；`rlabel` 调半径标签角度（默认自动落最大角隙）                                                                                                                                                                                                                                                                                      |
| 置信/区间    | `band`              | `kind:'band'` + `of`，`semantics:'iqr'\|'std'\|'range'` 驱动默认 alpha                                                  | 挂父系列继承扇出与色；不写 `of` = 独立填充带（自带 `x`/`lo`/`hi`，校准 gap 这类无父线填充也走 spec）                                                                                                                                                                                                                                                 |
| 参考线/区    | `ref`/`span`        | `dir:'h'\|'v'\|'diag'/'identity'`；`at` 收数字/列名/`{from,key,field}` join                                             | 随父色用 `of`；全局常数线用中性色；`span` 画相位带；`diag` 出斜率 1 对角线（`at`=y 截距、缺省 0 即 y=x）                                                                                                                                                                                                                                             |
| 注释         | `note`              | `{at:[x,y], text, units}`，`units` 支持混合 `[xunit,yunit]`；`at:{x:列,y:列}` 逐行扇出                                  | 只放已解析值；WHERE 怎么算属于 glue                                                                                                                                                                                                                                                                                                                  |

## 配方节：进阶图型与组合配方

每节 = 适用论证 → spec 字段/配方 → 实测样板。字段全量语义以 `spec.md` 为准，这里只记选型与拼法。

### 密度族：kde / jitter 点层 / raincloud / ridgeline

适用：reward/score/loss 等连续量的分布形状对比（seaborn kdeplot 等价物）；raincloud/ridgeline 是「分布轮廓 + 原始点层」的组间排布。

- `kind:'kde'`：`x` 数值列、`by` 叠画；`{bw:'scott'(默认)\|'silverman'\|正数, bw_adjust(默认1), grid:int≥2(默认200)\|升序数组, clip:[lo,hi], fill:alpha}`——`clip` 只截评估支撑、不重归一；常数列/单点组 `SpecError`，任一组 <10 点 lint `kde-min-points`。
- jitter 点层：scatter `jitter` 一等字段——标量 → 对称窗 ±半宽加在 x 上；`{w, at(默认0), axis:'x'\|'y', seed}` → `[at, at+w]` 窗（`{w:0.14, at:0.08}` = 单侧条带，`axis:'y'` 沿 y、类别槽位按槽位单位）；种子逐 (series，组键) 派生，跨运行/跨 spec 编辑可复现。imperative/glue 侧同语义是 `fvagg.jitter(rows, col, by=…, amount=…, seed=…, offset=…, mode=…)` 物化列（标量 `amount` 对称窗、二元组单侧，`offset` 平移基底）；`mode:'uniform'`（默认）seeded 随机流、`mode:'even'` 组内窗内等距摊开（确定性排版、与 seed 无关——数值列按值排序落位、类别列按行序；组内行数变化会整体重排，没有 uniform 的跨过滤稳定性）。glue 物化的数值列进 spec 时直过 `_cat_lookup`（数值不查类别表）——物化目标轴位置按槽位序号写即可。
- raincloud：`violin props:{side:'low', showmedians:false, showextrema:false}` 半云 + `box` 细箱（`widths`）+ scatter jitter 单侧点带，三层组色一致。`side` 的方向映射跟着朝向走：竖版 `low`=左半/`high`=右半，横版（`dir:'h'`）`low`=下半/`high`=上半——横版经典「云上雨下」= `props:{side:'high'}` + 负窗 jitter（`{axis:'y', w:0.3, at:-0.45}` 把点带压到槽位下方）。box 的须/帽/中位线宽画后被统一钉 0.7（`props` 里的 boxplot 线宽键被后处理盖掉）——细箱场景线宽不可控，要非常规线宽走 `raw`。三层都不带 label 时 audit `legend-coverage` 必报「N series reachable by no legend」——`_cat_identifiable` 的类别刻度豁免不含 scatter 的 PathCollection；组名已由类别刻度承担，配方里预写 `panel.audit_ignore:['legend-coverage']`（该规则可按 axes 豁免，不是图级）。
- ridgeline：glue 算 `base`（i·gap）/`top`（base+dens）两列 → 每行交错 `line`+`band` 对、低行后画（画序 = 遮挡序，joyplot 惯例）；或一段 ~20 行 `raw` helper。遮挡语义要求 `band` 给 `alpha:1.0`——默认 ~0.12 的语义 alpha 会让下行轮廓透出来。无图例的行标设计必触发 `legend-coverage`（line+band 双系列按组数翻倍地报），与 raincloud 同法预写 `panel.audit_ignore:['legend-coverage']`。
- 样板：`cases/dist-kde/`、`cases/dist-raincloud/`、`cases/dist-ridgeline/`。

### 场族：contour / quiver

适用：loss landscape、二元函数等值面、灵敏度场（contour）；梯度/流向场、ODE 相图（quiver）——「数值坐标场上的函数」，区别于 heat 的类别格轴。

- `kind:'contour'`：长表 `{x,y,z}` 按数值 (x,y) 透视（类别网格是 heat 语义 → `SpecError`）或 `{matrix,xlabels,ylabels}` 直给——labels 全数值须单调（真实坐标轴），非数值即类别标签按位等距落槽 0..n-1、原串写回刻度；`mode:'fill'(默认)\|'lines'\|'fill+lines'`（色面 + vink 细描线）、`levels:int≥2\|递增数组\|'log'`、`clabel`（`'all'`/步长/显式子集 + `fmt`，须有线层；`manual:[[x,y],…]` 手工钉标注点——与 `levels` 子集互斥 `SpecError`，manual 对所有画出层生效）。
- `kind:'quiver'`：`{x,y,u,v[,m]}`——`mode:'arrows'`（默认）逐行向量（`scale`/`pivot`）、`'stream'` 网格透视 streamplot（`density`/`linewidth`/`arrowsize`；网格轴等距硬校验——非等距 `SpecError` 点名罪魁列与期望步长，CSV `%.6g` 截断是常见病因）；`m` 量级列接管 cmap（与 `color` 互斥，不给 `m` 回退系列色）。
- 两 kind 与 heat 共享 `cmap`/`vcenter`/`cbar` 与 mist 缺格约定；场默认 zorder 0.5 垫底，叠散点/轨迹不遮。clabel 压自身等值面不触发 `text-overlaps-data`（QuadContourSet 同 QuadMesh/AxesImage 属整幅场豁免——遮挡语义由色条承担）。
- 样板：`cases/field-contour/`、`cases/field-quiver/`。

### waterfall 瀑布图（bar 三件套）

适用：逐级增益分解——pass@k、指标增减桥、预算变化这类「基座 + 浮动段」。

`bar` 的 `y` = 带符号增量、`bottom` = run-in 累计列（列名/数字/数组 → 逐行浮动底边，负增量自然下垂；缺值回落 `baseline`，与 `stack` 互斥 `SpecError`）；`connect:true`（或 `{color,ls,lw,zorder,groups,label,props}`）在相邻柱间隙画边到边虚线，level = 前一根柱远端边——`label:'run-in'` 这类图例词经克隆样式的幽灵条目进 panel/figure legend（无图例收时 lint `empty-legend`）；`labels:{mode:'delta'}` 标带符号增量、`'cum'` 标累计远端边（负值柱标值自动推到远端边外侧），`groups` 可按组过滤标值/连线。图例默认给 `where:'below'`——half 槽里 in-axes 图例必撞柱顶标值区；幽灵句柄只产 Line2D（`{kind:'patch'}` 无一等支持），柱色图例要色块也在 below 图例里用文字承担。负增量分色无一等通道（field-resolved 色组内不唯一 `SpecError`）——`raw` 重刷 patch：`for p, r in zip(ax.patches, ctx['data']['w']): p.set_facecolor(ctx['fv'].HUES['vcoral' if r['v']<0 else 'vteal'])`。样板 `cases/flow-waterfall/`。

### sankey 桑基图

适用：token/数据预算分配、样本筛漏斗、rollout fate——守恒拆分与汇合。

`kind:'sankey'` `{x=src,y=dst,z=value}` 每行一条流；`nodes` = dataset 名 | 字面行 `{id,stage,label,order,color}`（缺省按端点首见序推导），`stage` 定列（缺省拓扑 longest-path 分层，d3 justify）；兼有入出流的节点不守恒（rel 1e-6）`SpecError`；`gap`（默认 0.05）/`width`（默认 0.18）调列内隙与列距，`labels`（`'{l} {v}'` 模板）/`heads`（列头）。直给形 `flows:[{source,target,value},…]` 字面流行内嵌、不挂 dataset；`dir:'v'` 把列布局竖过来（stage 成行自上向下、行内流自左向右堆叠，漏斗/流程图纵向阅读序）。缎带宽 ∝ 流量、段按对端列位自上向下排；一条 sankey 独占 panel——同 panel 只许 ref/span/note 中性 overlay；面板坐标是流量单位，刻度归 NullLocator、全 artist fv-neutral，`missing-axis-label` 等数据轴语义不适用。四个边界要知道：无一等 per-ribbon 流量标签——`labels` 只出节点总量（`{l} {v}`），逐段标值要在 `raw` 里复刻内部布局账（段偏移记账不导出）；`heads` 列头各列对齐自身列顶（`mid + col_h/2`），列不等高时头基线不齐；流量行可带额外字段当 color field——`color:{'field':f}` 按行取色即端到端分色；labels 文本不进 datalim——左右节点标签超出自动预留的 ±(0.6+hw) 通道时靠 `xaxis.lim`/`yaxis.lim` 显式加宽。样板 `cases/flow-sankey/`。

### treemap 矩形树图

适用：层级组成——预训练数据配比这类「域 → 子域，面积 ∝ 份额」。无 spec kind，走 imperative：

`scripts/examples/treemap_demo.py` 是全套模板：空间填充交给 PyPI `squarify`（`uv run --with squarify` 即装；包缺席走文件内同算法兜底，输出等价），两级层级由调用方预算坐标（组块留白 → 组头带 → 体块内递归）；标签 fit-degrade——renderer 实测文本框 → 文案/字号逐级降级 → 装不进放弃（小叶不标是 treemap 惯例）；组内 tint ramp 的 hex 经 `fv.register_colors` 注册进 OFFPALETTE 接受集。勘误两条：`hue-budget` 对 Rectangle-patch 树图根本不触发（`fam_of` 只把 HUES/EDGE 主题色 hex 映回色相族——tint ramp 的派生 hex 不在映射表、不计入预算），结构性误报只剩 `missing-axis-label`（无轴图型）与 `low-contrast`（白字压深色 tile）两条需 `audit(ignore=[...])` 豁免；squarify 的 normalize 只保证**单次调用内**面积∝值——两级层级是逐组调用 + 组头定高扣除，小域组的全局占比被压缩（实测 ~29%），「面积∝份额」是组间近似不是严格等比。样板 `cases/flow-treemap/`。

### image plate 图版（方法×样本网格）

适用：vision/生成论文的定性图墙——行=方法、列=样本、每格一张图 + 格内量化角标（PSNR 这类）。

`kind:'image'` `file` 列逐行一张（路径/.npy/数组，`None` → mist 占位格）；`badge:{field,fmt,corner}` 行级角标（半透明黑底白字、fv-neutral 免审计）；全部面板皆 image 时 layout 网格放宽到 64 格/边 16；行标用 col0 `yaxis.label`、列标用 row0 `title`，`layout.tags:false` 关 (a)-(l) 角标；纯 image 面板刻度默认收掉、`grid:'none'`、`frame:'closed'`（spine 当格线），`xaxis`/`yaxis.ticks` 等可钉回。图版同样吃行数默认高——`size:{slot,height}` 显式钉高、`arrange.w_pad/h_pad≈0.12` 收紧格间贴边。样板 `cases/mpl-imageplate/`。

### heat 叠图（注意力 × 输入图）

适用：注意力权重/显著性图叠在输入图上的标准可视化。

`image`（`path`/`rgb` 直给源）+ `extent:[l,r,b,t]` 数据坐标摆位：`extent:(0,n,n,0)` + 默认 `origin:'upper'` 让像素（列 i，行 j）格心正落 `heat` pcolormesh 格心 `(i+0.5,j+0.5)`——naive 默认 extent 会偏半格；image zorder 0 垫底，`heat` 给 `alpha<1` + `props:{edgecolors:'none'}`；垫在透明度 <1 覆盖面下的底图不触发 `occluded-by-heat`。样板 `cases/heat-attn/`。

### forest / coefplot

适用：per-benchmark/intervention 效应量 ± CI 一览、回归系数图。

`scatter` 的 `y` 收类别列 → 首见序槽位 + 自动刻度标签（行标签免手工 pos+tick_labels；首行在顶由 glue 反序喂行或 `yaxis.lim` 按槽位反写表达）；`xerr:{lo,hi}` 双侧不等误差棒是 mpl 偏离量语义——glue 派生 `est−ci_lo`/`ci_hi−est` 两列，`errprops` 调 `capsize`/`elinewidth`/`capthick`；`by` 按显著性分色、`s` 列驱动 marker 面积（weight ∝ n）；`ref dir:'v' at:0` 零效应线；右侧 est(CI) 文本列走 `note at:{x:列,y:列}` 逐行扇出（`text` 里 `{field:fmt}` 行内替换、同位同文去重）。`by` 扇出 + 类别 y 时槽位按（组序，组内行序）分块建表——两组交错的数据行不会交错落位，要交错/固定行序用数值 pos 列 + `ticks`/`tick_labels` 回贴。样板 `cases/diag-forest/`。

### calibration 可靠性图

适用：binned accuracy vs confidence + y=x 对角线 + ECE——sklearn curve 形与 Guo 柱形都通。

glue 侧 `fvagg.calibration_bins(rows, conf, acc, bins, strategy:'width'|'mass', x:'mean'|'center', empty)` 产 bin 行（`{conf,acc,n,se,gap,x,center}`）+ stats（`ece`/`mce`/`nonempty`/`oob`）；图侧：`line`+marker 画 acc~conf + `yerr:'se'`、`band`{of,lo:acc,hi:conf} 涂 curve↔diagonal gap 区、`ref dir:'diag'` 恒等线、`note` 标 ECE/MCE、`hist` 画边际置信分布（grid 上下排 + `sharex:'col'` + `height_ratios`）；`aspect:'equal'` 走方形惯例。gap band 配方有个前提：带上沿 (x, conf) 恰落 y=x 只在 `x:'mean'` 成立（x 列即箱均置信度）——`x:'center'` 时 conf 仍是箱均值、center 是几何中点，(center, conf) 偏离对角线，gap 阴影偏轨；柱形要 gap 可视化改标 `gap` 列文本或接受偏轨近似。Guo 柱形：`bar` 的 `x` 列全数值 → 柱心落真实分箱中心坐标。样板 `cases/diag-calibration/`。

### pareto 前沿

适用：两目标 trade-off（cost↔acc 这类）散点 + 前沿线 + 前沿下可达域。

glue 侧 `fvagg.pareto_front(rows, x, y, senses=('min','max'), by, mark='on_front')` 产布尔标记列（`by` 分组各自求前沿）；图侧：`scatter by:on_front` 双色分前沿/被支配、`line draw:'steps-post'` 在 `where:{on_front:true}` 上画阶梯前沿（min-x 前沿 post 方向正确，max-x 换 `steps-pre`）、`band`{of:前沿，lo:0, hi, `props:{step:'post'}`} 前沿下填充——阶梯填充与阶梯线严格对齐（线性填充会在 riser 处高估可达域）。两个次序陷阱：`of` 只能前向引用**已声明**的系列（spec 序即注册序，指向后面才声明的系列 → `SpecError`）；band 默认 zorder 1 与 scatter 同级、靠画序决胜——半透明填充要明确压在数据墨之上时给 `props:{zorder}`。样板 `cases/diag-pareto/`。

### sig bracket 显著性括号

适用：分组柱/面板间两两检验的括号 + 星号标注（p 由上游统计脚本随聚合行交付）。

spec 侧直通：`kind:'sig'` 数据行驱动——每行 `{a,b,y}` + `'p'`|`'text'` 恰一；`a`/`b` 收类别名（同面板 bar 类目序 / box、violin 组位——解析到槽位中心）、`槽位:组值` 复合挂点（命中同面板竖直 bar 扇出组、按真实 dodge 几何解到组内柱心）或数值 x，`y` = 梁高（数据单位）；`p` → 星号（`p<.001 '***'`/`p<.01 '**'`/`p<.05 '*'`，否则 `'ns'`），`text` 字面量直用（与 `p` 互斥）。`{tick,pad}` 缺省随 y 量程自适应，`color` token（缺省 vink）+ `props`/`textprops` 覆写口；全 artist fv-neutral——不算系列、不进图例，梁贴/超 y 窗沿 lint `sig-outside-axes`。与 bar/box/violin 同面板混叠即得检验标注图；radar/donut 面板不收。模板 `scripts/examples/sigbracket_demo.py` 仍是 imperative 参照（fig-fraction 锚点、跨面板 bracket 这类 spec 未覆盖的几何走 `raw` + `fv.mark_neutral`）。样板 `cases/diag-sig/`。

### paired 三图：lollipop / dumbbell / bump

适用：两时点/两条件的配对对比——stems、连接段、名次迁移三形态。

- **lollipop**：`bar dir:'h' width:0.12` 细茎 + `scatter` 同列端点——横放让条目名住 y 轴；scatter 类别 y 与 bar 槽位共享首见序（两系列消费同表同序才保对齐）。
- **dumbbell**：`scatter by:phase`（`y` 类别列、两端点分色分 marker）+ `line by:item`（每项两行连接段，`y` 用与类别槽位同序的数值 pos 列）+ 右缘 Δ 标签 `note at:{x,y}` 行扇出或 `raw`。注意 `legend-coverage` 的幽灵覆盖判定逐色不逐语义——无标连接段的颜色撞上任一图例句柄色即算被覆盖（vgray 连接段撞同色柄这类异语义同色会巧合豁免），审计结论读「颜色已被图例代言」而非「语义已被图例代言」。
- **bump/slope**：`fvagg.rank` 物化名次列 → `line by:m y:rank` + `yaxis.lim` 反写（rank 1 在顶）；端点标签走 note 行扇出/raw；>4 色相触发 `hue-budget`——highlight 式（1–2 色 + 灰上下文）或显式豁免。
- 样板 `cases/diag-paired/`。

### facet matrix 小倍数矩阵

适用：ggplot `facet_grid` 式展开——行×列 facet 值 × 同一面板模板，不再手写 N 份只差一个 where 的 panel。

`layout.kind:'matrix'`：`template` 面板 × `rows`/`cols` facet 值（显式列表或 `{field:'g'}` 从 `template.from` 派生）；`$row`/`$col` 三形态代入（整串保型、字符串内嵌插值、dict 键），facet `field` 自动注入每条数据绑定 series 的 `where`——strip 文本与过滤条件同源，漂移在构造上不可能；`overrides` 逐格补丁（`null` 空格、命名格、面板补丁、`'r,c'` 键）；strip margin 标签（`{fmt:'{l}', bbox, size}`），`layout.strips:'top'|'right'|'both'(默认)|'none'` 管两侧边缘格的存在性（贴边排版/手动挂 strip 时收）；`sharex:'col'`/`sharey:'row'` 默认开（显式 `'none'` 可关）。样板 `cases/layout-facet/`。

### joint + 边际分布

适用：seaborn `jointplot`——主散点 + 顶/侧边际直方图。

`layout.kind:'spans'` + `map` 跨格（`hx` 顶条、`main`、`hy` 侧条，`map:{hx:[0,0,1,3], main:[1,0,3,3], hy:[1,3,3,4]}`）+ `bind:{hx:{to:main,axis:'x'}, hy:{to:main,axis:'y'}}`——side 绑定轴并入 main 共享组（viewlim 联动）、其刻度标签与轴标签自动隐藏，side 豁免 `missing-axis-label`/`legend-coverage`；y 边际分布用 `dir:'h'`（hist/kde/ecdf 数据沿 y、量沿 x），顶部 x 边际的 box/violin 也走 `dir:'h'`（数据沿 x、组位置沿 y）——`axis:'y'` 侧条上的 box/violin 维持缺省竖置；`width_ratios`/`height_ratios` 收比例。`bind` 各 layout kind 通用——grid 路（`cells` 留空 + `sharex:'col'`/`sharey:'row'`）也能拼同一形态。紧凑贴边两件套：`arrange:{w_pad,h_pad}` 单位是 tight_layout 字号分数 padding，joint 给 ≈0.12；`size` 只给 slot 时高按逻辑网格行数×1.8in 取（joint 3 行 map 默认 ~5.4in 偏高），须显式 `size.height` 钉紧凑高。样板 `cases/layout-joint/`。

### clustermap workaround（聚类热图 + 边际树状图）

适用：seaborn `clustermap`——聚类排序矩阵 + 两侧 dendrogram。

主形用「重排数据序」workaround：glue 侧 scipy `linkage` + `optimal_leaf_ordering` 出叶序 → `heat` matrix 直给预置换矩阵，或长表 + `xlabels`/`ylabels` 顺序钉（列出先排、余按原序）；`annotate` 在大矩阵/窄槽位撞 `collide` 与 `heat-cell-text` lint——clustermap 惯例是不标或给 `slot:'full'`；类别刻度密时用 `tick_stride`/`tick_rotation` 疏化。树状图侧条：side 面板 `raw` 画 linkage 段（`ctx["data"]` 拿 linkage 数据集、`fv.mark_neutral` 上中性身份）——raw 里 `'vgray'` 这类 token 字面量不自动解析，取真色用 `ctx['fv'].HUES[...]`/`NEUTRALS[...]`（extend 名走 `ctx['colors'].token(name, lambda n,m: None)`——lint 是必传位参）；`ctx['data']` 是 `{数据集名:[行dict]}`、CSV 值已转 float，linkage 行直读。经 `bind`（各 layout kind 通用）绑到主热图轴共享 cell 坐标，或 grid+raw panel 手排；`cbar` 会偷主面板宽度使叶尖错位——在 dendro 轴挂 ghost cbar（`fig.colorbar(ScalarMappable(), ax=side)` 后 `cb.ax.remove()`）镜像同一收缩，`set_visible(False)` 不够（隐藏轴仍喂文本审计）。样板 `cases/heat-clustermap/`。

## 选型提醒

- 精确比较别用 donut/radar——角度面积不可比；要比较就用 bar。
- 点/线/柱的不确定性 → `xerr`/`yerr`（标量\|列\|`{lo,hi}` 双侧）误差棒通道，`errprops` 调 `capsize`/`elinewidth` 等造型；缺值按行丢并报 `missing-rows`。
- log 轴上的离散网格值当类别刻度：`ticks + tick_labels + minor:'off'`（categorical-log 惯用法）。
- 同 x 双量纲 → 面板 `y2`；超过双轴 → 该面板走 `raw`。
- 非零基线、inset 这类刻意违规不静默：`panel.audit_ignore` 显式声明。
- 类别轴刻度样式出口：`xaxis`/`yaxis` 的 `tick_rotation`（非 0 自动 `ha:'right'` 锚定）与 `tick_stride`（隔 N 个主刻度只留文本——刻度/网格位置保留），bar/box/violin 的 x、heat 双轴、scatter 类别 y 同口径；旋转文本的碰撞判定按四边形实测（非 AABB）。
- 校准/parity 图要方形 → `panel.aspect:'equal'`；静默遮蔽有 lint 兜底——`note-outside-axes`（纯 data 坐标 note 落点在 axes 外被 clip）、`sig-outside-axes`（sig 括号梁出 y 窗或顶沿装不下星号）、`occluded-by-heat`（系列被同面板不透明覆盖面盖死，与列表序无关只按 zorder 判定）。
- 几何构造行（前沿延拓顶点、辅助锚点这类「为画图造的数据」）别混进主数据表——`by` 扇出会把它们捡成幻影系列/图例项；拆独立 dataset 喂专门的几何系列（front.csv 范式：主表纯观测行、构造行单表单列），主表的 `by`/统计口径才不被污染。
- imperative/raw 侧两件套：`fv.mark_neutral(*artists)` 给手写 overlay 上 `fv-neutral` 身份（豁免 series 计数与 coverage 规则，颜色仍查 OFFPALETTE）；`fv.ramp_cmap('seq'/'div')` 拿与 heat 同约定的语义色带。
