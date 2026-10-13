---
name: setup-toolchain
description: 为仓库搭建 format/lint/pre-commit/CI 工具链（含 yaml 注释宽度检查）、agent 入口（AGENTS.md + .agents/skills 为入库唯一事实源，.claude/skills 为 gitignore 的本机软链）与 MPE 预览环境（.crossnote，gitignore 本机层）。当用户要加 pre-commit hooks、接 formatter/linter、配置 agent 文件、统一各仓工具链、装 markdown 预览/pseudocode 渲染环境、或复刻这套布局时使用。
compatibility: 需要 git、node/npm、python3，系统工具走 brew（或等价包管理）。面向 macOS/Linux 仓库；Windows 侧文件（ps1）不进工具链。
---

# 搭建仓库工具链

镜像 devin-2api / mihomo-macos 布局的脚手架。流程驱动：普查仓库 → 用通用 base 加各语言配方拼装配置集 → 确认分叉决策 → 先修后挂 → 全量格式化 → 提交。

## 这套东西包含什么

- **Agent 入口**：`AGENTS.md` + `.agents/skills/` 入库为唯一事实源（每个 skill 目录带 `agents/openai.yaml` 供跨 harness 使用；Claude Code 原生读 `AGENTS.md`）；`.claude/skills`（目录级软链 → `../.agents/skills`，与全局 `~/.claude/skills` 同一约定）是 gitignore 的本机软链，由 `scripts/agent-links.sh` 重建。
- **Format 链**（版本以 `package.json` 为唯一事实源）：每个仓库都有 markdown + yaml + gitleaks；yaml 侧除 prettier 结构格式外还带 `scripts/check-yaml-comments.py` 注释宽度机检（散文注释折行约定见 [references/mechanics.md](references/mechanics.md)「散文注释折行约定」节）；其余文件类型按配方追加各自的 format/check hook。
- **pre-commit**：`local` hooks 走 git-format-staged——formatter 改写暂存内容并同步工作区文件使两侧一致，commit 不被格式化阻断，未暂存编辑不受污染；check 类 hook 失败才拦。gitleaks 是 secret 门。
- **Dotfiles**：.editorconfig、.gitattributes、.prettierrc/.prettierignore、.markdownlint.jsonc（规则）+ .markdownlint-cli2.jsonc（忽略）、.gitleaks.toml、.git-blame-ignore-revs、.vscode/*。
- **MPE 预览环境**：`assets/.crossnote/` 是唯一事实源，各仓 `/.crossnote/` 由 `scripts/crossnote-links.sh` 建链接农场（软链 + 两个硬链）并 gitignore——parser.js（QuickJS 沙箱）+ style.less 主题 + pseudocode 渲染链，机制与硬约束见 [references/crossnote.md](references/crossnote.md)。
- **CI**：一个 workflow 跑与本地相同的检查；shell 工具在 ubuntu-latest 上 brew 安装保持同源。

## 流程

### 1. 普查——产出类型清单

动手前先跑：

- 文件普查：`find . -path ./.git -prune -o -type f -print | sed 's/.*\.//' | sort | uniq -c | sort -rn | head`
- shell 文件 shebang 普查（逐个 `head -1` 各 `*.sh`）——bash vs zsh 决定 shell 配方走哪支
- 现状：`AGENTS.md`？`CLAUDE.md`？`.agents/`？`.claude/`（已入库还是 gitignore）？`package.json`？已有 lint/pre-commit/CI 配置要保留还是替换？
- 已装工具：`command -v node npm pre-commit shfmt shellcheck autocorrect ruff gitleaks gofmt golangci-lint rustfmt clang-format`
- Secrets 态势：库内有没有已提交凭据？gitignored env 文件？仓库自有凭据格式长什么样（喂给 gitleaks 自定义规则）？
- `git status`：未提交 WIP 会和全量格式化提交（第 6 步）纠缠

产出：**类型清单**（仓内存在的文件类型），驱动下面所有选择。

### 2. 拼装配置集

把 `assets/` 里所有文件拷到仓库根——那是通用层。然后对类型清单里的每种类型，应用 [references/recipes.md](references/recipes.md) 里对应的卡：

- `.pre-commit-config.yaml`：base 已有 markdown + yaml + gitleaks；把配方的 hook 块追加到 local repo 的 `hooks:` 下——配方块写在 0 列，粘贴时按现有条目缩进 6 格
- `.github/workflows/ci.yml`：base 有 format job；把配方的 CI job/steps 追加到 `jobs:`（缩进 2）或 `steps:`（缩进 6）下
- `package.json`：加配方的 npm devDeps（多数配方不需要——工具走 brew）
- `.gitignore`：加 `/node_modules/`、`/.claude/`、`/.crossnote/`，外加配方补充项（`__pycache__/`、`target/`……）；旧仓若已 gitignore `/CLAUDE.md` 或有实体 `CLAUDE.md`，内容并进 `AGENTS.md` 后删掉
- 配方列出的 assets（如 `scripts/fmt-shell.sh`）只在对应类型存在时才拷；`scripts/check-yaml-comments.py` 是通用层（yaml 每个仓库都有），随 assets 一起拷

没有配方的类型：按 [references/mechanics.md](references/mechanics.md) 的扩展规则处理。

### 3. 确认分叉决策

每项都先给推荐答案；已定的跳过——完整推理见 [references/decisions.md](references/decisions.md)：

- **入口**：`.claude/skills` 软链（推荐——仓库保持工具中立，避免 Windows clone 软链断裂）vs 入库实体 skill 目录
- **md 链选型**：默认 prettier-md；CJK 文档仓走「CJK 表格对齐链」变体（recipes.md 首卡——prettier 字符宽补白与 MD060 显示宽度互斥）
- **有争议的生态**：ts/js formatter 三选一、JVM 独立二进制 vs 构建工具、php/dart 原地 fixer
- **Lint 严重度**：默认先修后挂——先修完存量违规再上门。绝不降严重度凑过；用户拒绝修就明说：这些文件下次提交会被 hook 拦
- **Secrets**：自定义 gitleaks 规则（仓库自有凭据格式）+ 历史已提交 secret 的精确值放行。绝不整路径放行

### 4. 写入与接线

- `npm install`；`brew install` 各配方的工具；`pre-commit install`；`git config blame.ignoreRevsFile .git-blame-ignore-revs`
- `assets/scripts/crossnote-links.sh` 拷进 `<repo>/scripts/`（chmod +x）后跑一遍——建"事实源软链 + runtime 硬链"的链接农场（机制与分叉规则见 [references/crossnote.md](references/crossnote.md)；别用 rsync 实体拷贝，会断同步）
- 跑一遍 `scripts/agent-links.sh` → 生成 `.claude/skills -> ../.agents/skills` 目录级软链，并顺手清掉旧版留下的 `CLAUDE.md -> AGENTS.md` 软链。已入库的 `.claude/skills/` 内容先 `git mv` 迁进 `.agents/skills/`，每个 SKILL.md 旁边补 `agents/openai.yaml`；旧式逐 skill 软链农场会被脚本自动升级成目录级（混有实体目录/外来软链时拒绝）
- `AGENTS.md`：按 [references/agents-md.md](references/agents-md.md) 追加段落，文件类型 bullets 按类型清单裁剪

### 5. 先修后挂

逐配方跑 **验证** 命令全仓检查并修完再让门生效——每张卡上列了命令。格式化配置类文件后用项目自己的解析器/检查器复验（`mihomo -t`、`go build`，看项目）——prettier 改 yaml 保 anchors/merge keys，但还是要验。

### 6. 全量格式化仪式

- 独立一个 `style:` 提交装全部格式化产出——绝不折进功能提交
- 把它的 hash 记进 `.git-blame-ignore-revs`，跟一个 `chore:` 提交
- 未提交 WIP 会纠缠：要么只格式化干净文件（剩下的交给 hooks 在用户下次提交时自愈），要么拿到明确许可全扫

### 7. 验证

- [ ] `npm run format:check` + `npm run lint:md` + `python3 scripts/check-yaml-comments.py` 干净
- [ ] 各配方验证命令在对应文件上干净
- [ ] `gitleaks dir .` 只剩 gitignored/已放行项
- [ ] 一次真实 `git commit` 全 hook 绿（原地改写型 fixer 如 markdownlint --fix 改写时会失败一次要 re-add——设计如此）。零提交的仓库先用一次 `git commit --no-verify` 落地——gfs 需要 HEAD 才能 diff
- [ ] `.claude/skills -> ../.agents/skills` 可解析；`git check-ignore` 确认它及 `/.crossnote/` 被忽略
- [ ] `.crossnote/` 链接农场就位：四件套+`scripts/tests/vendor` 软链可解析、`pseudocode-runtime.js` 与 `theme-toggle.js` 均与事实源同 inode（`test a -ef b` 跨平台，`stat -c %i`/`stat -f %i` 分平台对比）；`.vscode/settings.json` 带 `markdown-preview-enhanced.*` 键块

### 8. 提交布局

- `build(tooling):`——机制：配置、package.json、scripts、.gitignore、.agents/ 迁移、AGENTS.md 段落、CI
- `style:`——只有全量格式化的产出
- `chore:`——blame-ignore rev

## 既定偏好（不要再争）

- `AGENTS.md` 是 agent 指令唯一事实源——Claude Code 原生读它，不需要 `CLAUDE.md` 软链或副本。`/.claude/` 保持 gitignore。
- formatter 走 git-format-staged 写 index 并同步工作区——两侧一致所以 commit 不被格式化阻断；check 类 hook 失败才拦。原地改写型 fixer（markdownlint --fix、php-cs-fixer、dart format）改写后失败一次 → re-add → 提交。
- zsh 脚本不进 shell 链——shfmt/shellcheck 都不认 zsh。按 shebang 嗅探透传，别为了让它们可被 lint 去改 shebang。
- prettier tabWidth 4 基础、yaml 2；markdownlint `MD007` indent 4。
- 散文注释折行约定：≤80 显示列（CJK 按 2 列计）+ 断点取标点/从句边界。宽度由 `check-yaml-comments.py` 机检，断点只能人工——没有 formatter 重排注释文字（依据见 mechanics.md）。编辑器 `max_line_length = 80` 只管 yaml，`.md` 不加（我们的 markdown 一段一行、由渲染器折行）。
- Secrets 态势：历史已提交 secret 走精确值放行（`regexTarget = "line"`）；占位符模式豁免；真实凭据只存在于 gitignored env 文件。
- 文档与注释跟随仓库现有语言；Conventional Commits 用英文；一个提交一个逻辑变更。
