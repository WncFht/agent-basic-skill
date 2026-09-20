# Preset 设计

当前 skill 不维护一堆按论文命名的 style，而只维护少量可组合 preset。

## 1. palette preset

- `tableau-paper`
  - 多类别、平衡、适合论文图
- `tableau-accent`
  - 一个主系列高亮，其余退成灰或低饱和
- `mono-paper`
  - 灰度为主，只保留一个强调色

## 2. marker preset

- `standard`
  - `o, s, ^, D, P`
- `paper-contrast`
  - `o, ^, D, X, *`

marker 的目标不是装饰，而是当颜色不够时继续区分类别。

## 3. line preset

- `solid-primary`
  - 主系列实线，次系列实线
- `with-reference`
  - 数据线实线，参考线虚线 `--`
- `with-dotted-grid`
  - 数据线实线，背景网格点线 `:`

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

## 当前建议

先不要让 preset 过多。默认只维护三套组合：

- `tableau-paper`
  - `palette=tableau-paper`
  - `markers=standard`
  - `frame=closed`
  - `grid=y-only`
  - `emphasis=balanced`
- `tableau-accent`
  - `palette=tableau-accent`
  - `markers=standard`
  - `frame=closed`
  - `grid=y-only`
  - `emphasis=accent-first`
- `mono-paper`
  - `palette=mono-paper`
  - `markers=paper-contrast`
  - `frame=open`
  - `grid=full-dotted`
  - `emphasis=highlight-best`
