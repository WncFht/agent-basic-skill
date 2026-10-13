# 多面板图

多面板图论证的是「同一个实验的几个切面」：一组面板共享数据、共享视觉语言、共享图例，各面板讲一个分论点。一个面板论证一件事；需要两套视觉语言讲两件事时，拆成两张图。

模板：`scripts/examples/multipanel_demo.py`（1x4 实验图全流程）；spec 侧语法见 `spec.md`。

## 面板数与布局选型

| 布局     | 适用                                                                | spec                                                            | mpl                                |
| -------- | ------------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------- |
| 均匀网格 | 主力：1xN 横排（实验图的支配形态）或 2x2                            | `layout.kind:'grid'`                                            | `plt.subplots(1, n)`               |
| 矩阵     | 指标×参数的笛卡尔展开：每行一个指标、每列一个参数值，单元格同一模板 | `layout.kind:'matrix'`（`template` + `$row`/`$col` facet 展开） | `subplots(R, C, sharex, sharey)`   |
| 跨格     | 非对称排布、留 legend 格（如 2x6 gridspec 里 `gs[1,0]` 作 legend）  | `layout.kind:'spans'`（`map` 跨格矩形 + `bind` 边际轴配对）     | `fig.add_gridspec` + `add_subplot` |

三种布局 spec 全实装：matrix 的 `template`/`rows`/`cols` facet 展开、strip margin（`layout.strips:'top'|'right'|'both'|'none'` 收位置）、spans 的 `map` 矩形（命名 axis-off 格不占 8 面板名额——8 面板 + 图例格塞得下）与 `bind` 边际轴配对见 `spec.md`「layout — matrix / spans」两节；不规则到 spec 装不下的混排仍走 imperative 或 `panels.*.raw` 逃生舱。

宽度永远来自版宽槽位：full=5.5in 一行排 3–4 个面板、half=2.70in 一个面板；高度 ≈1.8in/网格行。1x4 横排是 full 槽的密度上限——每轴只剩 ~1.3in，密集刻度要裁标签（见下）。

## 跨面板一致性

- **一臂一色**：实体（arm/方法/level）在所有面板里同一色。工程上 = 一张注册表（`ARM_COLORS`/spec `colors.registries`）在每个面板查同一张表，不是每个面板各调一次 `series_colors`——面板间语义同一性是全局约束，不是逐面板碰巧同序。
- **中性色给真正的共享量**：与 arm 无关的曲线（anchor coverage U(K)、总 baseline）用 `vink`/`vgray`，反而更醒目地区分「按臂分」与「全局」。
- **参考线随父色**：per-level 参考线（`axhline(exact[lev])` 按 level 逐条取色）取父系列色；全局参考（`axhline(1.0)` 这类常数线）用中性色。
- **一样式一语义**：实线=实测、虚线=预测/surrogate、点线=exact 参考、阴影带=IQR——在所有面板保持同一映射，图例只需讲一次（spec `pred`/`band`/`ref` 的 `of` 继承就是为这个）。
- **同尺度才共享轴**：`sharex`/`sharey` 只用于同量纲面板（matrix 行/列）。量纲不同的 1xN 横排不共享轴、各自标 ylabel——强扭共享比重复标注更糟。共享轴时内侧刻度标签隐藏（mpl `labelouter`），标签只住边缘——spec 侧渲染器按 share 组自动做这件事（非底行藏 x 刻度标签、非左列藏 y 刻度标签），手写 imperative 用 `ax.label_outer()`。共享轴的物理对齐另有 audit 兜底：`shared-axis-misaligned`（warn）把组成员按共享方向的中心聚成行/列带（4px 容差），只在同带成员间比边缘 device-px 错位 >2px——典型触发是 `aspect:'equal'` 与共享轴共存（等比约束把某面板内缩、轴名共享实错位），colorbar/secondary 轴不计入比较组，跨行 sharey/跨列 sharex 的天然错位不报。

## 标注去重

