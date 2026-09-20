# Paper Note Scripts 重构设计

## 结论

这次重构不再把 `scripts/` 当成一组可以各自长大的独立脚本，而是把它收成一个小型工具链：

- 只保留一个正式入口
- 命令层只负责参数解析和输出
- 业务逻辑全部下沉到 `core/`
- 模板资产从 Python 字符串里拿出来
- 不再兼容旧命令名，也不再保留旧脚本壳

重构完成后，`paper-note-skill` 的公共接口应该只有一套：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py <subcommand> ...
```

## 为什么要重构

当前代码能用，但组织方式已经不适合继续加功能。问题不在某一个函数，而在职责边界。

### 现在的主要问题

1. `build_paper_pdf.py` 过重  
   它同时承担 CLI、目标选择、entry 刷新、lint、编译执行、fatal 诊断、visual check 汇总。

2. `setup_paper_workspace.py` 过重  
   它同时放了大段 LaTeX 模板、workspace 检测、入口生成、CJK 包裹、脚注恢复和生成文件管理。

3. `fetch_arxiv_source.py` 耦合过深  
   arXiv 解析、下载、安全解压、源码预清洗绑在一起，后面很难单独改其中一段。

4. `lint_annotations.py` 已经不是“脚本”  
   它本质上是一个领域规则引擎，但现在还混着命令行入口、输出格式和规则常量。

5. `run_paper_note_pipeline.py` 是编排脚本，不该再带业务  
   它应该只负责编排顺序，不应该自己再维护 lint/build 的细节。

6. `paper_note_cli.py` 只是分发器，不是完整架构  
   现在看起来像统一入口，实际上每个子命令内部还是一个大脚本。

7. 模板资产放错了位置  
   `DEFAULT_PREAMBLE` 这种长模板不该放在 Python 源码里，应该是独立资产文件。

8. 输出协议不统一  
   有的脚本直接 `print`，有的返回 dataclass，有的支持 `--json`，有的不支持。

9. 常量和约定散落在多个文件  
   比如生成文件名、stale 文件名、默认入口名、主文档检测逻辑，都没有单一来源。

### 当前状态补充

这里还有三件现状需要先说清，不然后面的目标设计容易写飘。

1. `paper_note_cli.py` 已经做了“统一入口”的第一步  
   但它只是把各脚本的 `configure_parser` / `run_from_args` 拼到一个 `argparse` 子命令树里，内部职责并没有真正拆开。

2. `latex_compat.py` 和 `assets/binhex.tex` 已经说明了一条可行路径  
   也就是“薄脚本 + 小核心模块 + 显式资产文件”。这证明方向不是凭空想象，只是现在还只拆出了一小块，`paper_note_annotations.tex` 这类大模板还没跟上。

3. 现有对外文档仍然暴露旧命令面  
   `SKILL.md`、`references/workflow.md`、`references/latex-and-lint.md` 现在都还在教人跑 `paper_note_cli.py`。所以这次重构如果真的切公共接口，不能只改代码，必须把文档一起切过去。

## 重构目标

这次重构只做一件事：把这套能力整理成一套清楚、稳定、能继续长的工具链。

目标如下：

- 提供唯一正式入口 `paper_note.py`
- 把命令层和核心逻辑彻底拆开
- 删除旧脚本兼容层
- 让每个文件只负责一类事情
- 统一 text/json 输出和 exit code
- 把 LaTeX 模板、兼容文件这类资产移出 Python
- 让后续新增命令或规则时，落点自然，不需要再改大脚本

## 非目标

这次设计里，不把下面这些事情混进来：

- 不把 `scripts/` 挪到仓库外面
- 不重写现有业务规则本身，比如 `\pnote`、双语 inline、visual check 的判断标准
- 不为了“更工程化”把模块拆得过细

## 目标目录结构

重构后的 `scripts/` 应该长这样：

```text
scripts/
  paper_note.py

  commands/
    __init__.py
    fetch.py
    setup.py
    lint.py
    build.py
    visual_check.py
    run.py
    doctor.py

  core/
    __init__.py
    models.py
    output.py
    workspace.py
    arxiv.py
    source_clean.py
    entry.py
    lint_parse.py
    lint_rules.py
    build_plan.py
    build_exec.py
    build_report.py
    visual.py
    doctor.py
    latex_compat.py

  assets/
    paper_note_annotations.tex
    binhex.tex
