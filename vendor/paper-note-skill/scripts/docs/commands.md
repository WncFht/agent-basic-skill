# commands 层说明

这一层的目标不是实现业务，而是把 CLI 边界收干净。每个命令文件都负责参数定义、路径解析、异常转义和结果输出。

公共约定只有两条：

- 都支持 `--format text|json`，由 `core.output.add_format_argument()` 注入
- 都通过 `emit_result()` 输出，而不是直接 `print()` 业务内容

## 顶层入口：`paper_note.py`

`paper_note.py` 只做命令注册和分发。

- `build_parser()` 依次注册 `config`、`fetch`、`setup`、`lint`、`build`、`visual-check`、`run`、`doctor`
- `main()` 调 `args.handler(args)`，所以真正的逻辑入口都在 `commands/*`

这意味着要新增命令时，一般只需要两步：

1. 在 `commands/` 里新建一个遵循既有接口的文件
2. 在 `paper_note.py` 里补一段 `register_subcommand(...)`

## `config.py`

用途：查看或设置默认工作区根目录。

### 主要参数

- `--show`: 查看当前解析出的默认输出目录及来源
- `--set-root`: 非交互写入 `~/.paper-note-skill/config.yaml`
- `--clear`: 清空保存的默认输出目录

### 关键行为

- 默认直接进入交互式设置
- 默认输出目录解析顺序是 `--root` > `PAPER_NOTE_OUTPUT_ROOT` > `~/.paper-note-skill/config.yaml` > 仓库根 `paper/`
- 保存配置时会先规范化成绝对路径，并确保目录存在

## `fetch.py`

用途：抓取 arXiv 源码并初始化工作区目录。

### 主要参数

- `input`: arXiv ID、abs URL 或 pdf URL
- `--root`: 工作区根目录，默认是 `core.workspace.DEFAULT_PAPER_ROOT`
  它会按 `--root` > `PAPER_NOTE_OUTPUT_ROOT` > `~/.paper-note-skill/config.yaml` > 仓库根 `paper/` 的顺序解析
- `--version`: 显式指定版本，比如 `2` 或 `v2`
- `--keep-archive`: 是否保留下载后的 `source.tar`
- `--clean-source on|off`: 是否对提取出的 LaTeX 源码做清洗

### 调用链

1. `resolve_directory(..., create=True)`
2. `parse_toggle(args.clean_source, label="clean-source")`
3. `fetch_source_to_workspace(...)`

### 返回重点

- `workspace`
- `paper_id_with_version`
- `source_url`
- `archive_path`
- `preprocessed_tex_files`
- `removed_comment_lines`
- `collapsed_blank_lines`
- `binhex_status`

### 异常处理

- `RuntimeError` 视为依赖缺失，返回退出码 `4`
- 其他异常按输入错误处理，返回退出码 `1`

这里的 `RuntimeError` 主要来自 `requests` 缺失。

## `setup.py`

用途：在现有论文工作区里生成双语入口和共享宏文件。

### 主要参数

- `workspace`: 已存在的工作区目录
- `--force`: 已有生成文件时是否覆盖
- `--notes on|off`: 是否默认启用 `\pnote`
- `--main`: 显式指定顶层 TeX 文件

### 调用链

1. `resolve_existing_directory()`
2. 如有 `--main`，先 `resolve_workspace_file()`
3. `prepare_workspace(...)`

### 返回重点

- `main_tex`
- `annotation_support`
- `entry_files`
- `notes_enabled`
- `removed_generated_paths`
- `entry_path`
- `preamble_path`

### 特别说明

`setup` 输出里会把双语句子宏和 fallback 翻译宏一起报出来，这是给上层调用者一个稳定提示，不需要再反查 TeX 资产文件。

## `lint.py`

用途：在编译前检查批注和双语宏是否违反约束。

### 主要参数

- `workspace`
- `--tex`: 只检查某个 TeX 文件；不传则扫描整个工作区

### 调用链

1. `resolve_existing_directory()`
2. 如果传了 `--tex`，先 `resolve_workspace_file()`
3. `lint_workspace(workspace, tex_file=...)`
4. `format_issue()` 把 issue 变成稳定字符串

### 返回重点

- `checked_files`
- `issue_count`
- `issues`

### 退出规则

