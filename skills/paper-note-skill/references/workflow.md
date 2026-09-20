# 双语批注工作流

## 目标

这个 skill 现在只产出一个 PDF：双语逐句阅读版。

阅读顺序固定为：

1. 原文句子
2. 紧跟对应中文句子
3. 再进入下一组句子

中英文对应句子默认保持同一种功能色，两边都要着色。
中文默认 inline 接在英文后面，不额外起段，不改变原论文的段落推进。

默认保留：

- 句子颜色
- `tcolorbox` 章节总评

可选保留：

- `\pnote{功能|判断}{评}` 功能块分析

## 产物结构

初始化后，工作区内应至少有：

- `paper_note_annotations.tex`
- `paper_note_bilingual.tex`
- 原始主文档与原始章节 `*.tex`

## 初始化

如果想一条命令直接跑完整工作流：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py run <arxiv-id-or-url>
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

它会顺序执行：

- 拉源码
- 初始化双语工作区
- lint
- quick build
- full build

先拉源码：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py fetch <arxiv-id-or-url>
```

再初始化：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py setup <workspace>
```

如果默认就不想显示 `\pnote`：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py setup <workspace> --notes off
```

初始化脚本会：

- 检测主入口
- 写入共享宏文件 `paper_note_annotations.tex`
- 生成唯一编译入口 `paper_note_bilingual.tex`
- 在 `--force` 时清理旧的双 PDF 产物
- 为中文逐句部分提供和英文功能宏一一对应的着色宏
- 提供安全双语标题宏，避免中文直接进入 `.aux` / 书签
- 让中文逐句宏默认以 inline 方式跟在英文后面
- 保留句子级着色，但 `\pnote` 默认按相邻同功能块合并，而不是一句一个
- 默认把 `\pnote` 放在对应功能块最后一句中文后面

## 编译

预检：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py lint <workspace>
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --quick
```

正式编译：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace>
```

如果入口文件需要强制和当前主文档重新同步：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --refresh-entry
```

正式编译后，再单独跑视觉检查：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py visual-check <workspace> --pdf paper_note_bilingual.pdf
```

视觉检查会：

- 渲染前几页 PNG 预览到 `.paper_note_visual_check/`
- 扫描源码里的 `wrapfigure` / `wraptable`
- 给出 `status`、`note` 和风险列表

如果当前编译目标是 `paper_note_bilingual.tex`，而且原始主文档比入口文件更新，编译脚本也会自动先刷新入口，再继续 lint 和 build。

如果看到 `wrapfigure` / `wraptable` 风险，或预览页已经出现正文与浮动体互相挤压，优先把对应环境回退成普通 `figure` / `table`，再重新编译。

如果当前模板还是 `pdflatex + CJKutf8`，而且你需要双语标题，不要手写：

```latex
\title{\bititle{...}{...}}
\section{\bititle{...}{...}}
```

优先改成：

```latex
\bipapertitle{English Title}{中文标题}
\bisec{Introduction}{引言}
```

这样英文 short title 会进入目录、书签和 `.aux`，中文只出现在页面显示层，能避开这次 case 里最常见的 Unicode 回写问题。

默认目标是：

- `paper_note_bilingual.tex`

如需显式指定：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --tex paper_note_bilingual.tex
```

如果先想检查本机依赖和 workspace 前提：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py doctor --workspace <workspace>
```

## 该读哪些 reference

- 判断批注粒度、颜色和 `\pnote`：读 [annotation-rules.md](annotation-rules.md)
- 写逐句翻译与中英交替结构：读 [translation-format.md](translation-format.md)
- 查章节总评和章节重点：读 [section-guidance.md](section-guidance.md)
- 查宏、lint、编译注意点：读 [latex-and-lint.md](latex-and-lint.md)
