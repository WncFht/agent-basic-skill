---
name: plot-skill
description: |
    用中文生成和维护可复用的 matplotlib 图表能力，围绕 bar、donut、line、radar、scatter 五类图，
    通过少量 preset 统一配色、marker、线型、边框、网格和强调策略。
    当用户说“画个柱状图/折线图/散点图/雷达图/环形图”“做一个 preset”“统一图表风格”
    “按这个风格画数据”“整理成可维护的画图脚本”时使用。
---

# Plot Skill

这个 skill 不追求复现一堆按论文命名的单次脚本，而是维护一套长期可复用的图表系统。

## 支持范围

- 图类型：`bar`、`donut`、`line`、`radar`、`scatter`
- 输出方式：Python + `matplotlib`
- 目标：少量 preset、稳定复用、方便后续继续调风格

## 工作流

1. 先判断用户的任务目标：
    - `比较` → 优先 `bar`
    - `趋势` → 优先 `line`
    - `相关性/聚类` → 优先 `scatter`
    - `组成` → 优先 `donut`
    - `多维 profile` → 优先 `radar`
2. 再选 preset：
    - `balanced`：各系列地位相近
    - `accent`：一个主系列突出，其余退后
    - `paper`：偏论文图，轴和网格语义更强
3. 需要详细设计维度时，读取 `references/design-dimensions.md`
4. 需要具体 preset 含义时，读取 `references/presets.md`
5. 需要具体图类型的注意事项时，读取 `references/chart-families.md`
6. 直接从 `scripts/` 里的对应脚本开始，而不是重新手写整张图

## 目录说明

- `references/design-dimensions.md`
    - 解释画一张图要考虑哪些层面
- `references/presets.md`
    - 定义配色、marker、线型、边框、网格、强调策略
- `references/chart-families.md`
    - 解释五类图各自适合什么、不适合什么
- `scripts/style_presets.py`
    - 所有脚本共享的样式 token 和 helper
- `scripts/*.py`
    - 五类图的最小脚本模板

## 使用原则

- 优先复用 `scripts/style_presets.py`，不要在每个图里重新写颜色、marker、grid、spine 规则
- 单次图的个性化差异，尽量通过 preset 参数表达，不要直接散落成硬编码
- 如果用户要“像某篇论文”，先把它翻译成：
    - `palette`
    - `frame`
    - `grid`
    - `emphasis`
    - `marker / linestyle`
    - `annotation`
      再决定是否需要新增 preset

## 何时新增 preset

只有同时满足下面两个条件才新增：

- 至少会复用两次
- 不是只改一个颜色或一个字号，而是涉及完整视觉策略变化

## 当前默认 preset

- `tableau-paper`
- `tableau-accent`
- `mono-paper`

优先先在这三套里调整，不要一开始就扩成十几套。
