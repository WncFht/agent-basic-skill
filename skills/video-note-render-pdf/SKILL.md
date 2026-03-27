---
name: video-note-render-pdf
description: Use when the user wants to turn a YouTube or Bilibili lecture, tutorial, or technical talk into a structured Chinese LaTeX/PDF note that preserves the video's real teaching content, scales coverage roughly with subtitle and time emphasis, selects figures through writing-driven evidence or explanation needs, ends with a final synthesis chapter, and routes through the unified video-note wrapper plus an external runtime repo.
---

# Video Note Render PDF Wrapper

这是一个 thin wrapper。真正的运行时代码应位于外部 `video-note-pipeline` 类 runtime repo 中；当前 skill 只保留统一入口、模板、参考文档和轻量路径解析脚本。

## Goal

统一 video-note pipeline 的目标仍然是产出一份高质量、可交付的中文 `.tex` 讲义和最终 PDF，而不是只把字幕改写成摘要。默认交付应尽量满足：

- 以视频真实教学内容为主，而不是仅依赖字幕转写
- 主体篇幅与视频内容强度大致同向扩张，而不是长视频也写成固定厚度摘要
- 首页优先使用视频官方封面图，而不是任意视频帧
- 图片由正文写作需求驱动，优先选择真正必要且清晰的高信息量 figures
- 文末包含一个真正的 `\section{总结与延伸}`，吸收讲者有价值的 closing discussion，并加入你自己的结构化提炼
- 完稿后重新对照字幕和关键图片做事后修订，而不是把重复 build 视为已经完成复查
- 最终结果包含完整 `.tex`、本地图片资源和成功编译的 PDF

## 平台摘要

统一 skill 不再按平台拆成两个平行入口，但平台特有边界仍然存在：

- YouTube：优先使用公开视频可直接获得的官方字幕，手工字幕优先于自动字幕
- Bilibili：字幕更稀缺，1080P+ 常常需要 cookies，分 P 视频要先明确处理范围，`b23.tv` 需要归一化，弹幕不能作为教学内容源
- 当平台字幕与 cookies 字幕都不可用时，才进入 ASR fallback；若字幕和 ASR 都不可接受，允许转入 `visual-only` 的取图与重绘思路

平台细则见 `references/platform-notes.md`。

## 外部依赖与工作区

- 规划中的 canonical runtime repo：`WncFht/video-note-pipeline`
- 默认 clone 路径：`$HOME/Desktop/src/video-note-pipeline`
- 环境变量：`VIDEO_NOTE_PIPELINE_REPO`
- source override key：`repo:WncFht/video-note-pipeline`
- 默认 case workspace：`<runtime_repo>/.local/workspaces/video-notes`
- workspace 环境变量：`VIDEO_NOTE_WORKSPACE_ROOT`
- workspace override key：`workspace:video-notes`
- 安装命令：在 `agent-basic-skill` 仓根目录运行 `python scripts/install_skill.py video-note-render-pdf`

安装器会读取同目录下的 `external-repos.json`；它只在显式安装时检查或 clone 外部仓，运行时 resolver 仍然只做检测不做安装。

如果 runtime repo 的远端还没稳定发布，优先通过环境变量或 local source override 指向本地 clone。

首次进入 runtime repo 后，优先执行：

```bash
uv sync --extra dev
pre-commit install
```

如果本机需要本地 ASR backend，再按需增加：

```bash
uv sync --extra dev --extra asr-cpu
```

## 先解析 runtime repo 与 workspace

优先级：

1. 显式参数：`--runtime-repo`、`--workspace-root`
2. 环境变量：`VIDEO_NOTE_PIPELINE_REPO`、`VIDEO_NOTE_WORKSPACE_ROOT`
3. 本地 source override：`repo:WncFht/video-note-pipeline`、`workspace:video-notes`
4. 默认候选路径：runtime repo 下的 `.local/workspaces/video-notes`；runtime repo 自身仍优先从 `$HOME/Desktop/src/video-note-pipeline`、`$HOME/Desktop/src/video_note_pipeline` 检测

解析示例：

```bash
python scripts/resolve_video_note_paths.py --json
```

只打印 runtime repo：

```bash
python scripts/resolve_video_note_paths.py --print runtime_repo
```

如果解析失败，先修正路径与环境，再继续后续 pipeline。若未显式指定，workspace 默认解析到 runtime repo 下的 `.local/workspaces/video-notes`，并由 runtime 在实际运行时按需创建。不要把下载产物、cache、cookie、模型文件或 case 输出写回当前 skill 目录。

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
- `preflight.json.recommended_mode`
- `subtitle_probe.json`
- `transcriber_probe.json`
- `transcript.json`
- `transcript.srt`
- `transcript.txt`

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

## Teaching Content Rules

优先从以下信息重建讲义：

- 视频标题、章节、时长与关键信息
- 视频官方封面与 metadata
- 幻灯片、白板、公式、图表、表格、产品界面与代码片段
- 字幕中的解释、举例和口头强调

以下内容默认不应进入正文主叙事，除非它们本身承载教学价值：

- greetings
- small talk
- sponsorship
- channel logistics，例如“一键三连”、关注、投币、抽奖、口播推广
- Bilibili danmaku 或其他高噪声互动文本
- 纯礼貌性的 closing pleasantries

如果讲者在结尾部分给出了总结、局限、经验判断、后续方向、实践建议或开放问题，应把这些内容保留到最终 `总结与延伸` 中，而不是简单裁掉。若 transcript 质量不足以支撑判断，先修事实层 artifact，必要时切换到 `visual-only` 思维模式，而不是硬写。

