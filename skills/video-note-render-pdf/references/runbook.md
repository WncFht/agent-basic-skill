# Runbook

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

必要时先写一个轻量 content map，并为长视频或复杂 case 落下：

- `work/section_alignment.json`
- `review/coverage-note.md`

## 4. 起草正文

- 从 `assets/notes-template.tex` 开始
- 把封面图、链接、作者、发布日期、时长填进去
- 用结构化章节重建教学逻辑
- 让主体章节篇幅大致跟着视频重点分布走，而不是默认写成固定厚度摘要
- 在大章节末尾加 `\subsection{本章小结}`
- 文末写 `\section{总结与延伸}`

## 5. 写作驱动取图

不要先把图片预算定死。先问：

- 这一段正文为什么需要图
- 它需要的是证据、解释、导向，还是场景锚点
- 更好的来源是视频帧、外部原件，还是重绘

然后再决定：

- 是否少图多重绘
- 是否需要高召回窗口抽帧
- 哪些地方更适合用 TikZ / 外部图而不是原始截图

## 6. 编译与第一次视觉检查

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

## 7. 做一轮 revision loop

至少做三件事：

- coverage pass：重新对照字幕和内容地图，看重点是否写对、写够
- figure pass：逐图判断必要性、来源选择、清晰度和裁剪完成度
- page pass：结合 `pdf_preview/` 修页面级问题

必要时把结果写入：

- `review/coverage-note.md`
- `review/figure-audit.md`
- `review/page-flags.md`

## 8. 什么时候停下来修 pipeline

遇到以下情况，应先修 runtime 事实层而不是硬写：

- 没有 `metadata.json`
- 只有纯文本 transcript，没有带时间戳版本
- `subtitle_probe.json` 缺少来源信息
- `transcriber_probe.json` 没有 backend 选择依据
- 还不知道视频属于哪种模式
- 还无法按时间窗把正文重点段和 transcript 对齐
