# scripts 代码总览

这组脚本是 `paper-note-skill` 的正式实现入口，目标很单一：把一篇 arXiv 论文整理成可编译、可检查的双语逐句阅读工作区，并通过统一 CLI 暴露出来。

如果只看一条主线，可以按下面这条链路理解：

1. `paper_note.py` 注册全部子命令，负责把顶层参数分发到 `commands/*`。
2. `commands/*` 只处理命令行边界，把参数转成 `core/*` 能直接消费的数据。
3. `core/*` 承担真实业务，包括抓取论文源码、生成工作区入口、lint、编译、诊断和视觉检查。
4. `assets/binhex.tex` 是兼容性兜底资产，只在系统 TeX 缺少 `binhex.tex` 时写进工作区。

## 目录分层

### `paper_note.py`

唯一正式 CLI 入口。

- 定义总描述 `COMMAND_DESCRIPTION`
- 用 `register_subcommand()` 统一注册子命令
- 在 `main()` 里解析参数，并调用各子命令的 `handler`

这个文件不直接做业务判断，也不自己拼装结果输出。

### `commands/`

命令层。每个文件基本都遵守同一套结构：

- `COMMAND_NAME`
- `COMMAND_DESCRIPTION`
- `configure_parser(parser)`
- `run_from_args(args) -> int`

这一层只做三件事：

- 声明参数
- 解析工作区路径、布尔开关、显式文件路径
- 调用 `core/*` 并通过 `core.output.emit_result()` 输出结果

不要把 LaTeX 处理、lint 规则、编译重试逻辑塞回这一层。

### `core/`

核心实现层。这里没有 argparse，也不负责用户文案风格，主要返回 dataclass 结果对象，供 `commands/*` 继续包装。

按职责可以再分成几组：

- 输入与工作区：`arxiv.py`、`workspace.py`、`source_clean.py`
- 入口生成：`entry.py`
- lint：`lint_parse.py`、`lint_rules.py`
- 构建：`build_plan.py`、`build_exec.py`、`build_report.py`
- 环境与渲染检查：`doctor.py`、`visual.py`
- 公共模型与输出：`models.py`、`output.py`
- 兼容性：`latex_compat.py`

## 端到端执行流

最完整的流程在 `commands/run.py` 里，顺序是固定的：

1. `core.arxiv.fetch_source_to_workspace()`
2. `core.entry.prepare_workspace()`
3. `core.build_exec.build_workspace(..., quick=True, refresh_entry=True, skip_lint=False)`
4. 如果 quick build 成功且没有 `--skip-full-build`，再执行
   `core.build_exec.build_workspace(..., quick=False, refresh_entry=False, skip_lint=True)`
5. full build 成功后，调用 `core.visual.run_visual_check()`

这里有两个细节值得记住：

- quick build 会先跑 lint，full build 则复用 quick build 的结果，不再重复 lint。
- `build_workspace()` 在编译目标正好是 `paper_note_bilingual.tex` 时，会检查原始主文档是否更新得更晚；如果是，就自动刷新入口文件。

## 工作区与生成产物

脚本默认把论文工作区放到 `core.workspace.DEFAULT_PAPER_ROOT` 指向的目录下。

默认解析顺序是：

- 显式 `--root`
- 进程环境变量 `PAPER_NOTE_OUTPUT_ROOT`
- `~/.paper-note-skill/config.yaml`
- 都没有时回退到仓库根目录下的 `paper/`

可以用：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py config
```

来交互式写入用户级默认输出目录。

一次完整运行后，工作区里最常见的新增或更新文件有：

- `paper_note_annotations.tex`
  由 `core.entry.refresh_generated_entry()` 从资产模板写入
- `paper_note_bilingual.tex`
  由 `core.entry.build_entry_text()` 基于主文档生成
- `*.paper-note-build.log`
  由 `core.build_exec.append_log()` 逐轮附加编译日志
- `.paper_note_visual_check/<pdf-stem>/page-*.png`
  由 `core.visual.render_preview_pages()` 生成的预览页
- `binhex.tex`
  只有系统缺失该 TeX 文件时才会落到工作区

## 结果对象和输出约定

脚本的返回边界很统一：

- `core.models` 里定义 dataclass，例如 `FetchResult`、`SetupResult`、`LintResult`、`BuildResult`
- `commands/*` 拿到这些对象后，再交给 `core.output.command_result()` 组装成 `CommandResult`
- `core.output.emit_result()` 负责最后输出成 `text` 或 `json`

这套分层让核心逻辑不必知道“终端怎么打印”，也让后续接别的前端时更容易复用。

## 退出码

`core.models.ExitCode` 定义了统一退出码：

- `0`: 成功
- `1`: 输入错误
- `2`: lint 失败
- `3`: build 失败
- `4`: 依赖缺失

命令层基本都遵守这个约定，只有具体 `status` 会随场景变化，比如 `prepared`、`compiled`、`quick_build_failed`、`missing_dependency`。

## 建议的阅读顺序

如果要维护这套脚本，建议按下面顺序读：

1. [commands.md](commands.md)
2. [core-modules.md](core-modules.md)
3. `paper_note.py`
4. `commands/run.py`
5. `core/build_exec.py`
6. `core/lint_rules.py`

这样先看到边界，再下钻到最复杂的执行链，不容易在一开始就被细节淹没。