## 推荐工作流

1. 解析 runtime repo 与 workspace 路径。
2. 若是 Bilibili 分 P 视频，先确认本次要处理哪些 part，并把选择结果写入 case metadata。
3. 如果需要 cookies，先在 runtime repo 中运行 `uv run video-note cookies-export youtube --browser edge` 或 `uv run video-note cookies-export bilibili --browser edge`。
4. 在 runtime repo 中按顺序运行 `uv run video-note prepare <url>`、`uv run video-note probe <url>`、`uv run video-note transcript <url>`、`uv run video-note overview <url>`。
5. 检查 `recommended_mode`、overview montage、part selection 和 transcript 质量，先确认内容覆盖风险，而不是直接进入固定配图节奏。
6. 先做 lightweight content map，按主题段或时间段估计主体章节的相对写作权重；必要时把结果落成 `work/section_alignment.json` 或 `review/coverage-note.md`。
7. 从 `assets/notes-template.tex` 起稿，必要时用 `assets/case-manifest.template.json` 固定 case 元数据，并在 `talking-head / visual-light / static-outline / board-heavy` 之外补充 `evidence-led / explanation-led / demo-led` 的 support profile 判断。
8. 先写主体正文，再按 claim 或解释需要选图；优先区分这是 `evidence image`、`explanation image`、`orientation image` 还是 `anchor image`，并依据字幕时间窗和 montage 结果做高召回取图。
9. 写出完整 `note.tex`，用 `uv run video-note build <url>` 或 `latexmk -xelatex` 编译并生成 `pdf_preview/`。
10. 至少做一轮三段式 revision loop：coverage pass 重新对照字幕，figure pass 重新审阅图片必要性与清晰度，page pass 结合 `pdf_preview/` 修版式与页面级问题。

## 写作与配图规则

1. 默认使用中文写作，除非用户另有要求。
2. 使用 `\section{...}` / `\subsection{...}` 重建教学结构，而不是机械抄字幕。
3. 首页优先使用视频官方封面图，而不是任意视频帧。
4. 主体章节与小节的篇幅分配，应大致反映视频中各主要段落的时长、字幕密度与论证强度；不要把长视频主体默认压成固定厚度摘要。
5. 每个大章节以 `\subsection{本章小结}` 收束；有必要时可增加 `\subsection{拓展阅读}`；文末必须有 `\section{总结与延伸}`，并纳入 speaker closing discussion、你的 own distillation 与明确 takeaways。
6. 在正式写作前先做轻量 content map；对长视频、高字幕量或 evidence-heavy case，建议把 coverage 判断显式落成 artifact。
7. 图片必须由正文需要驱动。先判断该段需要的是证据、解释、导向还是场景锚点，再决定去视频帧、外部原件还是自绘图找支撑。
8. 任何最终保留的图片，都应回答为什么需要它、为什么选这个来源、为什么不改用更清晰的裁剪/放大/对照/重绘版本。
9. 对来自视频帧的图像，禁止接受潦草的图像处理；若裁剪、放大或 pair 之后仍不清楚，应改成重绘、外部原件或直接删图。
10. 数学公式使用展示公式，并紧跟扁平列表解释符号。
11. 代码示例使用 `lstlisting`，并带描述性 `caption`。
12. `importantbox` 用于核心概念与关键机制，`knowledgebox` 用于补充背景与类比，`warningbox` 用于误区、限制和易错点；三类盒子都只承载高信号内容，不做装饰。
13. 图片必须放在盒子之外。
14. 任何来自视频帧的图像，都要在同页底部注明具体时间区间。
15. 选图按教学价值，不按固定配额；同一节可以有多张关键图。
16. 遇到逐步显现的幻灯片、白板或动画时，优先定位最终完整可读状态。
17. 不要因为省时间而跳过高召回候选帧检查，也不要把字幕密度误当成视觉密度。
18. 截图仍不够清晰时，优先补充 TikZ / PGFPlots 或外部生成图，而不是塞进低信息截图。
19. 完稿后至少重新阅读一次字幕中的重点段和最终保留的关键图片，再决定是否补写、删图或改图。

更细的 figure heuristics、delivery expectations 与最终章节检查项见 `references/figure-delivery-guidance.md`；coverage 目标与 revision loop 见 `references/coverage-and-revision-guidance.md`。

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
- 主体章节篇幅没有明显背离视频重点分布
- 最终保留的图片都通过了必要性与清晰度复查

## 交付物

默认交付 bundle 至少包括：

- 最终 `note.tex`
- 首页引用的官方封面图
- 正文引用的本地 figure assets
- 成功编译的 `note.pdf`

如果本次 case 依赖 ASR 或需要复盘字幕来源，推荐同时保留：

- `transcript.srt`
- `case_manifest.json`
- `pdf_preview/` 或其他 QA 产物
- `review/` 或 `work/` 下的 coverage / figure / page 修订痕迹

如果在 Windows 上运行 runtime repo，优先确认：

- `ffmpeg`、`latexmk` 在 `PATH` 中
- case workspace 不要落到只读目录
- `transcriber_probe.json` 已确认 CUDA sample 成功；否则默认按 CPU 路径处理

## 按需读取的参考文档

- `references/adapter-contract.md`
- `references/coverage-and-revision-guidance.md`
- `references/case-bundle-contract.md`
- `references/platform-notes.md`
- `references/figure-delivery-guidance.md`
- `references/mode-routing.md`
- `references/runbook.md`
- `references/troubleshooting.md`