```

旧的这些文件在目标结构里应当删除：

- `fetch_arxiv_source.py`
- `setup_paper_workspace.py`
- `lint_annotations.py`
- `build_paper_pdf.py`
- `visual_check_pdf.py`
- `run_paper_note_pipeline.py`
- `paper_note_cli.py`
- `cli_common.py`

## 公共命令面

新的公共接口只保留一个入口：

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py <subcommand> ...
```

建议保留的子命令如下。

### `fetch`

用途：拉取 arXiv LaTeX 源码并初始化工作区目录。

建议参数：

- `fetch <arxiv-id-or-url>`
- `--root <dir>`
- `--version <n>`
- `--keep-archive`
- `--clean-source on|off`

### `setup`

用途：在现有论文工作区里生成双语批注入口和共享宏文件。

建议参数：

- `setup <workspace>`
- `--force`
- `--notes on|off`
- `--main <tex-file>`

### `lint`

用途：检查批注规则、标题安全、数学宏使用和脚注约束。

建议参数：

- `lint <workspace>`
- `--tex <tex-file>`
- `--format text|json`

### `build`

用途：编译双语入口，必要时自动刷新 entry，并给出结构化诊断。

建议参数：

- `build <workspace>`
- `--tex <tex-file>`
- `--quick`
- `--refresh-entry`
- `--skip-lint`
- `--format text|json`

### `visual-check`

用途：对编译结果做版面风险检查，并导出预览图。

建议参数：

- `visual-check <workspace>`
- `--pdf <file>`
- `--pages <n>`
- `--format text|json`

### `run`

用途：串完整链路，作为默认工作流入口。

建议参数：

- `run <arxiv-id-or-url>`
- `--root <dir>`
- `--notes on|off`
- `--skip-full-build`
- `--format text|json`

### `doctor`

用途：检查本机依赖和环境前提，提前暴露工具链问题。

建议参数：

- `doctor`
- `--workspace <dir>`
- `--format text|json`

`doctor` 不是当前功能的硬前提，但它很有必要。现在很多失败其实不是论文本身有问题，而是本机缺 `pdflatex`、`bibtex`、`pdftoppm`、`kpsewhich`，或者 `requests` 没装好。把这些检查单独收成一个命令，比等到 `build` 里半路炸掉要干净得多。

## 各目录职责

### 顶层入口

#### `paper_note.py`

这是唯一正式入口。

职责只有三件事：

- 注册全部子命令
- 解析顶层参数
- 把控制权转交给 `commands/*`

它不应该直接 import `core` 里的业务函数做流程判断，更不应该自己打印业务结果。

### `commands/`

这一层只负责命令行边界。

每个文件都应该遵守同一套结构：

1. `configure_parser(parser)`
2. `run_from_args(args) -> int`
3. 需要时调用 `core/*`

它不应该做这些事：

- 读写 LaTeX 内容
- 执行 lint 规则
- 直接跑编译细节
- 拼接复杂业务状态

#### `commands/fetch.py`

- 解析 arXiv 输入
- 调 `core.arxiv`
- 输出 workspace 路径、主文件、版本、标题 slug

#### `commands/setup.py`

- 解析 workspace、`--notes`、`--force`
- 调 `core.workspace` 和 `core.entry`
- 输出主入口、生成文件、notes 状态

#### `commands/lint.py`

- 解析目标 tex 和输出格式
- 调 `core.lint_parse` / `core.lint_rules`
- 输出 issue 列表和汇总状态

#### `commands/build.py`

