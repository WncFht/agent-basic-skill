# video-render-pdf skills

这个仓库托管两个 Codex skill，用于将视频讲座转换为结构化的中文 LaTeX 讲义和最终 PDF。

| Skill | 平台 | 说明 |
|-------|------|------|
| `youtube-render-pdf` | YouTube | 原始版本，利用 YouTube CC 字幕和章节结构 |
| `bilibili-render-pdf` | Bilibili (B站) | 适配 B 站的字幕缺失、登录高清、分P视频等特点 |

两个 skill 共享相同的写作规则、配图策略和 LaTeX 模板，但在素材获取阶段有平台特定的差异。

### Bilibili 版的核心差异

- **字幕三级回退**：CC 字幕 → Whisper 语音转写 → 纯视觉模式（B 站大量视频无 CC 字幕）
- **登录获取高清**：1080P+ 需要 cookies（`yt-dlp --cookies-from-browser chrome`）
- **分P视频处理**：自动检测多 P，询问用户处理范围
- **平台话术过滤**：额外排除"一键三连"、"关注投币"等非教学内容
- **额外依赖**：`whisper`（openai-whisper）用于语音转写

### 共同特点

- 以视频真实教学内容为主，而不是只依赖字幕转写
- 优先使用原始视频封面作为首页封面图
- 按教学价值提取关键画面、图表、公式和代码片段
- 生成带 `\section{}` / `\subsection{}` 结构的完整 `.tex`
- 最终必须落到可交付的 PDF

## 仓库结构

```text
.
├── LICENSE
├── README.md
└── skills/
    ├── youtube-render-pdf/
    │   ├── SKILL.md
    │   ├── agents/
    │   │   └── openai.yaml
    │   └── assets/
    │       └── notes-template.tex
    └── bilibili-render-pdf/
        ├── SKILL.md
        ├── agents/
        │   └── openai.yaml
        └── assets/
            └── notes-template.tex
```

## 包含内容

- `skills/youtube-render-pdf/SKILL.md`
  YouTube 版 skill 的主说明文件，定义适用场景、工作流、写作规则、配图规则和最终交付要求。
- `skills/bilibili-render-pdf/SKILL.md`
  Bilibili 版 skill 的主说明文件，在 YouTube 版基础上增加了字幕回退、分P处理等平台适配。
- `skills/*/assets/notes-template.tex`
  共享的默认 LaTeX 模板，包含首页封面位、盒子样式、代码块样式和正文占位结构。
- `skills/*/agents/openai.yaml`
  给 agent UI 使用的显示名称、简介和默认提示。

## 使用方式

如果你想在本地 Codex 环境中使用这些 skill，可以把对应目录放到你的技能目录中：

```bash
mkdir -p ~/.codex/skills

# YouTube 版
cp -R skills/youtube-render-pdf ~/.codex/skills/

# Bilibili 版
cp -R skills/bilibili-render-pdf ~/.codex/skills/
```

然后在 Codex 中使用对应 skill 处理视频链接，请求生成讲义 `.tex` 和最终 PDF。

## 外部依赖

| 工具 | 两个 skill 都需要 | 仅 Bilibili 版需要 |
|------|:-:|:-:|
| `yt-dlp` | ✓ | |
| `ffmpeg` | ✓ | |
| `xelatex` (TeX Live + CTeX) | ✓ | |
| `magick` (ImageMagick) | ✓ | |
| `whisper` (openai-whisper) | | ✓ |

此外，运行 skill 的 coding agent 必须具备一定的读图能力。

## 适用场景

- 技术课程笔记整理
- YouTube / Bilibili 教学视频转 LaTeX 讲义
- 需要封面图、关键帧和总结章节的高质量课程文档生成

## License

仓库保留了根目录下原有的 `LICENSE` 文件。使用、分发或二次修改时，请以该许可证为准。
