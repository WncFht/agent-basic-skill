# Runbook v2

## 1. 解析路径

先运行：

```bash
python scripts/resolve_video_note_paths.py --json
```

拿到：

- `runtime_repo`
- `workspace_root`

若失败，先修路径，不要继续写正文。

## 2. 先做事实层

进入 runtime repo 后，优先准备环境：

```bash
uv sync --extra dev
```

如果需要 cookies：

```bash
uv run video-note cookies-export youtube --browser edge
uv run video-note cookies-export bilibili --browser edge
```

然后按顺序完成：

```bash
uv run video-note prepare <url>
uv run video-note probe <url>
uv run video-note transcript <url>
uv run video-note overview <url>
```

目标不是“自动写完讲义”，而是稳定地产出事实层 artifact。

## 3. 先判断 coverage 风险，再决定写作重心

先看：

- `preflight.json`
- `preflight.json.recommended_mode`
- `overview_frames/` 或 montage
- transcript 质量

先决定：

- 主体内容可以拆成哪几个时间段或主题段
- 哪几段应当成为正文主力
- 是否存在明显的长视频 / 高字幕量 / evidence-heavy 风险
- 本次字数下限大概在哪里

必要时先写一个轻量 content map，并为长视频或复杂 case 落下：

- `work/section_alignment.json`
- `review/coverage-note.md`

## 4. 先算长度 guardrail，再写正文

根据 `transcript.txt` 计算：

- `transcript_txt_chars`
- `min_note_chars`
- `soft_note_char_range`
- `compression_ratio`

把结果写进 `work/section_alignment.json`。页数只当诊断指标，不要把它当目标。

## 5. 先做三轴路由

不要只继承 runtime 的 `recommended_mode`。在正文前显式写出：

- `carrier_family`
- `support_profile`
- `recall_budget`

必要时在 `work/section_alignment.json` 里记录覆写原因。

## 6. 视觉义务先于最终配图

不要先问“图片预算是多少”，而要先问“这段正文到底有哪些独立视觉义务”。

对 `demo-led`、`anchor-dense`、`document-led evidence` 段落，默认先写：

- `work/visual_obligation_ledger.json`

然后再决定：

- 是否需要单图、pair、crop pair 或 derived figure
- 哪些义务最终应该显式 waiver

## 7. 起草正文

- 从 `assets/notes-template.tex` 开始
- 把封面图、链接、作者、发布日期、时长填进去
- 用结构化章节重建教学逻辑
- 让主体章节篇幅跟着视频重点分布走，而不是默认写成固定厚度摘要
- 在大章节末尾加 `\subsection{本章小结}`
- 文末写 `\section{总结与延伸}`

## 8. 编译与第一次视觉检查

推荐命令：

```bash
uv run video-note build <url>
```

若只想直接编译当前 `note.tex`，也可以退回：

```bash
latexmk -xelatex -interaction=nonstopmode note.tex
```

检查：

- PDF 是否成功生成
- 图片与脚注是否留在同页
- 图表文字是否可读
- 目录、封面和总结章节是否完整

## 9. 做一轮 revision loop

至少做三件事：

- coverage pass：重新对照字幕和字数 guardrail，看重点是否写对、写够
- figure pass：逐图判断必要性、来源选择、清晰度和裁剪完成度
- page pass：结合 `pdf_preview/` 修页面级问题

必要时把结果写入：

- `review/coverage-note.md`
- `review/figure-audit.md`
- `review/page-flags.md`
- `review/revision-actions.json`

## 10. 什么时候停下来修 pipeline

遇到以下情况，应先修 runtime 事实层而不是硬写：

- 没有 `metadata.json`
- 只有纯文本 transcript，没有带时间戳版本
- `subtitle_probe.json` 缺少来源信息
- `transcriber_probe.json` 没有 backend 选择依据
- 还不知道视频属于哪种三轴组合
- 还无法按时间窗把正文重点段和 transcript 对齐
- `visual_obligation_ledger` 所依赖的候选图、候选页或 candidate windows 还没有稳定来源
