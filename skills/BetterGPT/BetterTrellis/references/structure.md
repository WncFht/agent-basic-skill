# Structure

## Core Layers

### 1. `.trellis/`

这是 Trellis 的项目知识与工作流层。

常见内容：

- `workflow.md`：工作流说明
- `spec/`：规范库
- `workspace/`：会话日志
- `tasks/`：任务系统
- `scripts/task.py`：任务管理脚本

### 2. `AGENTS.md`

这是 Codex 的入口层。

在 Trellis for Codex 中，它负责把项目级基础上下文暴露给 Codex，而不是承载全部规范细节。

### 3. `.agents/skills/`

这是共享 skill 层。

适合放跨平台可复用的 skills，不只服务 Codex，也可供其他兼容 agent 系统使用。

### 4. `.codex/`

这是 Codex 平台接入层。

常见内容：

- `config.toml`：项目级 Codex 配置
- `agents/`：自定义 agents
- `skills/`：Codex 专属 skills
- `hooks/session-start.py`
- `hooks.json`

补充说明：

- `hooks/session-start.py` 与 `hooks.json` 表示 hooks 接入位
- 但是否“当前已生效”，还取决于平台是否真的支持 hooks
- 在 Windows 原生 Codex 下，默认不要把这两项直接解释成“当前一定在运行”

## How To Explain It

对用户解释时，优先用这套分层：

- `.trellis/` 管知识与流程
- `AGENTS.md` 管入口
- `.agents/skills/` 管共享能力
- `.codex/` 管平台接入

如果当前平台是 Windows 原生 Codex，还要补一句：

- 当前实际工作流优先依赖 `AGENTS.md` + skills + 文档驱动 workflow
- hooks 更适合作为未来兼容位或占位，不要误报为当前已生效能力

不要混成一句“这些都是提示词文件”。
