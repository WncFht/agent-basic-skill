# Three-Axis Mode Routing

`recommended_mode` 仍然是 runtime 给模型的弱 prior，但 v2 不再把它当成最终 mode。真正决定写作与取图策略的，是下面这三个轴：

1. `carrier_family`：主要视觉载体是什么
2. `support_profile`：正文主要需要哪类支持材料
3. `recall_budget`：候选帧和候选图的召回强度该开多大

默认流程是：

1. 先读取 `preflight.json.recommended_mode`
2. 再看 `overview_frames/`、montage 和 transcript
3. 最终显式写出三轴结论，而不是只继承 runtime mode 名字

## Axis 1: Carrier Family

这一轴回答“视频里的主要信息，究竟是靠什么载体承载的”。

| Carrier family | 中文解释 | 默认图像策略 |
| --- | --- | --- |
| `document-led` | 正文主要围绕文档页、财报页、论文页或网页原件展开 | 优先证据页、局部 crop、外部原件 |
| `slide-lecture` | 主要信息承载在 PPT 或课件页上 | 优先完整页、关键过渡页和术语结构 |
| `ui-demo` | 软件界面、终端、网页操作步骤是主体 | 围绕状态变化和步骤顺序取图，不均匀抽帧 |
| `spatial-tactics` | 空间路线、站位、描点、投掷结果本身就是核心内容 | 允许更多 lineup/result pair 和高召回窗口 |
| `face-centric` | 主要是人物口播、访谈或镜头叙事 | 图像预算低，正文更依赖论证链和提炼 |
| `realworld-process` | 烹饪、器具操作、现实世界手把手流程为主 | 关键图跟动作节点和状态变化走 |
| `mixed-workflow` | PPT、界面、命令行、网页和口播混合出现 | 先拆段，再判断每段的主要载体 |
| `mixed-essay` | 口播叙事为主，但中间穿插结构图、投影片或少量关键界面 | 图像更多承担解释和导向 |
| `math-board` | 数学推导、板书、块矩阵或公式结构是重点 | 优先重绘或公式化重建，不硬保留模糊截图 |
| `static-outline` | 大纲页或静态结构页长期驻留 | 重点是完整结构和层次，而不是高频截图 |

## Axis 2: Support Profile

这一轴回答“正文主要需要什么类型的支持材料”，它不等于画面类型。

| Support profile | 中文解释 | 默认偏好 |
| --- | --- | --- |
| `evidence-led` | 正文核心是“让读者直接看到证据” | 外部原件页、原视频证据页、高可信截图 |
| `explanation-led` | 正文核心是“把结构讲清楚” | 重绘、重组、pair、结构化示意图 |
| `narrative-led` | 正文核心是论证链、人物判断和叙事弧线 | 图像承担导向，不追求高密度截图 |
| `demo-led` | 正文核心是步骤、状态切换和操作顺序 | before/after、step-by-step、状态对照 |
| `anchor-dense` | 一个动作、一个点位、一个描点就可能构成独立视觉义务 | 图会自然比普通章节更多，优先 pair |

## Axis 3: Recall Budget

这一轴回答“候选帧搜索该开到多大”。它是操作强度，不是载体类型。

| Recall budget | 中文解释 | 默认行为 |
| --- | --- | --- |
| `low` | 低召回 | 只围绕极少数关键时间窗做定向检查 |
| `medium` | 中召回 | overview 后再围绕重点段做局部扩搜 |
| `high` | 高召回 | 对关键段做高密度候选抽帧，再下采样 |
| `very-high` | 很高召回 | 允许同一节长出多个 pair、crop pair 或 derived figure |

## 推荐决策流程

1. 先接受 `recommended_mode` 作为初始假设。
2. 看 `overview_frames/` 或 montage，判断真正的视觉载体。
3. 看 transcript，判断正文更需要证据、解释、叙事还是 demo 支撑。
4. 最后根据 case 的视觉义务密度，决定 recall budget。

## 典型组合

- `document-led + evidence-led + medium/high`
  适合财报、论文解读、网页证据链分析。
- `ui-demo + demo-led + high`
  适合软件界面、终端、网页教学。
- `spatial-tactics + anchor-dense + very-high`
  适合点位课、路线课、投掷教学。
- `face-centric + narrative-led + low`
  适合长访谈、观点输出、镜头叙事。
- `math-board + explanation-led + high`
  适合数学推导、公式密集白板。

## 什么时候应该覆写 runtime mode

- overview 显示视觉密度与 transcript 推断明显不一致
- 平台章节极粗，但视频里有高价值白板、UI demo 或 document evidence
- `board-heavy` 桶里其实是终端教学、评论口播或财报页，而不是高锚点画面

## 不该做的事

- 未看 overview 就机械地按固定频率抽帧
- 只因为 runtime 给了 `board-heavy`，就默认每章都多配截图
- 把字幕密度误当成视觉密度
- 把 carrier family 当成 support profile，或把 support profile 当成 recall budget
- 没有把三轴结论落进 `work/section_alignment.json` 就直接开写