- 有 issue 时返回 `ExitCode.LINT_FAILED`
- 没有 issue 时返回 `ExitCode.SUCCESS`

这让 `build` 和 `run` 可以直接把 lint 当成前置门槛使用。

## `build.py`

用途：编译双语入口或显式指定的 TeX 文件，并汇总诊断信息。

### 主要参数

- `workspace`
- `--tex`: 显式编译哪个 TeX 文件
- `--quick`: 只跑 preflight LaTeX pass
- `--refresh-entry`: 编译前强制刷新 `paper_note_bilingual.tex`
- `--skip-lint`: 跳过 lint

### 调用链

1. `resolve_existing_directory()`
2. `build_workspace(...)`
3. 如果有 lint 结果，先转成字符串 issue 列表
4. 把每个 `BuildTargetResult` 经过 `target_payload()` 压平成输出字典

### 返回重点

- `targets`
- `entry_refresh`
- `lint_status`
- `lint_issue_count`
- `lint_issues`
- `results`

`results` 里的每个元素对应一个编译目标，包含 `pdf`、`log`、`compiler`、`warnings`、`fatal`、`status`。

## `visual_check.py`

用途：对 PDF 做轻量级视觉检查，并扫描源码里的高风险浮动体。

### 主要参数

- `workspace`
- `--pdf`: 显式 PDF 路径
- `--pages`: 渲染前几页，默认 `4`

### 调用链

1. `resolve_existing_directory()`
2. `resolve_pdf_path()`
3. `run_visual_check(...)`

### 返回重点

- `preview_dir`
- `rendered_pages`
- `risky_floats`
- `note`

### 默认路径推断

如果不传 `--pdf`，命令会：

1. 调 `detect_default_build_targets(workspace)`
2. 取第一个默认 TeX 目标
3. 再用 `detect_pdf_path()` 推断 PDF 名称

## `run.py`

用途：把 `fetch -> setup -> build -> visual-check` 串成一条完整工作流。

### 主要参数

- `input`
- `--root`
- `--version`
- `--notes on|off`
- `--skip-full-build`

### 固定流程

1. `fetch_source_to_workspace()`
2. `prepare_workspace(force=False, ...)`
3. `build_workspace(..., quick=True, refresh_entry=True, skip_lint=False)`
4. quick build 失败则立刻返回
5. 如果设置了 `--skip-full-build`，在 quick build 成功后就结束
6. 否则继续 `build_workspace(..., quick=False, refresh_entry=False, skip_lint=True)`
7. full build 成功后执行 `run_visual_check()`

### 为什么 quick 和 full 分两次

这里不是重复编译，而是刻意把“尽早失败”和“完整产物”拆开：

- quick build 负责快速暴露 lint 和第一轮 LaTeX fatal
- full build 只在 quick build 通过后才运行，避免在坏状态下继续堆日志

### `summarize_build()`

`run.py` 没有把完整 `BuildResult` 原样透出，而是压缩成一个更短的摘要，便于串行工作流输出。重点保留：

- `status`
- `exit_code`
- `targets`
- `lint_status`
- `lint_issue_count`
- `entry_refresh`
- `pdf`
- `log`
- `warnings`

## `doctor.py`

用途：检查本机依赖是否齐全，并可选验证工作区是否具备最小结构。

### 主要参数

- `--workspace`

### 调用链

1. 如传 `--workspace`，先 `resolve_existing_directory()`
2. `run_doctor(workspace)`

### 状态判定

- 工作区无效：`workspace_invalid`，退出码 `1`
- 缺依赖：`missing_dependency`，退出码 `4`
- 其他都通过：`ok`，退出码 `0`

### 检查项

- 命令：`pdflatex`、`bibtex`、`pdftoppm`、`kpsewhich`
- Python 模块：`requests`
- 可选工作区结构：能否检测到主 TeX、是否已有入口和宏文件

## 维护建议

要改命令层时，优先守住这几个边界：

- 新逻辑如果不依赖 argparse，就放进 `core/*`
- 新输出字段先定义清楚语义，再决定是否 text/json 都暴露
- 不要在 `commands/*` 里直接 `print()` 中间日志
- 不要在 `run.py` 里复制 `build_exec.py` 的内部判断

命令层越薄，后面排查问题时越容易定位到底是参数边界的问题，还是核心逻辑的问题。