- **tag**：`(a)`,`(b)`,… 按 layout 序自动编号（spec `layout.tags` 默认开），逐行引用面板靠 tag 不靠位置描述。
- **每轴标签归边**：ylabel 只写最左列、xlabel 只写最下行、列标题只写最上行——spec 侧 `layout.rows/cols` 边默认（ylabel 归左缘、xlabel 归底缘，与面板已有同文 label 幂等）与 matrix 的 strip margin 已实装承担这件事；手写 imperative 仍要逐面板遵守同一规则，不要在 4 个面板写 4 遍 "median KL"。
- **一个图例**：系列在多面板重复时，legend 全图共享一份——`fig.legend` 放底部并给 `tight_layout(rect=)` 让位，或 spans 里留 axis-off legend 格。面板级 legend 只留给「本面板自读」需要的（每面板 arm 组合不同时）；面板自带 legend 的就不再进图级 auto-collection，混合计划不重复计数。
- **legend 覆盖全部颜色**：图上出现的每个色都得能被 legend 解释——没画出来的样式角色用幽灵句柄（`Line2D`/`Patch` 手工构造，spec `entries[].handle`），标注在图上的单点也要给 ghost 或就地文字说明（audit `legend-coverage` 会查）。单系列面板不走成对覆盖——义务退化为「这条系列可识别」：label 进了某 legend、非空 ylabel、就地文字、颜色被幽灵覆盖，四取一即合法，全黑才报（死 label——有 label 却无 legend 收它——与匿名系列分报）。
- **刻度密度随面板宽度收缩**：1x4 横排里 log-x 离散网格别全标——刻度全打、标签隔位留（categorical-log 的 `minor:'off'` + 子集标签），宁可少标不可压字（audit `collide`）。
- **重复元素照画**：band、参考线这类系列内元素在每个相关面板重复出现是对的——去重的是「说明」（label/legend/title），不是「数据」。
- **figure 坐标 note 不进 tight bbox**：`units` 含 `'figure'` 的 note 自动 `in_layout:false`——画布级标注语义在版心之外，不计入宿主 axes 的 tight bbox（旧行为让 tight_layout 把面板挤向画布边缘）；跨面板的画布级标注走它，`props:{in_layout:true}` 可显式钉回。

## 空面板与稀疏

网格允许空格：`layout.cells` 里的 `null` 是合法空 axes（还可作 `legend.where:'cell'` 的目标格），不要硬凑内容填满——稀疏本身就是信息（presence-conditional：参数组合不存在就留空）；matrix 展开时 facet 值没有匹配数据的格子同语义留空（数据驱动空格，不是手写 `null`）。

## 密度纪律

- 字号按放置尺寸定（`paper_rc` base 7.6 / spec `rc.base`），图不再缩放；缩 1x4 横排不是把字号调小，是减少每面板元素——字号与对比度下限由 audit `text-too-small`/`low-contrast` 机检，压字换密度会被机器拦下。整图要换 base 字号别逐 artist 写 `fontsize=`——`fv.apply_rc(theme, fontsize=7.2)` 一处改 `font.size`，tick/label 的相对名（'small'/'medium'）全部随动；逐 artist 硬编码会把字号体系打散，audit 只能逐个拦越界，管不了比例失调。
- 单面板系列数 ≤4–5；整张图活跃色相族 ≤4（audit `hue-budget`）。
- `savefig` 前必跑 `fv.audit(fig)`：多面板的典型犯规是 `facet-ylim-mismatch`（同行不同尺度）、`label-color-inconsistent`（同名不同色）、`duplicate-legend-label`、`tag-sequence`——全是跨面板一致性问题，机器查比自己看靠谱。

## zoom inset

放大局部用 `mpl_toolkits.axes_grid1.inset_locator`，三个坑都有标准解法：

```python
axins = inset_axes(ax, width="38%", height="38%", loc="upper right", borderpad=1.0)
# …在 axins 上重画同系列数据，再 set_xlim/set_ylim 到放大窗口…
axins.tick_params(labelbottom=False, labelleft=False)  # 藏刻度标签
rect, connectors = ax.indicate_inset_zoom(axins, edgecolor="gray")
rect.set(alpha=0.15, facecolor="gray")  # 宿主放大区半透明示位
```

- **藏刻度用 `tick_params(label…=False)`，不用 `set_xticks([])`**——后者清掉的是刻度本身，log 轴的 minor grid、后续手工加的刻度也一起消失。
- **宿主矩形要半透明**：`indicate_inset_zoom` 默认只画边框，填色版务必 `alpha` 压低，实心块会盖住被放大的数据。
- **连角要挑**：自动连的两条 connector 可能压数据或交叉；换 `mark_inset(ax, axins, loc1=…, loc2=…)`（角位 1–4）手工选不穿数据的两个角，或对返回值里的 `connectors[i].set_visible(False)` 逐条取舍。**渲染后必须显式校验**——自动配对选到哪对角不可预判（e2e m03 案实锤选中了穿数据色带的底缘对），逐条 connector 目检走线；若源框与 inset 的几何关系注定让 connector 穿数据（如 g06 案左下源框→右上 inset 必两穿下行曲线），别硬凑角位——换 `axvspan` x 窗条带或半透源框标记源区，放大语义交给 caption 承载。
- inset 在 `ax.child_axes` 里，audit 的 `_all_axes` 会查到；刻意的截断/重叠别硬扛规则，`audit(scoped_ignore=[(rule, axins)])` 显式豁免——检查与豁免都沿 `child_axes` 递归后代（inset 里再开 inset 同样查得到、豁得到），spec 侧 `panel.audit_ignore` 同口径。反向盲区：`indicate_inset_zoom` 返回的 InsetIndicator 挂在 `ax.artists`（mpl≥3.10），series_map/OFFPALETTE 审计完全看不见——矩形与 connector 的配色须手动遵守调色板。
