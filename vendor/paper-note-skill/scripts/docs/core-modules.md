# core 模块说明

`core/` 是这套脚本的业务中心。命令层只负责把参数送进来，真正决定行为的是这里的模块。

整套设计有两个明显特点：

- 模块之间尽量按职责切开，不把 CLI 解析掺进业务函数
- 大多数函数返回 dataclass，而不是松散 tuple 或直接打印文本

## `models.py`

这里集中定义了结果对象和退出码。

### 关键类型

- `ExitCode`
- `CommandResult`
- `FetchResult`
- `GeneratedEntryResult`
- `SetupResult`
- `LintIssue`
- `LintResult`
- `BuildPlan`
- `BuildPassResult`
- `FatalDiagnosis`
- `VisualCheckResult`
- `BuildTargetResult`
- `BuildResult`
- `ToolCheck`
- `DoctorResult`

这些对象把跨模块边界稳定下来。比如 `build_exec.py` 不需要关心命令层要怎么打印，只需要返回 `BuildResult`。

## `output.py`

输出适配层，负责把 dataclass 和路径对象转换成 CLI 可打印结构。

### 关键函数

- `add_format_argument()`
- `command_result()`
- `error_result()`
- `emit_result()`

### 实现要点

- `_to_jsonable()` 会把 `Path`、`IntEnum`、dataclass、容器递归转成 JSON 友好的值
- `emit_result(..., "json")` 用 `json.dumps(..., ensure_ascii=False, indent=2)`
- 文本模式下，列表字段会展开成 `key:` 加若干 `- item`

如果以后要给这套脚本接 Web UI 或 MCP，这个文件是最先会被复用或替换的一层。

## `workspace.py`

工作区解析和探测逻辑都在这里。

### 关键常量

- `DEFAULT_PAPER_ROOT`
- `DEFAULT_PAPER_ROOT_ENV_VAR`
- `PREAMBLE_FILE_NAME`
- `ENTRY_FILE_NAME`
- `STALE_GENERATED_FILE_NAMES`
- `STALE_GENERATED_DIR_NAMES`

### 关键函数

- `resolve_existing_directory()`
- `resolve_directory()`
- `resolve_workspace_file()`
- `detect_main_tex()`
- `detect_existing_generated_paths()`
- `remove_generated_paths()`
- `needs_entry_refresh()`
- `detect_compiler()`
- `validate_workspace()`

### 关键行为

`detect_main_tex()` 的优先级很明确：

1. 先看 `00README.json` 里的 `sources[*].usage == "toplevel"`
2. 再看工作区根目录下是否有 `main.tex`
3. 最后在全部 `*.tex` 里找同时包含 `\documentclass` 和 `\begin{document}` 的文件

这让脚本既能吃 arXiv 常见结构，也能容忍作者自己整理过的目录。

`DEFAULT_PAPER_ROOT` 的默认解析顺序是：

1. 先看进程环境变量 `PAPER_NOTE_OUTPUT_ROOT`
2. 再看 `~/.paper-note-skill/config.yaml`
3. 都没有时回退到仓库根目录下的 `paper/`

显式传入 `--root` 时，命令行参数仍然优先。

## `user_config.py`

用户级配置存储和默认输出目录来源解析都在这里。

### 关键常量

- `CONFIG_DIR_NAME`
- `CONFIG_FILE_NAME`
- `OUTPUT_ROOT_ENV_VAR`
- `OUTPUT_ROOT_KEY`

### 关键函数

- `config_dir_path()`
- `config_path()`
- `load_config()`
- `save_config()`
- `normalize_output_root()`
- `resolve_output_root()`

### 关键行为

- 配置文件固定在 `~/.paper-note-skill/config.yaml`
- 只存一层简单键值，目前主要字段是 `output_root`
- `resolve_output_root()` 会返回路径和来源，便于 `config` 命令展示当前是 env、config 还是 fallback

## `arxiv.py`

负责把用户输入转成论文源码工作区。

### 关键函数

- `normalize_version()`
- `extract_arxiv_id()`
- `fetch_arxiv_abs_html()`
- `parse_latest_version()`
- `parse_arxiv_title()`
- `build_workspace_name()`
- `ensure_workspace()`
- `safe_extract_tar()`
- `fetch_metadata()`
- `fetch_source_to_workspace()`

### 关键行为

- 支持直接从原始输入或 URL path 提取 arXiv ID
- 如果用户没显式指定版本，会先抓 abs 页，再推断最新版本
- 工作区目录名默认是 `arxiv_id + 标题 slug`
- 若目标目录不存在但根目录下恰好有一个同 arXiv ID 前缀的旧目录，会直接复用
- `safe_extract_tar()` 会过滤绝对路径和带 `..` 的成员，避免 tar 路径穿越

