# agent-basic-skill

`agent-basic-skill` 是一个可复用的 Codex skills 与 local agents 仓库。每个 skill 都直接存放在 `skills/<skill-name>/` 下，整个目录就是安装、同步和覆盖更新的最小单位；可复用的本地 agent 配置则放在 `agents/*.toml`。

如果你要让外部 AGENT 通过一句固定指令完成安装，使用面向 agent 的入口文档：[`.codex/INSTALL.md`](.codex/INSTALL.md)。

## 技能列表

| Skill | 用途 |
| --- | --- |
| [memory-skill](skills/memory-skill/SKILL.md) | 会话启动时读取/回写 curated memory repo（机器、repo、跨仓上下文）；自带 init/sync/resolve 脚本与模板，代理感知的 GitHub 同步。 |
| [paper-note-skill](skills/paper-note-skill/SKILL.md) | 把 arXiv LaTeX 源码整理成双语批注阅读版，产出可编译 PDF（英句后跟中文翻译、tcolorbox 摘要、函数块 pnotes）。 |
| [asr](skills/asr/SKILL.md) | 将音频、视频转录为带时间戳的文字与 SRT 字幕。 |
| [figure-viz](skills/figure-viz/SKILL.md) | 用 TikZ 绘制研究结构图，用 matplotlib 绘制可复现的数据图表。 |
| [link-get](skills/link-get/SKILL.md) | 获取网页正文、视频字幕、论文 LaTeX 源或媒体文件。 |
| [paper-search](skills/paper-search/SKILL.md) | 在 arXiv、DBLP、OpenAlex、OpenReview、Semantic Scholar 和 Crossref 检索论文。 |
| [video-render-pdf](skills/video-render-pdf/SKILL.md) | 从视频、字幕与关键帧生成中文 LaTeX 课程笔记及 PDF。 |
| [setup-toolchain](skills/setup-toolchain/SKILL.md) | 配置格式化、lint、pre-commit、CI、agent 入口和 Markdown 预览环境。 |
| [skill-management](skills/skill-management/SKILL.md) | 维护多 CLI 共用的 skill 与 AGENTS.md，检查软链、命名和依赖。 |

plot-skill 和 report-download 已移入 [`vendor/`](vendor/README.md)，保留历史内容，不参与默认安装。图表任务使用 figure-viz。

## 使用方法

安装单个 skill（复制到共享的 `~/.agents/skills/`）：

```bash
python scripts/install_skill.py memory-skill --dest-root ~/.agents/skills
```

或手动复制整个 skill 目录：

```bash
mkdir -p "$HOME/.agents/skills/memory-skill"
rsync -a --delete skills/memory-skill/ "$HOME/.agents/skills/memory-skill/"
```

安装全部现役 skill：

```bash
python scripts/install_skill.py memory-skill paper-note-skill asr figure-viz link-get paper-search video-render-pdf setup-toolchain skill-management --dest-root ~/.agents/skills
```

同步本仓附带的 local agents：

```bash
mkdir -p "$HOME/.codex/agents"
rsync -a agents/ "$HOME/.codex/agents/"
```

安装时请始终复制整个 `skills/<skill-name>/` 目录，而不是只拷贝 `SKILL.md`——skill 还依赖相邻脚本、模板、资源或参考文档。

更多示例见 [INSTALL.md](INSTALL.md)。

新增 skill 的依赖声明和跨 skill 调用使用 `~/.agents/skills/<name>/`。安装只复制载荷，外部工具、虚拟环境与模型按各 skill 的说明另行初始化。安装器会替换指定目录，更新前保存本地修改；避免在 Codex 私有目录保留同名副本。

## Demo

paper-note-skill 双语批注 PDF 样例：[paper_note_bilingual.pdf](assets/paper_note_bilingual.pdf)

figure-viz 图表示例：[`skills/figure-viz/scripts/examples/`](skills/figure-viz/scripts/examples/)
