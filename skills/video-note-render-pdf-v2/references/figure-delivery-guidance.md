# Figure Delivery Guidance v2

这份文档承接 v2 最关键的图片规则：图片不再只在章节级别做“写作驱动”判断，而是要先把独立的视觉义务显式列出来。

## 先建 Visual Obligation Ledger

对下面三类段落，默认先建 `work/visual_obligation_ledger.json`，再决定最终图数：

- `demo-led`
- `anchor-dense`
- `document-led + evidence-led`

每一行至少应包含：

- `section_id`
- `claim_or_action`
- `intent`
- `preferred_source`
- `candidate_windows_or_pages`
- `delivery_form`
- `status`
- `waiver_reason`

推荐字段解释：

- `intent`：`evidence / explanation / demo-pair / anchor-pair / orientation`
- `preferred_source`：`video-frame / external-original / derived-figure`
- `delivery_form`：`single / pair / crop-pair / derived`
- `status`：`planned / kept / waived / replaced`

默认 contract：

- 进入最终 prose 的视觉义务，必须落成三选一：保留 figure、改成 derived figure、写清 waiver 原因
- 不允许让“有图总比没图好”的占位图绕过 ledger

## Figure Intent First

不要先问“这里能截什么图”，而要先问“这里为什么需要图”。

常见 intent：

- `evidence`：需要让读者直接看到原始载体，例如财报页、论文图、白板页、产品 UI
- `explanation`：原始画面不够适合阅读，需要重绘、重组或 pair 来讲清结构
- `demo-pair`：需要显示操作前后、状态切换或步骤衔接
- `anchor-pair`：需要把站位/描点与结果画面成对保留
- `orientation`：帮助读者知道视频讲到哪个阶段或界面

默认顺序：

1. 先写出该段核心论点或动作
2. 再判断是否真的需要图
3. 需要图时，先判断 intent，再判断来源
4. 如果图的必要性说不清，优先删图而不是保留占位图

## 高召回选帧规则

- 先高召回，再下采样；不要一猜一个时间戳就只截一张图。
- 优先使用字幕时间窗定位候选画面；若字幕不可用，则退回 overview 与视觉峰值窗口。
- 能做 montage / contact sheet 时，优先先看候选集合，再挑最终图。
- 如果首张截图处在动画、PPT reveal 或白板构建中间态，继续向前后搜索，直到找到最完整可读状态。
- 若多个相邻候选只在 reveal 完整度上有差异，优先选择信息更完整的后者。
- 对于密集视觉段落，可以先过采样，再丢弃低信息候选；不要过早收窄候选集。

## Recall Budget 怎么影响取图

- `low`
  只围绕极少数核心时间窗做定向抽帧，通常不做 pair 扩展。
- `medium`
  允许在关键段附近做局部扩搜，优先 single figure 或少量 pair。
- `high`
  允许为一个关键段保留多组候选，再根据正文选择最清楚的版本。
- `very-high`
  允许同一节自然长出多个 pair、crop pair 或 derived figure，不要为了“图数好看”强行压扁。

## 来源选择优先级

- 若外部原件明显更清楚、更权威，例如财报 PDF、论文图、README 页面，应优先保留外部原件。
- 若原视频画面更能体现步骤或状态变化，应优先保留视频帧。
- 若截图始终不够清晰，优先用 TikZ / PGFPlots / 外部图复画，而不是塞进低信息截图。
- 若单张图无法同时保留上下文和细节，应优先考虑 pair，而不是把读者留给一张模糊小图。

## 画面质量处理

- 画面过松时，允许裁剪、局部放大或拆成多张图。
- 同一节可以有多张关键图，不必为了“看起来简洁”强行压成一张低可读大图。
- 若视觉信息稀疏，不要把字幕密度误判成视觉密度；必要时减少截图、增加结构化重绘。
- 若选择 crop 或放大，必须确认最终 PDF 页面里仍然清晰；拒绝粗糙裁剪、模糊放大和明显未完成的图像处理。

## Figure Review Questions

交付前，至少逐张问一次：

- 没有这张图，正文会损失什么
- 它是否已经是当前可得来源里最清楚的版本
- 它是否在最终 PDF 页面中仍然足够大、足够清楚
- 它是否只是“有图总比没图好”的占位图
- 如果最终没有做图，waiver 原因是否在 ledger 里写清楚了

只要其中任一答案明显不合格，就应删图、换图、重绘或记录 waiver。

## 最终章节要求

`\\section{总结与延伸}` 不只是一个收尾标题。默认应包含：

- 讲者在结尾部分真正有价值的 closing discussion
- 你的 own distillation：核心主张、机制、结构关系
- 清晰的 takeaways、限制、开放问题或下一步

如果结尾部分只有礼貌性告别，可以裁掉这些低价值内容，但不能因此省略总结章节本身。

## 交付 Bundle

默认交付应尽量包括：

- `note.tex`
- 官方封面图文件
- 正文引用的本地 figure assets
- `note.pdf`

在以下场景中，建议一并保留额外产物：

- 使用 ASR：保留 `transcript.srt`
- 调试复杂取图：保留 `montages/` 或 overview 产物
- 做 QA：保留 `pdf_preview/`
- 视觉义务复杂：保留 `work/visual_obligation_ledger.json`

## 最终检查

交付前至少确认：

- 封面图来自官方封面而不是任意视频帧
- 图像脚注中的时间区间与正文叙述一致
- 高价值 closing discussion 没有被误删
- 每张保留图片都通过了必要性与清晰度复查
- 每个高优先级视觉义务都已被兑现、替换或豁免
- 交付 bundle 至少包含 `.tex`、图片资源和 `note.pdf`
