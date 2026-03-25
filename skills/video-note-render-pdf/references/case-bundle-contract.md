# Case Bundle Contract

统一 video-note case 目录的目标是把平台差异、设备差异和 backend 差异压平，让下游写作只面对一套稳定产物。

## 推荐目录布局

```text
<workspace>/<case-id>/
├── case_manifest.json
├── metadata.json
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
└── work/
```

## 必需产物

- `metadata.json`: 平台原始 metadata 的规范化版本
- `preflight.json`: 平台、格式、封面、章节、推荐模式等事实层摘要
- `subtitle_probe.json`: 平台字幕与 cookies 探测结果
- `transcriber_probe.json`: ASR 探测结果；如果平台字幕已成功，仍可记录为 `required=false`
- `transcript.json` / `transcript.srt` / `transcript.txt`: 标准 transcript 三件套

## 推荐产物

- `case_manifest.json`: 总览本 case 的核心路径、来源和状态
- `overview_frames/`: 粗采样总览帧
- `montages/`: 高召回阶段使用的 contact sheet
- `work/`: 中间候选帧、probe log、转写 log

## `case_manifest.json`

推荐至少记录：

- `source_url`
- `platform`
- `video_id`
- `runtime.repo_root`
- `runtime.workspace_root`
- `runtime.subtitle_source`
- `runtime.transcript_source`
- `runtime.recommended_mode`
- `artifacts.*`

可以直接从 `assets/case-manifest.template.json` 起草。

## 编译与 QA

`note.tex` 进入交付前至少应经过：

```bash
latexmk -xelatex -interaction=nonstopmode note.tex
```

若生成 `note.pdf`，建议同时输出页面预览到 `pdf_preview/`，用于快速检查跨页漂移、footnote 位置和图像可读性。