`fetch_source_to_workspace()` 是最完整的入口，它还会顺手调用：

- `preprocess_latex_sources()` 清理源码
- `ensure_binhex_compat()` 处理缺失的 `binhex.tex`

## `source_clean.py`

负责对下载下来的 `*.tex` 做轻量清洗。

### 做的事

- 删除整行注释，但保留 `% !TeX` 这类指令行
- 折叠多余空行
- 数学环境里不主动压空行
- `verbatim`、`lstlisting`、`minted`、`filecontents` 这类受保护环境不改

### 为什么单独拆出来

这一步和“论文批注规则”无关，只是下载后预处理。如果把它混进 `arxiv.py` 或 `entry.py`，后面定位问题会很难分清是下载阶段改坏了，还是入口生成阶段改坏了。

## `entry.py`

负责生成或刷新 `paper_note_bilingual.tex` 以及共享宏文件 `paper_note_annotations.tex`。

### 关键函数

- `parse_toggle()`
- `read_existing_notes_enabled()`
- `sanitize_main_text()`
- `ensure_annotation_preamble()`
- `ensure_cjk_wrapper()`
- `maybe_reset_footnotes()`
- `build_entry_text()`
- `refresh_generated_entry()`
- `prepare_workspace()`

### 生成逻辑

`build_entry_text()` 的顺序是固定的：

1. `sanitize_main_text()` 删除旧的自动生成标记
2. `ensure_annotation_preamble()` 注入 `\input{paper_note_annotations.tex}` 和 notes 开关
3. `ensure_cjk_wrapper()` 确保正文包在 `CJK*` 环境里
4. `maybe_reset_footnotes()` 在 `\maketitle` 后恢复脚注编号样式

### 覆盖与复用策略

- 若 `notes_enabled` 没显式传入，`refresh_generated_entry()` 会从已有入口里推断 `\annotnotestrue` 还是 `\annotnotesfalse`
- `prepare_workspace()` 默认拒绝覆盖已有生成文件，除非用户传 `--force`
- `--force` 时不仅会重写当前入口，还会清理旧名字的历史产物和目录

## `lint_parse.py`

这是纯解析工具层，为 lint 规则提供字符串级能力。

### 关键函数

- `strip_comments()`
- `parse_braced_group()`
- `parse_command_calls()`
- `find_annsummary_ranges()`
- `find_unmatched_dollars()`
- `find_bare_math_macros()`
- `contains_non_ascii()`
- `strip_tex_commands()`
- `parse_first_optional_arg()`

### 适合放这里的逻辑

- “怎么在字符串里找到某个 TeX 命令的参数”
- “怎么判断一个数学宏是不是裸奔”
- “怎么找未闭合的 `$`”

### 不适合放这里的逻辑

- “某个命令为什么在 paper-note 语义里是非法的”
- “发现了问题之后应返回什么中文提示”

后者属于 `lint_rules.py`。

## `lint_rules.py`

这里定义的是 paper-note 领域规则，而不是通用 TeX 语法规则。

### 规则覆盖面

- 废弃命令：`\annnote`、`\annote`
- `annsummary` 起止不配对
- 未配对 `$` / `$$`
- 句子功能宏内部嵌入 `\footnote` 或 `\footnotemark`
- `\zhtrans`、`\bgsent`、`\zhbgsent` 等 inline 文本宏里的裸数学宏
- `\pnote` 第二参数里的裸数学宏
- 旧三参数 `\pnote`
- `\title`、`\section` 等 moving argument 里的非 ASCII 文本或不安全双语标题写法

### 关键函数

- `lint_moving_arguments()`
- `is_bibliography_like_tex()`
- `lint_file()`
- `collect_tex_files()`
- `lint_workspace()`
- `format_issue()`

### 设计取向

`lint_workspace()` 会跳过：

- `paper_note_annotations.tex`
- `paper_note_bilingual.tex`
- 历史生成目录 `paper_note_zh`
- bibliography-like 文件

原因很直接：lint 主要是拦人工编辑的原稿，不是反过来挑脚本自己生成文件的刺。

## `build_plan.py`

负责把“该编什么、往哪写日志、是否需要 bibtex”这些前置信息整理好。

### 关键函数

- `needs_bibtex()`
- `detect_pdf_path()`
- `detect_log_path()`
- `cleanup_stale_aux_files()`
- `detect_default_build_targets()`
- `make_build_plan()`

### 关键行为

