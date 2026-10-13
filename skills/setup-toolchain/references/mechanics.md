# 机制——这条链实际怎么工作的

手工接线、调试反常行为、或覆盖没有配方的文件类型时读这个。

## 两个 hook 槽位

每种文件类型在 `.pre-commit-config.yaml` 里最多占两个槽：

1. **format**——`git-format-staged --formatter "<cmd>"`。formatter 改写 index 里的*暂存内容*并把工作区文件打补丁到一致——worktree 与 index 两侧相同，pre-commit 的 "files were modified" 检测不触发，commit 带着格式化后的内容落地。commit 不被格式化阻断，未暂存的工作区编辑不被碰。
2. **check**——普通命令、文件名当参数。失败即拦 commit。linter 在这。

hook 文件之外还有两个槽：

3. **原地 fixer**——不会 stdin→stdout 的 formatter 改写工作区文件、失败一次、用户 re-add 再提交（markdownlint-cli2、php-cs-fixer、dart format）。代价和 check 失败一样，但文件已经替你修好。
4. **CI**——塞不进 per-file 的全项目级工具：类型检查（tsc、pyright）、包级 linter（clippy、golangci-lint、detekt）、构建工具（gradle spotlessCheck、mvn、cargo test）、schema 校验（kubeconform）。

## git-format-staged 契约

`--formatter` 是一条 shell 命令，对每个暂存文件跑一次：

- **stdin**：暂存的 blob 内容（index 里的，不是工作区的）
- **stdout**：格式化后的内容——写回 index，成功后同步到工作区文件
- **`{}`**：替换成文件名——只是给 formatter 推断 parser/配置的*提示*（prettier `--stdin-filepath`、clang-format `--assume-filename`）。formatter 绝不能打开 `{}` 读写——那会碰工作区状态、破坏契约。

推论：

- 没有 stdin 模式的 formatter 当不了 gfs formatter——降级成原地 fixer。
- 部分暂存的文件也能正确格式化：gfs 操作的是 blob，只有已暂存的块被格式化。
- gfs 幂等：formatter 输出等于输入时不产生写。
- 工作区补丁正是"边改写边通过"的原因：pre-commit 只在 hook 跑完后工作区与 index 分叉时才报 "files were modified"。gfs 两侧写一样 → 不分叉 → 通过。（`--no-update-working-tree` 存在但会让文件在提交后保持脏状态——别用。）

## 会咬人的 pre-commit 语义

- **`types: [X]`** 靠 identify 按扩展名匹配——`types: [shell]` 命中所有 `.sh` 不看 shebang。子集文件无法解析时（zsh）在命令内部跳过，绝不维护会腐烂的 `exclude:` 文件名清单。
- **`files:`** 是对仓库相对路径的 Python 正则——`types` 太粗或不确定时用它（BUILD、Dockerfile、dotfile 扩展名）。
- **`entry:` 在仓库根跑**，走 shell。`language: system` 表示 pre-commit 不建环境——工具必须在 PATH 上。逐文件跳过用循环：`bash -c 'for f in "$@"; do ...; done' --`（`--` 占 `$0`，文件名填进 `$@`）。
- **改写文件的 hook 即使成功也算失败**——这就是原地 fixer 的 UX。gfs hook 不以副作用方式改工作区；内容置换是机制本身，所以干净通过。
- **`pass_filenames: false`** 给忽略参数的仓库级检查用（少见——优先 CI）。

## 实战里攒下来的坑

