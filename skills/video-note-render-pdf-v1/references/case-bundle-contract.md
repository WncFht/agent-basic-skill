# Case Bundle Contract

统一 video-note case 目录的目标是把平台差异、设备差异和 backend 差异压平，让下游写作只面对一套稳定产物。

## 推荐目录布局

```text
<workspace>/<case-id>/
├── case_manifest.json
├── metadata.json
├── metadata.raw.json
├── preflight.json
├── subtitle_probe.json
├── transcriber_probe.json
├── transcript.json
├── transcript.srt
├── transcript.txt
├── cover.*
├── note.tex
├── note.pdf
├── figures/
├── overview_frames/
├── montages/
├── pdf_preview/
├── review/
└── work/
```

## 必需产物

- `metadata.json`: 平台原始 metadata 的规范化版本
- `metadata.raw.json`: 原始平台抓取结果，便于调试 adapter 差异
- `preflight.json`: 平台、格式、封面、章节、推荐模式等事实层摘要
- `subtitle_probe.json`: 平台字幕与 cookies 探测结果
- `transcriber_probe.json`: ASR 探测结果；如果平台字幕已成功，仍可记录为 `required=false`
- `transcript.json` / `transcript.srt` / `transcript.txt`: 标准 transcript 三件套

## 推荐产物

- `case_manifest.json`: 总览本 case 的核心路径、来源和状态
- `overview_frames/`: 粗采样总览帧
- `montages/`: 高召回阶段使用的 contact sheet
- `pdf_preview/`: PDF 页面预览图，便于快速肉眼检查
- `review/`: coverage、figure、page 三类 revision note
- `work/`: 中间候选帧、probe log、转写 log、overview/build 摘要

对于长视频、高字幕量或 evidence-heavy case，建议额外保留：

- `work/section_alignment.json`: 文档章节和视频时间段的轻量对齐结果
- `review/coverage-note.md`
- `review/figure-audit.md`
- `review/page-flags.md`

## `case_manifest.json`

推荐至少记录：

- `source_url`
- `normalized_url`
- `platform`
- `video_id`
- `runtime.repo_root`
- `runtime.workspace_root`
- `runtime.part_selection`
- `runtime.subtitle_source`
- `runtime.subtitle_language`
- `runtime.subtitle_kind`
- `runtime.transcript_source`
- `runtime.recommended_mode`
- `runtime.visual_only_reason`
- `artifacts.section_alignment`
- `artifacts.review_dir`
- `artifacts.*`

可以直接从 `assets/case-manifest.template.json` 起草。

补充约定：

- 若视频是分 P / multipart case，`runtime.part_selection` 应显式记录本次处理范围
- 若使用平台字幕，建议同时记录 `subtitle_language` 与 `subtitle_kind`
- 若进入 `visual-only`，`runtime.visual_only_reason` 不得为空
- `artifacts.cover_image`、`artifacts.figures_dir` 与 `artifacts.pdf_preview_dir` 应指向本地 case 内的稳定路径
- 若生成了 coverage 或 review artifact，建议在 `artifacts.section_alignment` 和 `artifacts.review_dir` 中显式记录它们

## 编译与 QA

`note.tex` 进入交付前至少应经过：

```bash
latexmk -xelatex -interaction=nonstopmode note.tex
```

若生成 `note.pdf`，建议同时输出页面预览到 `pdf_preview/`，用于快速检查跨页漂移、footnote 位置和图像可读性。
对于需要复盘 coverage 或选图决策的 case，建议同时保留 `review/` 与 `work/section_alignment.json`。
