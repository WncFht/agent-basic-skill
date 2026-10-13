# Preset 设计

`fvstyle` 只维护少量可组合 preset，不堆按论文命名的 style。preset 按下面的设计维度组织，每个维度是图的一个独立决策轴。

## 设计维度（选型自检）

画一张图先回答：信息任务（比较/趋势/相关/组成/多维）→ mark 几何（长度/位置/角度）→ 坐标尺度（零基线、对数、归一）→ 视觉编码（位置 > 长度 > 颜色 > 形状 > 透明度——别让颜色承担该由几何承担的信息）→ 标注策略（图乱多半乱在标注，不在颜色）→ 版式输出（单图/多面板、放置尺寸）。图型先服从信息任务，preset 只管风格层。

## 0. 调色板（与 TikZ 侧共享）

`HUES` 九个色相，与 `assets/tikz/vizstyle.tex` 一一对应（`check_palette.py` 机检）：

- 语义组（前六）：`vteal` 主、`vorange` 次、`vcoral` 对比/警示、`vviolet`/`vgreen` 辅助、`vgray` 中性
- 扩展组：`vgold`/`vblue`/`vrose` 为数据图表补到八个可区分色相
- 中性色：`vink` 墨色文字、`vmist` 浅网格/填充、`paper` 纯白画布底；`baseline` 是 `vgray` 的参考线别名

系列取色顺序 `SERIES_ORDER`：teal → orange → coral → violet → green → gold → blue → rose → gray。

## 1. palette preset

- `paper`
    - 多类别、平衡，按 SERIES_ORDER 取色，适合论文图
- `accent`
    - 一个主系列（vteal）高亮，其余退成灰阶
- `mono`
    - 灰度为主（vink → vmist 灰阶），靠 marker/线型区分

## 2. marker preset

- `standard`
    - `o, s, ^, D, P, X, v, *`
- `contrast`
    - `o, ^, D, X, *, s, P, v`

marker 的目标不是装饰，而是当颜色不够时继续区分类别。

## 3. line preset

- `with-reference`
    - 数据线实线，参考线虚线 `--`
- `with-dotted-grid`
    - 数据线实线，背景网格点线 `:`
- `dashed-secondary`
    - 主系列实线，次系列虚线（黑白打印也能分）

## 4. frame preset

- `open`
    - 只保留左/下 spine
- `closed`
    - 四边框完整
- `minimal`
    - 极弱边框，强调留白

## 5. grid preset

- `none`
- `y-only`
- `full-dotted`

## 6. emphasis preset

- `balanced`
    - 各系列地位平等
- `accent-first`
    - 第一个系列是主角
- `highlight-best`
    - 强调最优值或最优系列

## 7. annotation preset

- `legend-only`
- `value-labels`
- `direct-label`

字号下限与文本对比度不是风格自由——audit 的 `text-too-small`/`low-contrast`/`cvd-clash` 机检可读性底线。

## 当前建议

先不要让 preset 过多。默认只维护三套组合（`THEMES`）：

- `paper`
    - `palette=paper`、`markers=standard`、`frame=closed`、`grid=y-only`、`emphasis=balanced`
- `accent`
    - `palette=accent`、`markers=standard`、`frame=closed`、`grid=y-only`、`emphasis=accent-first`
- `mono`
    - `palette=mono`、`markers=contrast`、`frame=open`、`grid=full-dotted`、`emphasis=highlight-best`