- **gitleaks `protect` 扫的是暂存 diff。** 历史 secret 只有在所在行进 diff 时才被揪出来——全量格式化提交重写整个文件正是这种场景。放行按精确值（`regexTarget = "line"`），绝不按路径。
- **prettier 改 yaml** 语义上保 anchors/aliases/merge keys，但可能搬动注释的挂载位置、把长标量折行——注释文字本身永远原样保留（所有 formatter 都不碰注释散文，见下节）。格式化提交要用项目自己的配置测试把门（`mihomo -t`、`helm template`……），不是靠肉眼读 diff。
- **markdownlint-cli2 没有 stdin 模式** → 只能当原地 fixer。
- **ubuntu-latest runner 自带 Homebrew** → CI 里 `brew install` 保持与本地开发同源。
- **shellcheck SC1090**（跟不上非固定 source）：用 `# shellcheck source=/dev/null` 修，别全仓禁用这条规则。
- **CI 里的 `npm run format:check` 只覆盖已提交文件。** 工作区 WIP 由 hooks 在用户下次提交时自愈——这就是全量格式化跳过 WIP 是安全的原因。
- **版本锁定**：npm 工具锁在 package.json（唯一事实源）；brew 工具随 brew 浮动——CI 与本地漂移时锁 CI 安装（`brew install tool@X` 或工具自带的版本 flag）。更硬的形态是官方 release 直取 + sha256 核验（`curl -fsSL … && echo "<sha256>  <path>" | sha256sum -c -`）——版本告警集不同的工具（shellcheck/actionlint/taplo/gitleaks/shfmt 这类）漂移咬人时换这种，recipes.md shell 卡有模板。
- **gfs 需要 HEAD**——它拿 index 对 HEAD diff，零提交仓库的首个 commit 所有 gfs hook 全挂。先 `git commit --no-verify` 落地一次（通常就是工具链提交本身），之后 hooks 正常。
- **原地 fixer 和 gfs 打同一文件**：fixer（markdownlint --fix）先改写工作区文件，与 index 分叉；gfs 接着格式化暂存 blob 并在其上打补丁——分叉仍在，gfs hook 也报 "files were modified" 失败一次。设计如此：re-add 再提交，一切都已修好。
- **prettier 的 md 表格补白按字符宽，不是显示宽**：CJK 表格全角字符 prettier 只算 1 列。仓内一旦另有「显示宽度对齐」约定（markdownlint MD060 + realign 工具这类组合——CJK 文档仓常配），两边会来回补白乒乓、永远跑不净。解法是整套替换链——pre-commit 的 prettier-md 钩换 `scripts/md_table_align.py` 原地 fixer + autocorrect-only、`package.json` 的 format glob 去掉 `**/*.md`、`.vscode` 的 `[markdown]` 去掉 defaultFormatter/formatOnSave（留 markdownlint fixAll）。完整接线块在 recipes.md 首卡「markdown 变体：CJK 表格对齐链」。

## 散文注释折行约定

yaml 配置模板的注释是给裸文件读的——没有渲染层替你折行，所以走「硬折行 + 语义断点」约定：**≤80 显示列（CJK 等 East Asian Wide/Fullwidth 字符按 2 列计），断点落在标点/从句边界**。依据与边界：

- 宽度带的业界形态：Google Go styleguide 取 80/100、Go stdlib 实测 ~70、Prometheus 官方 example config ~72-80、GitLab gitlab.rb ~70-79——可执行规则都是「文件内一致」。我们取 80。
- 断点的另一派是 semantic linefeeds / ventilated prose（Kernighan 1974、AsciiDoc 官方 one-sentence-per-line、SemBr spec）：句末必断、逗号/分号/冒号/破折号后应断、从句间可断——断在停顿处才不像随机截断。mid-token 断裂（`~/` 拆成两行、`详见` 悬空）是该修的形状。
- **没有 formatter 会重排注释文字**：prettier 对注释 verbatim 保留、js-yaml/PyYAML 直接丢弃、yamlfix 只修 `#` 间距、gofmt 不重排段落——注释里可能藏 ASCII 图/表格/代码，机械 reflow 有破坏风险，所有作者一致选择保守。该约定只能手写维护。
- 能自动化的只有宽度半段：`scripts/check-yaml-comments.py` 按显示宽度查纯注释行（`lstrip` 首个字符是 `#` 的行），无空格且无宽字符的单 token 行（长 URL 等不可断情形）豁免；块标量（`|`/`>`）与多行引号标量内部行首 `#` 是字面内容不是注释——checker 会先算出标量内容行集再跳过（yaml 里嵌 python/shell 摘录的场景）。不用 yamllint `line-length` 的原因：它数字符数不是显示宽度，CJK 行 40 字符=80 列会被放过。断点语义无法机检，机械重排交给编辑器 reflow（vim `gq`、Emacs `M-q`、VS Code Rewrap、JetBrains Fill Paragraph——它们按 textwidth/ruler 贪心折行，宽度能统一但断点不管语义）。
- 接线面：base 的 `.pre-commit-config.yaml` 有 `yaml-comment-width` check hook（`types: [yaml]`）、base `ci.yml` format job 有同名 step（裸跑扫 `git ls-files` 全部 yaml）、`.editorconfig` 的 `[*.{yml,yaml}]` 声明 `max_line_length = 80` 给编辑器 ruler。注释写在哪个文件类型都适用同一约定，但 hook 只挂 yaml——代码注释存量太大，进门前先修存量。

## 扩展规则——没有配方的类型

对它的 formatter 问两个问题：

1. **有 stdin→stdout 模式？** → gfs format hook（模板在 recipes.md 单工具表下面）。
2. **只认文件？** → 原地 fixer hook（`entry: <tool> <file-args>`、`language: system`、配 `types`/`files`）。

再看 linter：**逐文件可检查** → 文件参数型 check hook；**需要全项目**（类型检查、构建、schema registry）→ CI。如果某类型既没有正常 formatter 也没有文件级 linter（ps1、Linux 上的 plist），就别进链，在 AGENTS.md 里写明，而不是接个脆弱的东西。
