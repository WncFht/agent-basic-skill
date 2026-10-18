---
name: paper-note-skill
description: Pull an arXiv LaTeX source paper into the default paper workspace, inject bilingual annotation support into the original LaTeX project, and produce a single bilingual PDF where each English sentence is followed by its Chinese translation, with optional function-block pnotes and default tcolorbox summaries. Use when the user asks for an annotated paper source workflow rather than a rewritten summary.
---

# Paper Note Skill

目标是把一篇 arXiv LaTeX 论文处理成一份可编译的双语 PDF：

- 先写英文原句
- 紧跟对应中文句子
- 可选择是否带按功能块合并的 `\pnote`
- `tcolorbox` 章节总评默认保留

## 何时使用

- 用户要你处理 arXiv LaTeX 源码，而不是只读 PDF
- 用户要“原文上批注”“功能块批注”“章节总评”“逐句中文翻译”
- 用户要最终可编译的原始 `.tex` 和 PDF

## 先读哪份 reference

- 工作流和产物结构：[`references/workflow.md`](references/workflow.md)
- 批注规则、颜色和 `\pnote`：[`references/annotation-rules.md`](references/annotation-rules.md)
- 逐句翻译格式：[`references/translation-format.md`](references/translation-format.md)
- 章节重点与 `annsummary`：[`references/section-guidance.md`](references/section-guidance.md)
- 宏、lint、编译约束：[`references/latex-and-lint.md`](references/latex-and-lint.md)

## 最短流程

### 0. 一键跑完整链路

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py run <arxiv-id-or-url>
```

默认会串起来执行：

- 拉源码
- 初始化双语入口
- lint
- quick build
- full build
- visual check

如果只想先停在 quick build：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py run <arxiv-id-or-url> --skip-full-build
```

默认工作区根目录会按以下顺序解析：

- 显式 `--root`
- 环境变量 `PAPER_NOTE_OUTPUT_ROOT`
- `~/.paper-note-skill/config.yaml`
- 仓库根目录下的 `paper/`

如果想交互式设置默认输出目录：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py config
```

### 1. 拉源码

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py fetch <arxiv-id-or-url>
```

### 2. 初始化双语批注支持

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py setup <workspace>
```

如果默认就不想显示 `\pnote`：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py setup <workspace> --notes off
```

### 3. 按规则批注与翻译

- 英文原句仍直接写在原始 `*.tex`
- 中文句子直接接在英文句子后面，不放脚注，也不要打断原段落结构
- 中英文对应句子默认保持同一种功能色，两边都要着色
- 优先使用与英文句子功能对应的 `\zh*sent` 宏；` \zhtrans{...}` 只留给非句级或无功能色文本
- `\pnote` 默认按“相邻、同功能”的英文句群合并，不再一句一个
- `\pnote` 仍只跟在对应功能块最后一句中文后面
- 节末继续补 `annsummary`
- caption 默认不翻译
- references / bibliography / BibTeX 数据这类部分默认不翻译，也不做逐句分析

### 4. 编译 PDF

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py lint <workspace>
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --quick
```

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace>
```

默认只编：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --tex paper_note_bilingual.tex
```

如果主文档改过，想在编译前强制重生入口：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --refresh-entry
```

如果目标就是 `paper_note_bilingual.tex`，编译脚本也会在发现原始主文档更新后自动刷新入口。

正式编译后，再单独跑视觉检查：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py visual-check <workspace> --pdf paper_note_bilingual.pdf
```

如果出现 `wrapfigure` / `wraptable` 风险或预览页异常，就先修排版再继续批注。

如果先想检查本机依赖和 workspace 前提：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py doctor --workspace <workspace>
```

## 输出要求

- 保留原论文结构
- 产物在论文工作区内
- 最终至少要有：
  - 原始主文档，例如 `main.tex`
  - 原始章节 `.tex`
  - 共享宏文件 `paper_note_annotations.tex`
  - 双语入口 `paper_note_bilingual.tex`
  - 单一双语 PDF

## 边界

- 脚本只负责拉取、初始化和编译
- 真正的批注判断和逐句中文翻译，严格按 references 中的规则在源码上完成