- 解析 build 参数
- 先根据参数生成 plan
- 调 `core.build_exec`
- 再由 `core.build_report` 生成 warning/fatal 摘要

#### `commands/visual_check.py`

- 定位 PDF
- 调 `core.visual`
- 输出风险项和预览目录

#### `commands/run.py`

- 只编排
- 顺序固定为 `fetch -> setup -> build -> visual-check`
- 默认由 `build` 自己决定是否先做 lint

这里有一个明确原则：`run` 不再单独维护一套 lint/build 细节。它只是串命令，不复制业务逻辑。

#### `commands/doctor.py`

- 检查 Python 依赖
- 检查 `pdflatex` / `bibtex` / `pdftoppm` / `kpsewhich`
- 可选检查 workspace 是否具备最小结构

### `core/`

这一层是真正的工具库。这里不直接面向用户，不做 CLI 文案，只返回结果对象。

#### `core/models.py`

统一放结果对象和状态对象，避免 tuple 到处飞。

建议至少有这些 dataclass：

- `FetchResult`
- `SetupResult`
- `LintIssue`
- `LintResult`
- `BuildPlan`
- `BuildPassResult`
- `BuildResult`
- `FatalDiagnosis`
- `VisualCheckResult`
- `DoctorResult`

#### `core/output.py`

统一 text/json 输出协议。

职责包括：

- `emit_text_result(...)`
- `emit_json_result(...)`
- 常用字段格式化
- exit code 常量

这样 `commands/*` 不需要各自维护输出细节。

#### `core/workspace.py`

负责 workspace 级别的约定。

包括：

- 检测主文档
- 统一生成文件名
- 统一 stale 文件名
- 判断 entry 是否需要刷新
- 校验 workspace 最小结构

这部分应该成为所有命令共享的单一事实来源。

#### `core/arxiv.py`

负责 arXiv 相关逻辑。

包括：

- 解析 arXiv id 和 URL
- 解析版本号
- 拉 metadata
- 生成目录 slug
- 下载源码压缩包
- 安全解压

#### `core/source_clean.py`

负责源码预清洗。

包括：

- 去注释
- 合并无意义空行
- 做最小限度的文本归一化

把这部分从 `fetch` 里拆出来后，后续如果要改“下载时保留原样”还是“下载后默认清洗”，不会牵动 arXiv 逻辑。

#### `core/entry.py`

负责双语入口生成。

包括：

- 加载 `assets/paper_note_annotations.tex`
- 注入共享宏
- 生成 `paper_note_bilingual.tex`
- 处理 `\annotnotestrue` / `\annotnotesfalse`
- 处理 `CJK*` 包裹
- 恢复脚注编号

这里是 setup 的核心。

`DEFAULT_PREAMBLE` 不再保留在 Python 里，而是迁到 `assets/paper_note_annotations.tex`。

#### `core/lint_parse.py`

负责 TeX 文本解析辅助。

包括：

- 去 comment 的安全处理
- 识别 command 调用
- 解析 braced group
- 定位行号和上下文

它不判断规则，只提供结构化输入。

#### `core/lint_rules.py`

负责 paper-note 的领域规则。

至少包括：

- 禁止旧 `\annnote`
- 禁止旧三参数 `\pnote`
- moving argument 中文风险
- 不安全双语标题写法
- 裸数学宏
- `annsummary` 闭合检查
- 句子宏内 `\footnote` / `\footnotemark`

以后再加 lint 规则，只动这个文件，不再碰 CLI 和 parser。

#### `core/build_plan.py`

负责把“用户想编什么”转成“真正要执行什么”。

包括：

- 选择目标 tex
- 判断是否 quick/full
- 判断是否要 refresh entry
- 判断是否要跑 bibtex
- 生成编译 pass 列表

#### `core/build_exec.py`

负责真正执行编译。

包括：

- 跑 `pdflatex` / `xelatex` / `lualatex`
- 跑 `bibtex`
- 清理 aux 类文件
- 调 `latex_compat`
- 保存 build log

