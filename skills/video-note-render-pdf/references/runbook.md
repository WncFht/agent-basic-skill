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

在 runtime repo 中优先完成：

- metadata probe
- subtitle probe
- cookies probe
- format probe
- ASR probe

目标不是“自动写完讲义”，而是稳定地产出事实层 artifact。

## 3. 先判断模式，再决定取图强度

先看：

- `preflight.json`
- `recommended_mode`
- `overview_frames/` 或 montage
- transcript 质量

再决定：

- 是否少图多重绘
- 是否需要高召回窗口抽帧
- 哪些地方更适合用 TikZ / 外部图而不是原始截图

## 4. 起草正文

- 从 `assets/notes-template.tex` 开始
- 把封面图、链接、作者、发布日期、时长填进去
- 用结构化章节重建教学逻辑
- 在大章节末尾加 `\subsection{本章小结}`
- 文末写 `\section{总结与延伸}`

## 5. 编译与视觉检查

推荐命令：

```bash
latexmk -xelatex -interaction=nonstopmode note.tex
```

检查：

- PDF 是否成功生成
- 图片与脚注是否留在同页
- 图表文字是否可读
- 目录、封面和总结章节是否完整

## 6. 什么时候停下来修 pipeline

遇到以下情况，应先修 runtime 事实层而不是硬写：

- 没有 `metadata.json`
- 只有纯文本 transcript，没有带时间戳版本
- `subtitle_probe.json` 缺少来源信息
- `transcriber_probe.json` 没有 backend 选择依据
- 还不知道视频属于哪种模式
