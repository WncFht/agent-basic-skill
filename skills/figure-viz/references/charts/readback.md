# 渲染后回读（rb-*）与 print-fit

`fv.audit` 里带 `rb-` 前缀的三条规则与 `print-fit` 是**渲染后回读层**：不读 spec、不读声明坐标，只在 `fig.canvas.draw()` 之后拿 renderer 实测的 device-px 几何说话。全部 warn 级——它们是「声明意图与渲染现实的差集报告」，不是新的硬约束。

动机来自两次真实事故：mpl 侧 `audit` 量出图宽 258px < 270px 栏宽判了干净，产物嵌进 tex 却被裁（pgf 的字体度量比声明宽）；twin-axes 面板的图例把 ax2 系列**静默丢弃**，声明坐标系里一切正常，只有渲染产物里那行图例文字真的不存在。声明坐标 ≠ 渲染坐标——这一层就是为了接住从指缝漏下去的那部分。

## 三条规则

| 规则              | 判定                                                                                              | 与既有规则的关系                                        |
| ----------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `rb-text-outside` | 文本包围盒任一边超出 figure 画布 >1px；消息给越界量 + 占图宽百分比（dpi 无关）                    | `text-outside-figure`（error）的回读版，同一判定带读数  |
| `rb-text-collide` | 两文本包围盒真相交（旋转文本按四边形实测，ix>0 且 iy>0），相交面积 > 较小框 20%                   | `collide`（error，任何相交即报）的宽量版                |
| `rb-label-diff`   | spec 声明的标识文本 vs 渲染出的文本字符串做差集：声明了没渲染 = `missing`，渲染了没声明 = `extra` | `legend-coverage` 管不到的「图上有 label 但没被图例收」 |

`rb-text-collide` 的 20% 阈值是有意与 `collide` 拉开：横排图例条目、相邻刻度标签天然贴在一起，**边贴边不算交**（`ix<=0 or iy<=0` 直接跳过），真压字才有面积占比。两条规则都报时读 `collide` 修几何，`rb-text-collide` 的百分比告诉你压了多少。文本压数据墨水是另一条轴——声明空间规则 `text-overlaps-data`（error）管文本 vs 线/点/柱，rb 层只查文本 vs 文本，两者互补不重叠。