这里不负责把错误解释成用户文案。

#### `core/build_report.py`

负责解释编译结果。

包括：

- warning 摘要
- fatal 分类
- aux 重试判定
- rerun 提示
- 给 `build` 命令准备结构化输出

把执行和诊断拆开后，编译器细节和用户提示就不会继续缠在一起。

#### `core/visual.py`

负责编译后的版面检查。

包括：

- 扫 `wrapfigure` / `wraptable`
- 调 `pdftoppm` 生成预览图
- 输出风险列表
- 输出预览目录路径

#### `core/doctor.py`

负责环境检查。

包括：

- 查外部命令是否可用
- 查 Python 依赖是否可导入
- 查资产文件是否齐全
- 可选检查 workspace 最小结构

#### `core/latex_compat.py`

继续只做一件事：确保 `binhex.tex` 可用。

这个模块不该扩张成“通用 LaTeX 兼容层”，否则边界会再次变糊。

### `assets/`

资产层现在应该显式存在，而不是藏在 Python 字符串里。

建议放两个文件：

- `assets/paper_note_annotations.tex`
- `assets/binhex.tex`

这样有两个好处：

1. LaTeX 宏模板可以单独读、单独 review、单独 diff
2. Python 代码终于只负责“加载和注入模板”，不再自己承载整份模板正文

## 现状到目标的映射

为了避免实现时一边拆一边重新发明边界，旧文件和目标落点最好先一一对应。

| 现状文件 | 目标落点 | 说明 |
| --- | --- | --- |
| `paper_note_cli.py` | `paper_note.py` | 继续只做顶层参数和子命令注册，但不再直接把旧脚本当公共接口。 |
| `fetch_arxiv_source.py` | `commands/fetch.py` + `core/arxiv.py` + `core/source_clean.py` | 把 arXiv 解析、下载、安全解压、源码预清洗拆开。 |
| `setup_paper_workspace.py` | `commands/setup.py` + `core/workspace.py` + `core/entry.py` + `assets/paper_note_annotations.tex` | 当前最重的模板和入口生成逻辑主要落在这里。 |
| `lint_annotations.py` | `commands/lint.py` + `core/lint_parse.py` + `core/lint_rules.py` + `core/models.py` | parser、规则和 CLI 输出分层。 |
| `build_paper_pdf.py` | `commands/build.py` + `core/build_plan.py` + `core/build_exec.py` + `core/build_report.py` | 把“决定怎么编”“真正去编”“如何解释失败”拆开。 |
| `visual_check_pdf.py` | `commands/visual_check.py` + `core/visual.py` | 保留 float 扫描和预览渲染，但统一输出协议。 |
| `run_paper_note_pipeline.py` | `commands/run.py` | 只保留编排，不再自带 lint/build 业务细节。 |
| `cli_common.py` | `core/output.py` + `core/workspace.py` | 输出协议归 `output`，路径和 workspace 约定归 `workspace`。 |
| `latex_compat.py` | `core/latex_compat.py` | 这是最接近“原地迁移”的一个模块，基本只需要换落点。 |

这个映射的目的不是把每个旧文件机械地对半拆，而是先把未来每类职责的唯一归属定下来。只要归属先稳住，实现时就不会反复把逻辑塞回大脚本。

## 统一设计约束

### 1. 旧命令不再兼容

这是这次设计里最明确的边界。

下面这些调用方式在目标结构里都应删除：

```bash
python .../fetch_arxiv_source.py ...
python .../setup_paper_workspace.py ...
python .../lint_annotations.py ...
python .../build_paper_pdf.py ...
python .../visual_check_pdf.py ...
python .../run_paper_note_pipeline.py ...
python .../paper_note_cli.py ...
```

保留这些旧名字只会拖着架构一起脏下去。既然已经决定重设计，就应该让公共接口干净下来。

### 2. core 层不直接 `print`