- 默认优先编译 `paper_note_bilingual.tex`
- 若入口不存在，就退回 `detect_main_tex(workspace)`
- 日志固定写成 `<stem>.paper-note-build.log`
- 编译前会清理 `.toc`、`.lof`、`.lot`、`.out`、`.loc` 这些陈旧辅助文件

## `build_exec.py`

这是最核心、也最复杂的模块，负责执行真实编译。

### 关键函数

- `append_log()`
- `run_command()`
- `compile_target()`
- `build_workspace()`

### `compile_target()` 在做什么

1. 读取编译器配置 `detect_compiler()`
2. 判断是否需要 `bibtex`
3. 清空目标 log 文件
4. 清理部分辅助文件
5. 调 `ensure_binhex_compat()`
6. 检查编译器是否合法，且命令是否在 PATH 里
7. 执行 `pdflatex` / `bibtex` 编译序列
8. 根据输出提取 warning 和 fatal
9. 必要时做一次 `aux` 清理后重试

### 编译序列

有参考文献且不是 quick build 时：

- `latex-preflight`
- `bibtex`
- `latex-pass-2`
- `latex-pass-3`
- 如有 rerun 提示，再跑 `latex-pass-4`

没有参考文献时：

- `latex-preflight`
- `latex-pass-2`
- 如有 rerun 提示，再跑 `latex-pass-3`

quick build 只跑第一轮 `latex-preflight`。

### 自动恢复逻辑

如果 `diagnose_fatal()` 认为 fatal 很像 Unicode `.aux` / 书签残留问题，就会：

1. 清理 `.aux`
2. 记录一条 `paper-note-recovery` 日志
3. 再完整重试一次编译序列

这段逻辑能避免“主文档已经改对了，但旧辅助文件还在拖后腿”的假失败。

### `build_workspace()` 额外做的事

- 先根据 `make_build_plan()` 生成计划
- 编译目标如果是 `paper_note_bilingual.tex`，会在需要时自动刷新入口
- 如未跳过 lint，则先执行 `lint_workspace()`
- 最终把多目标编译结果聚合成 `BuildResult`

## `build_report.py`

负责把原始 LaTeX 输出压成短诊断信息。

### 关键函数

- `summarize_warnings()`
- `summarize_final_warnings()`
- `summarize_quick_warnings()`
- `extract_fatal_summary()`
- `diagnose_fatal()`
- `should_rerun_latex()`

### 当前重点识别的 fatal

- `missing-dollar`
- `unicode-moving-argument`
- 其他统称 `generic`

`unicode-moving-argument` 这一类还会附带一组明确建议，例如优先改成 `\bipapertitle`、`\bisec` 之类的安全双语标题宏。

## `doctor.py`

环境自检模块。

### 检查项

- 外部命令：`pdflatex`、`bibtex`、`pdftoppm`、`kpsewhich`
- Python 模块：`requests`
- 可选工作区验证：`validate_workspace()`

### 使用场景

- 新机器第一次跑这套脚本
- build 报错，但还不确定是环境问题还是论文问题
- 想在外层流程里先做依赖预检

## `latex_compat.py`

只做一件事：保证 `binhex.tex` 可用。

### 逻辑顺序

1. 工作区里已经有 `binhex.tex`，返回 `"workspace"`
2. 系统 `kpsewhich binhex.tex` 能找到，返回 `"system"`
3. 否则把 `assets/binhex.tex` 写到工作区，返回 `"created"`

这一步很小，但把兼容性兜底拆成独立模块之后，编译链和抓取链都能复用。

## `visual.py`

负责 PDF 预览渲染和高风险浮动体扫描。

### 关键函数

- `scan_risky_floats()`
- `render_preview_pages()`
- `run_visual_check()`

### 当前检查内容

- 扫描所有 `*.tex`，找 `wrapfigure` / `wraptable`
- 如果系统有 `pdftoppm`，渲染前若干页 PNG 预览
- 根据浮动体命中和渲染结果给出 `ok` 或 `needs_review`

这里的设计很克制。它不是做复杂版面分析，而是给出一个便宜但有用的信号，让人尽快知道双语 inline 展开后有没有高风险布局。

## 维护时最值得注意的边界

改 `core/` 时，建议一直守住下面几条：

- 参数解析放在 `commands/*`，不要回流到 `core/*`
- 能返回 dataclass 就别返回匿名 dict
- `build_exec.py` 负责“怎么编”，`build_report.py` 负责“怎么解释失败”
- `lint_parse.py` 负责“怎么找”，`lint_rules.py` 负责“为什么错”
- `workspace.py` 负责探测和路径规则，不要在别的模块里重新发明一套主文档检测逻辑

这几个边界一旦混起来，后续再加命令、换输出介质或扩展 lint 规则时，改动面会很快失控。
