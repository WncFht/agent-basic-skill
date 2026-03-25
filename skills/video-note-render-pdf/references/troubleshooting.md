# Troubleshooting

## 找不到 runtime repo

优先检查：

- `VIDEO_NOTE_PIPELINE_REPO`
- `AGENT_BASIC_SKILL_SOURCE_OVERRIDES`
- 默认路径 `~/Desktop/src/video-note-pipeline`

如果 runtime repo 远端还未发布，先用环境变量或 local override 指向本地 clone。

## 找不到 workspace

默认 workspace 是 `~/Desktop/src/video_notes`。如果该目录不存在：

- 先创建它，或
- 设置 `VIDEO_NOTE_WORKSPACE_ROOT`

不要把 case 目录写回当前 skill 目录。

## 平台字幕拿不到

检查顺序：

1. 匿名字幕探测是否失败
2. cookies 路径是否被尝试
3. 是否记录了失败原因

只有这两层都失败，才进入 ASR。

## ASR fallback 不稳定

应先看 `transcriber_probe.json`，确认：

- 哪些 backend 被检查过
- sample probe 是否成功
- device / compute type 是什么

不要在没 probe 成功前直接启动长转写。

## GPU / 代理问题

视频平台访问或下载异常时，先在同一 shell 会话里设置代理：

```bash
export https_proxy=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
export all_proxy=http://127.0.0.1:7897
```

GPU 可用性应由 runtime repo 的 probe 给出，不要靠猜测。

## LaTeX 编译问题

优先使用：

```bash
latexmk -xelatex -interaction=nonstopmode note.tex
```

常见问题：

- 用了 `pdflatex` 导致中文模板不稳定
- 图像浮动把 footnote 挤到别页
- 引用了不存在的本地图片路径