`core/*` 只能返回对象，不能直接输出终端文本。

这样做的好处是：

- CLI 输出容易统一
- 后面如果要给 agent、UI 或 API 复用，不用再拆 print
- 测试和日志也更好接

### 3. 每个命令只负责一层

- `fetch` 只负责拉源码
- `setup` 只负责生成入口
- `lint` 只负责规则检查
- `build` 只负责编译和诊断
- `visual-check` 只负责版面检查
- `run` 只负责编排

如果一个命令开始“顺手”承担别的事情，后面很快又会回到现在这种大脚本状态。

### 4. 统一输出协议

所有命令默认都支持：

- `--format text`
- `--format json`

默认文本输出给人看，JSON 输出给 agent 或脚本接。

### 5. 统一 exit code

建议保留稳定语义：

- `0`: 成功
- `1`: 输入错误或 workspace 错误
- `2`: lint 失败
- `3`: build 失败
- `4`: 依赖缺失或环境不满足

这样后面不管是 shell、CI 还是 agent，都能稳定判断结果。

## 输出契约

光说“支持 text/json”还不够，最好把最小输出契约也定下来。

### 文本输出

- 仍然保留现在这种适合人在终端扫读的 `key: value` 风格
- 但字段语义要和 JSON 一致，不能出现 text 模式有结论、json 模式没字段，或者反过来

### JSON 输出

每个子命令的 JSON 至少应带这些公共字段：

- `command`
- `status`
- `exit_code`

按命令不同再补专属字段，例如：

- `workspace`
- `tex`
- `pdf`
- `log`
- `issues`
- `warnings`
- `advice`
- `preview_dir`

这里最重要的不是字段数量，而是同一命令的成功态和失败态都要保持稳定 shape。后面无论是 shell、agent 还是可能出现的 Web UI，接的都是这套结构，而不是 CLI 上一时顺手 `print` 出来的文本。

## 建议的主流程

### 标准交互

#### 拉源码

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py fetch 2501.01234
```

#### 初始化

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py setup <workspace>
```

#### 预检

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py lint <workspace>
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace> --quick
```

#### 正式编译

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py build <workspace>
```

#### 一键跑完整链路

```bash
python writing-skill/paper-note-skill/scripts/paper_note.py run 2501.01234
```

### 内部调用关系

```text
paper_note.py
  -> commands/*
      -> core/*
          -> assets/*
```

更具体一点：

```text
run
  -> arxiv.fetch_source(...)
  -> entry.prepare_workspace(...)
  -> build.execute(...)
  -> visual.check(...)

build
  -> workspace.detect_main_tex(...)
  -> build_plan.make_plan(...)
  -> build_exec.run_plan(...)
  -> build_report.summarize(...)
```

## 迁移顺序

虽然这份文档主要是目标设计，但实现时最好按下面顺序走。

### 第一步：先定公共接口

先把 `paper_note.py`、`commands/*`、`core/output.py`、`core/models.py` 立起来。

原因很简单：公共接口不先稳住，后面每拆一个模块，外部调用方式都可能继续变。

### 第二步：先拆 `setup` 和 `build`

这两个文件现在最重，也最影响后面的结构。

优先做：

- 把模板移到 `assets/`
- 把 entry 逻辑移到 `core/entry.py`
- 把 build 拆成 plan / exec / report

### 第三步：再拆 `lint`

把 parser 和 rules 分开。

这一步之后，lint 规则新增和维护就会轻很多。

### 第四步：最后拆 `fetch` 和 `run`

`fetch` 的拆法已经很清楚，`run` 也只剩编排工作，放在后面改风险最低。

### 第五步：删除旧文件

等新入口跑通后，直接删旧脚本，不留壳。

这一步不能拖。壳留久了，后面总有人继续从旧路径长代码。

## 文档联动

公共接口从 `paper_note_cli.py` 切到 `paper_note.py` 之后，下面这些文件应当在同一轮迁移里一起更新：

