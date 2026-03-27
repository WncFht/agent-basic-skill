# Mode Routing

`recommended_mode` 是 runtime 给模型的建议，不是硬性锁定。模型可以覆写，但覆写前应先看 overview、transcript 和封面图。

它主要回答“视觉密度和抽帧强度该怎么判断”，不直接回答“正文需要什么支持材料”。

## 推荐模式

| Mode | 典型特征 | 默认策略 |
| --- | --- | --- |
| `talking-head` | 人像为主，视觉信息稀疏 | 少量截图，更多依赖 transcript 与结构化重绘 |
| `visual-light` | 有少量关键幻灯片或产品界面 | 先 overview，再围绕关键时间窗做定向抽帧 |
| `static-outline` | 大纲式 PPT、文字页较多 | 优先捕获完整大纲页与关键过渡页，避免重复截图 |
| `board-heavy` | 白板、手写推导、渐进构建 | 高召回抽帧，重点保留最终完整状态和中间关键步骤 |

## 建议流程

1. 先接受 runtime 的 `recommended_mode` 作为初始假设。
2. 查看 `overview_frames/` 或 montage。
3. 再决定是否加大或减小抽帧强度。
4. 额外判断 support profile：当前正文更偏 `evidence-led`、`explanation-led` 还是 `demo-led`。

## Support Profile

这不是新的 runtime mode，而是写作时的第二判断轴。

- `evidence-led`：重点在证据核验，优先找外部原件、视频中的原始页或高可信截图
- `explanation-led`：重点在解释结构关系，优先考虑重绘、pair 或结构化示意图
- `demo-led`：重点在步骤、界面或状态变化，优先保留视频帧及其高质量 crop

实践上可以这样用：

- 先用 `recommended_mode` 判断视觉密度
- 再用 support profile 判断正文更需要哪类图和哪类来源

## 什么时候应该覆写模式

- overview 显示视觉密度与 transcript 推断明显不一致
- 平台章节极粗，但视频里有高价值白板或 UI 演示
- talking-head 视频里插入了少量但关键的图表页

## 不该做的事

- 未看 overview 就机械地按固定频率抽帧
- 因为想省时间，跳过 `board-heavy` 视频的高召回窗口检查
- 把字幕密度误当成视觉密度
- 把视觉 mode 当成图像来源或正文支持方式的唯一判断
