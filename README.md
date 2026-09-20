# agent-basic-skill

`agent-basic-skill` 是一个可复用的 Codex skills 与 local agents 仓库。每个 skill 都直接存放在 `skills/<skill-name>/` 下，整个目录就是安装、同步和覆盖更新的最小单位；可复用的本地 agent 配置则放在 `agents/*.toml`。

如果你要让外部 AGENT 通过一句固定指令完成安装，使用面向 agent 的入口文档：[`.codex/INSTALL.md`](.codex/INSTALL.md)。

## 技能列表

| Skill | 用途 |
| --- | --- |
| [memory-skill](skills/memory-skill/SKILL.md) | 会话启动时读取/回写 curated memory repo（机器、repo、跨仓上下文）；自带 init/sync/resolve 脚本与模板，代理感知的 GitHub 同步。 |
| [paper-note-skill](skills/paper-note-skill/SKILL.md) | 把 arXiv LaTeX 源码整理成双语批注阅读版，产出可编译 PDF（英句后跟中文翻译、tcolorbox 摘要、函数块 pnotes）。 |
| [plot-skill](skills/plot-skill/SKILL.md) | 用 matplotlib 维护可复用的论文图表脚本和 preset（bar/donut/line/radar/scatter），统一配色与风格。 |
| [report-download](skills/report-download/SKILL.md) | 下载 A 股/港股上市公司财报 PDF（年报/中报/季报），官方源优先。 |

## 使用方法

安装单个 skill（复制到 `~/.codex/skills/`）：

```bash
python scripts/install_skill.py memory-skill
```

或手动复制整个 skill 目录：

```bash
mkdir -p "$HOME/.codex/skills/memory-skill"
rsync -a --delete skills/memory-skill/ "$HOME/.codex/skills/memory-skill/"
```

刷新整个 skills 仓：

```bash
mkdir -p "$HOME/.codex/skills"
rsync -a --delete skills/ "$HOME/.codex/skills/"
```

同步本仓附带的 local agents：

```bash
mkdir -p "$HOME/.codex/agents"
rsync -a agents/ "$HOME/.codex/agents/"
```

安装时请始终复制整个 `skills/<skill-name>/` 目录，而不是只拷贝 `SKILL.md`——skill 还依赖相邻脚本、模板、资源或参考文档。

更多示例见 [INSTALL.md](INSTALL.md)。

## Demo

paper-note-skill 双语批注 PDF 样例：[paper_note_bilingual.pdf](assets/paper_note_bilingual.pdf)

plot-skill 图表示例：[`skills/plot-skill/examples/`](skills/plot-skill/examples/)
