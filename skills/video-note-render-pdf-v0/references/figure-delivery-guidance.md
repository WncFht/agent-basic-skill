# Figure And Delivery Guidance

这份文档承接旧 video-note skill 里最关键、但不适合全部堆回主 `SKILL.md` 的细粒度 figure heuristics 与交付 expectations。

## 高召回选帧规则

- 先高召回，再下采样；不要一猜一个时间戳就只截一张图。
- 优先使用字幕时间窗定位候选画面；若字幕不可用，则退回 overview 与视觉峰值窗口。
- 能做 montage / contact sheet 时，优先先看候选集合，再挑最终图。
- 如果首张截图处在动画、PPT reveal 或白板构建中间态，继续向前后搜索，直到找到最完整可读状态。
- 若多个相邻候选只在 reveal 完整度上有差异，优先选择信息更完整的后者。
- 对于密集视觉段落，可以先过采样，再丢弃低信息候选；不要过早收窄候选集。

## 画面质量处理

- 画面过松时，允许裁剪、局部放大或拆成多张图。
- 同一节可以有多张关键图，不必为了“看起来简洁”强行压成一张低可读大图。
- 若截图始终不够清晰，优先用 TikZ / PGFPlots / 外部图复画，而不是塞进低信息截图。
- 若视觉信息稀疏，不要把字幕密度误判成视觉密度；必要时减少截图、增加结构化重绘。

## 最终章节要求

`\\section{总结与延伸}` 不只是一个收尾标题。默认应包含：

- 讲者在结尾部分真正有价值的 closing discussion
- 你的 own distillation：核心主张、机制、结构关系
- 清晰的 takeaways、限制、开放问题或下一步

如果结尾部分只有礼貌性告别，可以裁掉这些低价值内容，但不能因此省略总结章节本身。

## 交付 bundle

默认交付应尽量包括：

- `note.tex`
- 官方封面图文件
- 正文引用的本地 figure assets
- `note.pdf`

在以下场景中，建议一并保留额外产物：

- 使用 ASR：保留 `transcript.srt`
- 调试复杂取图：保留 `montages/` 或 overview 产物
- 做 QA：保留 `pdf_preview/`

## 最终检查

交付前至少确认：

- 封面图来自官方封面而不是任意视频帧
- 图像脚注中的时间区间与正文叙述一致
- 高价值 closing discussion 没有被误删
- 交付 bundle 至少包含 `.tex`、图片资源和 `note.pdf`