`rb-label-diff` 的比较口径在 `_norm_label`：折叠空白、去 `$` 定界与数学间距命令（`\,` `\;` `\:` `\!` `\`）、去 `(a)` 自动面板 tag、unicode minus 归一——声明串与渲染串同走一遍再比。分层查：

- **missing**（声明 → 渲染缺席）：查找域是全部渲染文本——图例条目与标题、axes 标题、轴标签、`ax.texts`、`fig.texts`（刻度标签不算——声明的标识不会躲进刻度里）。典型命中：`legend.entries` 过滤掉的系列 label（m07 同款静默丢弃）、模板展开前写死的旧系列名、声明了 label 却没有任何图例收集的系列——按轴配色、刻意无图例的设计会踩到这条；warn 级，要么删 label、要么把这条 warn 当预期收下。
- **extra**（渲染 → 声明缺席）：只查身份层——图例条目/图例标题 + axes 标题。轴标签、`ax.texts`、`fig.texts` 允许来自 `panels.*.raw` 逃生舱与数据标注，不算未声明。系列 label 会被图上 artist 的已解析 label 自动并入 declared（模板 `"{v}"` 的展开结果直接覆盖），所以 extra 实际只能由残留的标题/手工图例文字触发——这正是要抓的：spec 里删了、raw hook 又画上的旧文案。

`declared` 集合由渲染 CLI 自动喂：`fvspec.declared_texts(spec)` 走 spec 结构收集 panel title、xaxis/yaxis/y2 label、legend title 与 entry label、系列字面 label、note.text、donut 切片名（labels≠False 时）、`{group}` 条目的 by 组键、`{series}` 条目兜底显示的系列 id、meta.caption。imperative 路径没有 spec——`audit(fig)` 不传 `declared` 时整条规则跳过；手工传 `declared={...}` 也能开。

## print-fit：按目标槽位算降采样后的有效字号

图交付后不是以 figsize 展示，是按版宽槽位（`SIZE_SLOTS`：full=5.5 / half=2.70 / third=1.77 in）缩印。print-fit 的判定：

1. 交付物理宽 = `fig.get_tightbbox(renderer)`（已是英寸）——tight 裁剪能裁到的实际产物宽，图例外挂的 legend/文本会让产物更宽、在槽位里被缩得更小，比 canvas 宽更保守。
2. 目标槽：`audit(print_slot=)` 显式给（槽位名或英寸数），spec 侧由 `size`/`size_slots` 自动解析；都没给时按「图宽一旦超过 full 槽就注定按 full 缩印」自动取 5.5in——更小的槽属于显式意图，不猜。
3. `w_in > target * 1.02` 才查（2% 容差防边界抖动）；`scale = target / w_in`，任一文本 `size_pt * scale < 5.5pt` 即报一条汇总：多少个文本、缩到哪个槽、最差的那个缩到几 pt。

5.5pt 是有效字号下限：mpl 图嵌进论文后小于这个数在印刷/投影上不可读——multipanel.md 的「缩 1x4 横排不是把字号调小，是减少每面板元素」这条纪律的机器版。print-fit 与 `text-too-small` 是同一纪律的两端：一个管交付缩印后，一个管画的时候。

已知误译链：figure 级文本的越界墨迹同样进 tightbbox——超宽 `meta.caption`（居中 fig.text、无 spec-time lint）把产物宽顶大后，print-fit 会把「图超槽→全文字缩印 <5.5pt」成片报出，根因是 caption 不是面板。遇到 print-fit 集群先查最宽的 fig.text/legend 外挂（`rb-text-outside`/`fv.overlay` 定位），修 caption 文案比逐 artist 放大字号对症。

## 已知误报与抑制

- **旋转刻度标签**：已按旋转四边形实测（不再是轴对齐盒近似），30–45° 密集刻度报的「相交」是四边形真相交——旋转标签互压在该密度下客观存在，调疏刻度或旋转角，别当误报豁免。确实刻意叠放的组合体才用 `ignore`/`scoped_ignore`。
- **数学文本归一化**：`_norm_label` 去 `$` 与间距命令是为了让 `label="$x_i$"` 匹配渲染出的 `x_i`，但 TeX 命令内嵌文本（`\mathrm{relu}`）与渲染字形仍可能差一步——`\mathrm` 剥不掉时声明侧写纯文本形式即可对齐。
- **重叠声明过的组合体**：TikZ 侧有 `overlap=`/`adjacent=` 声明通道，mpl 侧目前没有对应的文本级声明——刻意的双层标注（白衬底文字盖参考线标签这类）用 `scoped_ignore`/`ignore` 豁免。
- **回读域的边界**：rb-_的文本池是 `_iter_texts`——刻度标签、轴标签、标题、`ax.texts`、`fig.texts`、图例文本都在域内；`ax.artists`/`fig.artists` 上的 AnchoredOffsetbox 容器子树（AnchoredText、TextArea/HPacker、Table 单元格）经 `_container_texts` 递归收编同域——不可见子树整支跳过、legend 容器走专用通道不重复计、id 去重，raw 里 `add_artist` 注入的 offsetbox 文本对 rb-_ 与 collide/offpalette/missing-glyph 全链可见。残余缺口只在判定位：`rb-text-outside`/`text-outside-figure` 只查越界不查贴边——画布角内侧的 `fig.text` 逃逸；锚点轴内、墨迹越 spine >2pt 的文本归 `text-spills-axes`（warn，`frameon=False`/`axison=False`/四 spine 全隐的轴豁免），锚点在轴外的骑缝仍是盲区；`text-overlaps-data` 的「data」只算系列墨水（线/集合/柱矩形/img）——spine、刻度线、图例框都不是墨水（文 - 文域里 spine 也不是文本）。装饰性贴边/骑缝文本靠 `fv.overlay` 目检兜底。

`--no-readback`（render_mpl）只豁免 `rb-*` 三条：lint、其余 audit 规则、`print-fit` 照跑。任何 rb 规则都能进 `ignore`/`scoped_ignore`/`audit_ignore` 体系——它们就是 RENDER_RULES 里的普通 warn 级规则。

## overlay：回读几何的可视化

`fv.overlay(fig, path)`（或 `render_mpl.py --overlay` → `<stem>.overlay.png`）把回读层实测的 window-extent 画成细框叠加到图上：画布 `vink`、axes `vteal`、legend `vgold`、每个文本 `vcoral`。坐标走 `IdentityTransform`（device px）——与 rb-* 同一份测量，声明坐标不参与。按 tight 外扩落盘，画布外的越界框也看得见。

用法定位：rb-* 报出来后**看图定位**用，不是交付物。「`rb-text-collide 'lr' x 'wd'`」报了两个短文本时，overlay 上哪两个珊瑚框相交一眼可见；`rb-text-outside` 报的越界文本在画布框（ink 框）外露出多少也直接可读。审计零错误时 overlay 图依然能当目检辅助——机器只查相交与越界，美感留给自己。
