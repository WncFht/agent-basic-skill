# LaTeX 宏、lint 与编译约束

## 当前关键宏

初始化脚本会生成 `paper_note_annotations.tex`，其中关键宏包括：

- 句子功能宏：`\bgsent`、`\gapsent`、`\questionsent`、`\methodsent`、`\resultsent`、`\claimsent`、`\structsent`、`\relatedsent`
- 中文逐句宏：`\zhtrans` 与对应的 `\zh*sent`
- 重点句宏：`\keysent`、`\zhkeysent`
- 双语标题辅助：`\bititle`
- 安全双语标题宏：`\bipapertitle`、`\printzhpapertitle`、`\bisec`、`\bisubsec`、`\bisubsubsec`、`\bipara`
- 功能块分析：`\pnote`
- 章节总评：`annsummary`

## 中文与编译器

- 如果正文或总评里有中文，且编译链仍然是 `pdflatex`，要保留 `\usepackage{CJKutf8}`，并在正文外层包 `CJK*`。
- 初始化脚本会自动处理 `CJK*` 包裹和脚注编号恢复。
- 如果英文句子已经使用了功能色宏，中文对应句子也应使用同色的 `\zh*sent` 宏，而不是退回未着色或灰色说明。
- 中文逐句宏默认是 inline 形态，用来保持原段落结构；不要再把中文翻译写成额外段落块。
- 在 `pdflatex + CJKutf8` 下，不要把中文直接写进 `\title`、`\section`、`\subsection`、`\paragraph` 这类 moving argument。
- 如果要做双语标题，优先用安全宏，让英文 short title 进入 `.aux` / 书签，中文只留在页面显示层。

## 脚注约束

- 如果标题区、作者区或前文改过脚注样式，进入正文和批注区后要恢复正常编号。
- 启用 `\pnote` 时，脚注应显示连续的阿拉伯数字。
- 不要把 `\footnote` / `\footnotemark` 写进句子功能宏内部。
- `\pnote` 默认跟在一个功能块的最后一句英文后面，而不是每句都挂。

## 标题安全写法

正文标题推荐：

```latex
\bisec{Introduction}{引言}
\bisubsec{Main Findings}{主要发现}
\bipara{Limitations}{局限性}
```

论文题目推荐：

```latex
\bipapertitle{English Title}{中文标题}
...
\maketitle
\printzhpapertitle
```

避免：

```latex
\title{\bititle{English}{中文}}
\section{\bititle{English}{中文}}
```

这两种写法在 `pdflatex + CJKutf8 + hyperref` 下很容易把中文写进 `.aux` 或书签，随后在下一轮编译时触发 Unicode fatal。

## lint 应拦的内容

`paper_note.py lint` 至少会检查：

- `\annote{...}`
- 旧的 `\annnote{...}`
- 旧三参数 `\pnote{功能|判断}{译}{评}`
- 未配对 `$`
- 未闭合 `annsummary`
- `\pnote` 评语中的裸数学宏
- `annsummary` 中的裸数学宏
- `\bgsent` / `\zhbgsent` / `\zhtrans` 等 inline 文本宏中的裸数学宏
- 句子功能宏内部的 `\footnote` / `\footnotemark`
- `\title` / `\section` / `\paragraph` 等 moving argument 中的非 ASCII 文本风险
- `\section{\bititle{...}{...}}` 这类不安全双语标题写法

lint 会直接跳过 bibliography-like 文件或内容块，例如：

- `thebibliography`
- `\bibliography{...}`
- `\bibliographystyle{...}`
- `\printbibliography`

## 编译链

推荐先做预检：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py lint <workspace>
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --quick
```

如果不想手动串这些步骤，可以直接跑：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py run <arxiv-id-or-url>
```

默认编译链：

- 有参考文献时：`pdflatex -> bibtex -> pdflatex -> pdflatex`
- 没有参考文献时：至少 `pdflatex -> pdflatex`
- 如果仍有 rerun 提示，再补一遍 `pdflatex`
- 当编译目标是 `paper_note_bilingual.tex` 时，如果检测到原始主文档更新晚于入口文件，编译脚本会自动先刷新入口
- 也可以显式要求在编译前重生入口：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --refresh-entry
```

## 兼容性

- 如果当前 TeX 环境缺 `binhex.tex`，编译脚本会自动在工作区补一份兼容文件。
- 编译脚本会输出 `warning_summary`，只保留值得人工看的短警告摘要。
- 如果出现 fatal，编译脚本会额外输出 `fatal_kind` 和 `fatal_advice`，优先把错误归类到 “裸数学宏” 或 “moving-argument Unicode”。
- 当 fatal 看起来来自旧 `.aux` / 书签状态时，编译脚本会自动清理目标入口对应的 `.aux` 后重试一次。
- 视觉检查现在由独立命令负责：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py visual-check <workspace> --pdf paper_note_bilingual.pdf
```

- 视觉检查会在 `.paper_note_visual_check/` 下生成前几页预览图。
- `wrapfigure` / `wraptable` 在双语 inline 展开后是高风险环境；一旦预览图出现挤压、重叠或段落错位，优先回退到普通 `figure` / `table`。
