# AGENTS.md 段落模板

工具链接通后把这些段落追加到仓库的 `AGENTS.md`。跟随仓库的文档语言（这些仓库用中文）。下面的文件类型 bullets 是并集——只保留已应用配方（见 [recipes.md](recipes.md)）对应的行，每行的写法对齐该配方的实际接法。

## 格式化工具链（模板）

```markdown
## 格式化工具链

`git commit` 会走 pre-commit：formatter 经 git-format-staged 改写暂存内容并同步工作区（两侧一致，commit 不被格式化阻断，未暂存编辑不受污染）；check 类 hook 失败才拦。前置条件：`npm install`、`brew install <本仓需要的系统工具>`、`pre-commit install`。版本以 `package.json` 为唯一事实源，编辑器（`.vscode/settings.json` 的 prettierPath）与 hook 同源。

- `*.sh`：`shfmt -i 2`（gfs）+ `shellcheck -S warning`。zsh 脚本不在链内——两者都不支持 zsh，`scripts/fmt-shell.sh` 对 zsh shebang 原样透传。
- `*.py`：`ruff format`（gfs）+ `ruff check`。
- `*.md`：`markdownlint-cli2 --fix` 原地改写（改写会 fail 一次，重新 `git add` 再提交）→ `autocorrect --stdin | prettier`（gfs）。
- `*.yaml`：`prettier`（gfs）。缩进规则：yaml 2 空格、md 4 空格，见 `.prettierrc` overrides。
- `*.go`：`gofmt`（gfs）；提交前跑 `golangci-lint run`，规则见 `.golangci.yml`。
- gitleaks 拦 secret；`.gitleaks.toml` 自定义规则与精确值放行见文件注释。

CI（`.github/workflows/ci.yml`）与本地同源，本地不过 CI 必挂。
```

## Agent 入口约定（固定文本）

```markdown
## Agent 入口约定

`AGENTS.md` 与 `.agents/` 是入库的唯一事实源（skill 本体在 `.agents/skills/`，各带 `agents/openai.yaml` 元数据）。`.claude/skills/` 是指向 `.agents/skills/` 的软链，属本机便利层、不入库；clone 后跑 `scripts/agent-links.sh` 重建。
```

## 项目运维约定（从仓库事实写，不用模板）

这一节按仓库的 README/scripts/service 文件里的事实逐仓写——工具链那节覆盖的是*代码怎么提交*，这节覆盖*项目怎么跑*。值得写的内容（两个参考仓的实例）：

- 仓库与 live/部署目录的边界、同步流向（`update.sh` 仓→live、`sync-from-live.sh` live→仓）
- "不要自动部署"类规则、scratch/测试在哪做
- 服务面：launchd/systemd/schtasks 单元名、wrapper 命令、优雅重启要求
- 诊断入口（doctor 脚本、debug log 布局、API endpoint）
- secret/凭据文件位置（gitignored env 模板 vs 真实值）

只写 agent 能验证或需要避免踩的东西——这一节是契约，不是文档。