- `writing-skill/paper-note-skill/SKILL.md`
- `writing-skill/paper-note-skill/references/workflow.md`
- `writing-skill/paper-note-skill/references/latex-and-lint.md`

`annotation-rules.md`、`translation-format.md`、`section-guidance.md` 这几份更偏内容规则，通常不需要因为脚本重构而大改；但如果里面出现了旧命令示例，也要顺手清掉。

这里的原则很简单：不要出现“新入口已经上线，但文档还在教人跑旧入口”的过渡状态。对于这种 skill 来说，文档本身就是接口的一部分。

## 完成标准

只有同时满足下面三组条件，这次重构才算真的完成。

### 代码层

- 公共入口只剩 `paper_note.py`
- `commands/*` 与 `core/*` 的分层已经落地
- `paper_note_annotations.tex` 已经成为显式资产文件
- 旧脚本和 `cli_common.py` 已删除，不留兼容壳

### 文档层

- `SKILL.md`、`workflow.md`、`latex-and-lint.md` 已全部改成新入口
- 仓库内不再有面对用户的旧命令示例

### 行为层

- 每个子命令都能独立 `--help`
- text/json 输出语义一致
- exit code 语义稳定
- 至少有一条真实 workspace 路径完成 smoke test

## 最小验证矩阵

后面真正实施时，至少要跑下面这组验证。

| 检查项 | 命令或动作 | 预期结果 |
| --- | --- | --- |
| 顶层帮助 | `python .../paper_note.py --help` | 能看到全部正式子命令。 |
| 子命令帮助 | `python .../paper_note.py <subcommand> --help` | 每个子命令参数完整且无旧兼容参数残留。 |
| 环境预检 | `python .../paper_note.py doctor --format json` | 能稳定返回依赖检查结果。 |
| 初始化 | `python .../paper_note.py setup <workspace>` | 生成 `paper_note_annotations.tex` 和 `paper_note_bilingual.tex`。 |
| 规则预检 | `python .../paper_note.py lint <workspace> --format json` | 成功时返回稳定空 issue 结构，失败时返回 issue 列表和 lint exit code。 |
| 快速编译 | `python .../paper_note.py build <workspace> --quick --format json` | 能跑到 preflight，并返回 log / warning / status。 |
| 正式编译 | `python .../paper_note.py build <workspace>` | 能返回 pdf、log 和 warning 摘要。 |
| 视觉检查 | `python .../paper_note.py visual-check <workspace> --pdf <file>` | 能返回 preview 目录或明确的依赖缺失说明。 |
| 串行工作流 | `python .../paper_note.py run <id>` | 能验证 fetch -> setup -> build -> visual-check 的编排链路没有分叉。 |
| 文档收口 | `rg -n "paper_note_cli.py|fetch_arxiv_source.py|build_paper_pdf.py" writing-skill/paper-note-skill` | 只允许 `scripts-redesign.md` 这类历史设计文档保留旧名字。 |

## 这套设计的好处

1. 后续加功能时，文件落点清楚  
   改 arXiv 逻辑去 `core/arxiv.py`，改双语入口去 `core/entry.py`，改 lint 规则去 `core/lint_rules.py`。

2. 命令面干净  
   用户只需要记住 `paper_note.py` 一套入口，不需要记一串脚本名。

3. 文档和实现更容易一致  
   现在 workflow 文档、SKILL 和代码接口经常互相牵制。统一入口后，这个问题会小很多。

4. 后面再 package 化也更顺  
   这次先不做安装包，但只要内部层次先对了，后面要改成真正的 CLI 包就只是搬入口，不是重写业务。

## 最后的取舍

这次重构里，最重要的不是“拆成更多文件”，而是把公共接口、核心逻辑和模板资产三层分开。

如果这三层没分开，文件再多也只是把混乱切成更小块。

如果这三层分开了，后面不管是继续留在 `scripts/`，还是再往外做 package，代码都会稳得多。
