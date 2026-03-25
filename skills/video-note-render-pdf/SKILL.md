---
name: video-note-render-pdf
description: Use when the user wants to turn a YouTube or Bilibili lecture, tutorial, or technical talk into a structured Chinese LaTeX/PDF note through the unified video-note wrapper and an external runtime repo.
---

# Video Note Render PDF Wrapper

这是一个 thin wrapper。真正的运行时代码应位于外部 `video-note-pipeline` 类 runtime repo 中；当前 skill 只保留统一入口、模板、参考文档和轻量路径解析脚本。

## 外部依赖与工作区

- 规划中的 canonical runtime repo：`WncFht/video-note-pipeline`
- 默认 clone 路径：`$HOME/Desktop/src/video-note-pipeline`
- 环境变量：`VIDEO_NOTE_PIPELINE_REPO`
- source override key：`repo:WncFht/video-note-pipeline`
- 默认 case workspace：`$HOME/Desktop/src/video_notes`
- workspace 环境变量：`VIDEO_NOTE_WORKSPACE_ROOT`
- workspace override key：`workspace:video-notes`
- 安装命令：在 `agent-basic-skill` 仓根目录运行 `python scripts/install_skill.py video-note-render-pdf`

安装器会读取同目录下的 `external-repos.json`；它只在显式安装时检查或 clone 外部仓，运行时 resolver 仍然只做检测不做安装。

如果 runtime repo 的远端还没稳定发布，优先通过环境变量或 local source override 指向本地 clone。

## 先解析 runtime repo 与 workspace

优先级：

1. 显式参数：`--runtime-repo`、`--workspace-root`
2. 环境变量：`VIDEO_NOTE_PIPELINE_REPO`、`VIDEO_NOTE_WORKSPACE_ROOT`
3. 本地 source override：`repo:WncFht/video-note-pipeline`、`workspace:video-notes`
4. 默认候选路径：`$HOME/Desktop/src/video-note-pipeline`、`$HOME/Desktop/src/video_note_pipeline`、`$HOME/Desktop/src/video_notes`

解析示例：

```bash
python scripts/resolve_video_note_paths.py --json
```

只打印 runtime repo：

```bash
python scripts/resolve_video_note_paths.py --print runtime_repo
```

如果解析失败，先修正路径与环境，再继续后续 pipeline。不要把下载产物、cache、cookie、模型文件或 case 输出写回当前 skill 目录。

## 运行时边界

skill 目录只保留：

- `SKILL.md`
- `agents/openai.yaml`
- `assets/notes-template.tex`
- `assets/case-manifest.template.json`
- `references/*.md`
- `scripts/resolve_video_note_paths.py`

runtime repo 负责：

- URL 归一化与 platform adapter
- metadata / subtitle / cookies / format / ASR probe
- transcript 标准化输出
- overview frames / montage / extraction helper
- build / preview / QA helper

如果运行时没有先产出事实层 artifact，不要直接进入正文写作。

## 必要 artifact contract

在模型开始组织正文前，case 目录至少应具备：

- `metadata.json`
- `preflight.json`
- `subtitle_probe.json`
- `transcriber_probe.json`
- `transcript.json`
- `transcript.srt`
- `transcript.txt`
- `recommended_mode`

推荐同时维护：

- `case_manifest.json`
- `overview_frames/` 或 montage
- `figures/`
- `note.tex`
- `note.pdf`

字段和目录约定见：

- `references/adapter-contract.md`
- `references/case-bundle-contract.md`
- `references/mode-routing.md`

## Subtitle-first 约束

统一 pipeline 必须遵循：

1. 先探测平台官方字幕
2. 匿名路径失败后再探测 cookies 路径
3. 两层平台字幕都失败后，才进入 ASR probe / wrapper fallback

额外要求：

- 手工字幕优先于自动字幕
- 保留时间戳，不要过早压平为纯文本
- 记录字幕来源、语言、是否使用 cookies
- ASR 只负责 fallback，不是默认主路径

## 推荐工作流

1. 解析 runtime repo 与 workspace 路径。
2. 在 runtime repo 中先完成 metadata、subtitle probe、format probe、preflight。
3. 检查 `recommended_mode`、overview montage 和 transcript 质量，再决定截图强度。
4. 从 `assets/notes-template.tex` 起稿，必要时用 `assets/case-manifest.template.json` 固定 case 元数据。
5. 让模型在 `talking-head / visual-light / static-outline / board-heavy` 之间确认或覆写模式。
6. 依据字幕时间窗和 montage 结果选图；先高召回，再下采样。
7. 写出完整 `note.tex`，再用 `latexmk -xelatex` 编译并做 PDF 预览检查。

## 写作与配图规则

1. 默认使用中文写作，除非用户另有要求。
2. 使用 `\section{...}` / `\subsection{...}` 重建教学结构，而不是机械抄字幕。
3. 首页优先使用视频官方封面图，而不是任意视频帧。
4. 每个大章节以 `\subsection{本章小结}` 收束，文末必须有 `\section{总结与延伸}`。
5. 数学公式使用展示公式，并紧跟扁平列表解释符号。
6. 代码示例使用 `lstlisting`，并带描述性 `caption`。
7. `importantbox`、`knowledgebox`、`warningbox` 只承载高信号内容，不做装饰。
8. 图片必须放在盒子之外。
9. 任何来自视频帧的图像，都要在同页底部注明具体时间区间。
10. 选图按教学价值，不按固定配额；同一节可以有多张关键图。
11. 遇到逐步显现的幻灯片、白板或动画时，优先定位最终完整可读状态。
12. 截图仍不够清晰时，优先补充 TikZ / PGFPlots 或外部生成图，而不是塞进低信息截图。

## 编译与验证

推荐命令：

```bash
latexmk -xelatex -interaction=nonstopmode note.tex
```

最低验证要求：

- `.tex` 可编译
- PDF 中封面图、关键 figures、footnote provenance 与目录结构都正确
- 没有 `[cite]` 占位符
- figure 的时间区间与正文描述一致

## 按需读取的参考文档

- `references/adapter-contract.md`
- `references/case-bundle-contract.md`
- `references/mode-routing.md`
- `references/runbook.md`
- `references/troubleshooting.md`
